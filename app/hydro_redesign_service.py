"""抗体疏水性改造任务入队。"""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import settings
from app.engines import HYDRO_REDESIGN_ENGINE
from app.job_paths import sanitize_label
from app.models import Job, JobStatus
from app.queue_service import dispatch_to_gpu
from worker.tasks import run_hydro_redesign_job

ALLOWED_STRUCT = {".pdb", ".cif", ".mmcif"}


def parse_fasta_chains(fasta_text: str) -> dict[str, int]:
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
    if "H" not in chains and len(chains) == 1:
        cid = next(iter(chains))
        chains = {"H": chains[cid]}
    extra = [k for k in chains if k not in {"H", "L"}]
    if extra:
        raise HTTPException(400, f"第一版只接受抗体链 H / L，收到 {', '.join(extra)}")
    if sum(chains.values()) < 20:
        raise HTTPException(400, "FASTA 序列过短")
    return chains


async def save_structure_upload(upload: UploadFile, dest: Path) -> Path:
    suffix = Path(upload.filename or "ab.pdb").suffix.lower()
    if suffix not in ALLOWED_STRUCT:
        raise HTTPException(400, "结构需为 .pdb / .cif / .mmcif")
    if suffix == ".mmcif":
        suffix = ".cif"
        dest = dest.with_suffix(".cif")
    content = await upload.read()
    if len(content) < 80:
        raise HTTPException(400, "上传的结构文件太小或为空")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return dest


def create_and_queue_hydro_redesign_job(
    db,
    *,
    user_id: str,
    name: str,
    fasta_text: str,
    structure_path: Path | None = None,
    allow_cdr: bool = False,
    allow_charged: bool = False,
) -> Job:
    fasta_text = fasta_text.strip()
    if not fasta_text.startswith(">"):
        fasta_text = ">H\n" + re.sub(r"\s+", "", fasta_text) + "\n"
    chains_json = parse_fasta_chains(fasta_text)

    slug = sanitize_label(name or "hydro", max_len=32)
    settings.hydro_redesign_out_root.mkdir(parents=True, exist_ok=True)
    campaign = settings.hydro_redesign_out_root / f"{slug}__{uuid.uuid4().hex[:8]}"
    (campaign / "input").mkdir(parents=True, exist_ok=True)
    fasta_norm = fasta_text if fasta_text.endswith("\n") else fasta_text + "\n"
    (campaign / "input" / "sequences.fasta").write_text(fasta_norm, encoding="utf-8")
    if structure_path and structure_path.is_file():
        dest = campaign / "input" / f"structure{structure_path.suffix.lower() or '.pdb'}"
        dest.write_bytes(structure_path.read_bytes())
        structure_path = dest

    job = Job(
        user_id=user_id,
        name=name,
        engine=HYDRO_REDESIGN_ENGINE,
        status=JobStatus.queued.value,
        stage="queued",
        fasta_text=fasta_norm[:8000],
        sequence_hash=hashlib.sha256(fasta_norm.encode()).hexdigest(),
        chains_json=chains_json,
        total_length=sum(chains_json.values()),
        use_msa_server=True,
        params_json={
            "allow_cdr": allow_cdr,
            "allow_charged": allow_charged,
            "structure_path": str(structure_path) if structure_path else None,
            "slug": slug,
        },
        work_dir=str(campaign),
    )
    db.add(job)
    db.flush()
    async_result = dispatch_to_gpu(run_hydro_redesign_job, job.id)
    job.celery_task_id = async_result.id
    return job
