"""抗体疏水性改造任务入队。"""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.engines import HYDRO_REDESIGN_ENGINE
from app.job_paths import sanitize_label
from app.models import Batch, Job, JobStatus
from app.queue_service import dispatch_to_gpu
from worker.tasks import run_hydro_redesign_job

ALLOWED_STRUCT = {".pdb", ".cif", ".mmcif"}
HYDRO_BATCH_TYPE = "hydro_redesign"
_AA = re.compile(r"[^A-Za-z]")


def parse_vhh_records(fasta_text: str) -> list[tuple[str, str]]:
    """多条 FASTA：每条记录一条 VHH（批量）。无表头则视为单条 H。"""
    text = (fasta_text or "").replace("\r", "").strip()
    if not text:
        raise HTTPException(400, "FASTA 无效：未解析到任何链")
    records: list[tuple[str, str]] = []
    if ">" not in text:
        seq = _AA.sub("", text).upper()
        if len(seq) < 70:
            raise HTTPException(400, "FASTA 序列过短，需要完整 VHH 可变区")
        return [("H", seq)]
    current = "seq1"
    buf: list[str] = []
    seen: dict[str, int] = {}
    started = False
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith(">"):
            if buf:
                seq = _AA.sub("", "".join(buf)).upper()
                if seq:
                    records.append((current, seq))
            started = True
            raw = s[1:].split()[0] or "seq"
            n = seen.get(raw, 0) + 1
            seen[raw] = n
            current = raw if n == 1 else f"{raw}_{n}"
            buf = []
        else:
            buf.append(s)
    if buf:
        seq = _AA.sub("", "".join(buf)).upper()
        if seq:
            records.append((current, seq))
    if not started and records:
        records = [("H", records[0][1])]
    if not records:
        raise HTTPException(400, "FASTA 无效：未解析到任何链")
    too_short = [hid for hid, seq in records if len(seq) < 70]
    if too_short:
        raise HTTPException(400, f"序列过短（需完整 VHH）：{', '.join(too_short[:8])}")
    return records


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
        raise HTTPException(
            400,
            f"单条任务只接受抗体链 H / L。多条 VHH 请用批量。收到 {', '.join(extra)}",
        )
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
    batch_id: str | None = None,
    heavy_chain_id: str | None = None,
    defer_dispatch: bool = False,
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
        batch_id=batch_id,
        heavy_chain_id=heavy_chain_id,
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
    if not defer_dispatch:
        async_result = dispatch_to_gpu(run_hydro_redesign_job, job.id)
        job.celery_task_id = async_result.id
    return job


def dispatch_hydro_redesign_jobs(jobs: list[Job]) -> None:
    for job in jobs:
        async_result = dispatch_to_gpu(run_hydro_redesign_job, job.id)
        job.celery_task_id = async_result.id


def create_and_queue_hydro_redesign_batch(
    db: Session,
    *,
    user_id: str,
    name: str,
    fasta_text: str,
    allow_cdr: bool = False,
    allow_charged: bool = False,
) -> tuple[Batch, list[Job]]:
    records = parse_vhh_records(fasta_text)
    cap = int(settings.hydro_redesign_max_batch)
    if len(records) > cap:
        raise HTTPException(400, f"批量最多 {cap} 条 VHH，当前 {len(records)} 条")
    batch_name = (name or "").strip() or f"疏水改造_{len(records)}条"
    batch = Batch(
        user_id=user_id,
        name=batch_name,
        batch_type=HYDRO_BATCH_TYPE,
        target_name="",
        target_chain_id="",
        target_sequence="",
        heavy_chain_id="H",
        heavy_chain_count=len(records),
        use_msa_server=True,
    )
    db.add(batch)
    db.flush()
    jobs: list[Job] = []
    for hid, seq in records:
        fasta = f">H\n{seq}\n"
        job_name = f"{batch_name}_{hid}"[:128]
        jobs.append(
            create_and_queue_hydro_redesign_job(
                db,
                user_id=user_id,
                name=job_name,
                fasta_text=fasta,
                allow_cdr=allow_cdr,
                allow_charged=allow_charged,
                batch_id=batch.id,
                heavy_chain_id=hid,
                defer_dispatch=True,
            )
        )
    return batch, jobs
