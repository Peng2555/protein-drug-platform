"""Affinity redesign (antibody_redesign) end-to-end workflow jobs."""

from __future__ import annotations

import hashlib
import re
import sys
import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import settings
from app.engines import AFFINITY_REDESIGN_ENGINE
from app.job_paths import sanitize_label
from app.models import Job, JobStatus
from app.queue_service import dispatch_to_gpu
from worker.tasks import run_affinity_redesign_job

ALLOWED_STRUCT = {".pdb", ".cif", ".mmcif"}


def _ensure_package() -> None:
    from app.config import affinity_redesign_src_dir, ensure_affinity_redesign_on_path

    ensure_affinity_redesign_on_path()
    try:
        import affinity_redesign  # noqa: F401
    except ImportError as exc:
        src = affinity_redesign_src_dir()
        raise HTTPException(
            503,
            "affinity_redesign 未安装；仓库应包含 affinity_redesign/src。"
            f"若用独立目录，请设置 ANTIBODY_REDESIGN_ROOT，或执行 pip install -e {src.parent}，然后重启 API/worker",
        ) from exc


def _parse_fasta_chains(fasta_text: str) -> dict[str, int]:
    chains: dict[str, int] = {}
    current: str | None = None
    buf: list[str] = []
    for line in fasta_text.replace("\r", "").split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith(">"):
            if current is not None:
                chains[current] = len("".join(buf))
            current = s[1:].split()[0] or "seq"
            buf = []
        else:
            buf.append(re.sub(r"\s+", "", s))
    if current is not None:
        chains[current] = len("".join(buf))
    if not chains:
        raise HTTPException(400, "FASTA 无效：未解析到任何链")
    if sum(chains.values()) < 20:
        raise HTTPException(400, "FASTA 序列过短")
    return chains


async def save_structure_upload(upload: UploadFile, dest: Path) -> Path:
    suffix = Path(upload.filename or "complex.pdb").suffix.lower()
    if suffix not in ALLOWED_STRUCT:
        raise HTTPException(400, "复合物结构需为 .pdb / .cif / .mmcif")
    if suffix == ".mmcif":
        suffix = ".cif"
        dest = dest.with_suffix(".cif")
    content = await upload.read()
    if len(content) < 80:
        raise HTTPException(400, "上传的结构文件太小或为空")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return dest


def create_and_queue_affinity_redesign_job(
    db,
    *,
    user_id: str,
    name: str,
    fasta_text: str,
    complex_path: Path | None = None,
    skip_round1: bool = False,
) -> Job:
    _ensure_package()
    from affinity_redesign.pipeline.workflow import bootstrap_campaign

    fasta_text = fasta_text.strip()
    if len(fasta_text) < 20:
        raise HTTPException(400, "请提供有效的 FASTA 序列")
    chains_json = _parse_fasta_chains(fasta_text)

    slug = sanitize_label(name or "antibody", max_len=32)
    settings.affinity_redesign_out_root.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".fasta",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        tmp.write(fasta_text if fasta_text.endswith("\n") else fasta_text + "\n")
        tmp_fasta = Path(tmp.name)

    try:
        campaign_dir = bootstrap_campaign(
            slug=slug,
            fasta=tmp_fasta,
            complex_pdb=complex_path,
            runs_root=settings.affinity_redesign_out_root,
        )
    finally:
        tmp_fasta.unlink(missing_ok=True)

    entry_mode = "structure" if complex_path else "sequence_only"
    job = Job(
        user_id=user_id,
        name=name,
        engine=AFFINITY_REDESIGN_ENGINE,
        status=JobStatus.queued.value,
        stage="queued",
        fasta_text=fasta_text[:8000],
        sequence_hash=hashlib.sha256(fasta_text.encode()).hexdigest(),
        chains_json=chains_json,
        total_length=sum(chains_json.values()),
        use_msa_server=True,
        params_json={
            "skip_round1": skip_round1,
            "entry_mode": entry_mode,
            "slug": slug,
        },
        work_dir=str(campaign_dir),
    )
    db.add(job)
    db.flush()

    async_result = dispatch_to_gpu(run_affinity_redesign_job, job.id)
    job.celery_task_id = async_result.id
    return job
