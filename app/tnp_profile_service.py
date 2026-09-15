"""VHH 可开发性画像任务入队。"""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.engines import TNP_PROFILE_ENGINE
from app.job_paths import sanitize_label
from app.models import Batch, Job, JobStatus
from app.queue_service import dispatch_to_gpu
from app.sequence_inputs import (
    parse_fasta_chain_lengths,
    parse_vhh_records as parse_common_vhh_records,
    save_structure_upload,
)
from worker.tasks import run_tnp_profile_job

TNP_BATCH_TYPE = "tnp_profile"


def parse_vhh_records(fasta_text: str) -> list[tuple[str, str]]:
    """多条 FASTA：每条记录一条 VHH。无表头则视为单条 H。"""
    return parse_common_vhh_records(fasta_text)


def parse_fasta_chains(fasta_text: str) -> dict[str, int]:
    return parse_fasta_chain_lengths(
        fasta_text,
        allowed_chain_ids={"H"},
        extra_chains_error_template="单条任务只接受一条 VHH（链 ID H）。多条请用批量。收到 {ids}",
        min_total_length=70,
        too_short_error="FASTA 序列过短，需要完整 VHH 可变区",
    )


def create_and_queue_tnp_profile_job(
    db,
    *,
    user_id: str,
    name: str,
    fasta_text: str,
    structure_path: Path | None = None,
    batch_id: str | None = None,
    heavy_chain_id: str | None = None,
    defer_dispatch: bool = False,
) -> Job:
    fasta_text = fasta_text.strip()
    if not fasta_text.startswith(">"):
        fasta_text = ">H\n" + re.sub(r"\s+", "", fasta_text) + "\n"
    chains_json = parse_fasta_chains(fasta_text)

    slug = sanitize_label(name or "tnp", max_len=32)
    settings.tnp_profile_out_root.mkdir(parents=True, exist_ok=True)
    campaign = settings.tnp_profile_out_root / f"{slug}__{uuid.uuid4().hex[:8]}"
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
        engine=TNP_PROFILE_ENGINE,
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
            "structure_path": str(structure_path) if structure_path else None,
            "slug": slug,
            "scheme": "kabat",
            "structure_engine": "boltz2",
        },
        work_dir=str(campaign),
    )
    db.add(job)
    db.flush()
    return job


def dispatch_tnp_profile_jobs(jobs: list[Job]) -> None:
    for job in jobs:
        async_result = dispatch_to_gpu(run_tnp_profile_job, job.id)
        job.celery_task_id = async_result.id


def create_and_queue_tnp_profile_batch(
    db: Session,
    *,
    user_id: str,
    name: str,
    fasta_text: str,
) -> tuple[Batch, list[Job]]:
    records = parse_vhh_records(fasta_text)
    cap = int(settings.tnp_profile_max_batch)
    if len(records) > cap:
        raise HTTPException(400, f"批量最多 {cap} 条 VHH，当前 {len(records)} 条")
    batch_name = (name or "").strip() or f"VHH画像_{len(records)}条"
    batch = Batch(
        user_id=user_id,
        name=batch_name,
        batch_type=TNP_BATCH_TYPE,
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
            create_and_queue_tnp_profile_job(
                db,
                user_id=user_id,
                name=job_name,
                fasta_text=fasta,
                batch_id=batch.id,
                heavy_chain_id=hid,
                defer_dispatch=True,
            )
        )
    return batch, jobs
