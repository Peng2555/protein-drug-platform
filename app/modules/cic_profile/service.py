"""抗体 CIC 表面斑任务入队。"""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

from fastapi import HTTPException

from app.core.config import settings
from app.core.engines import CIC_PROFILE_ENGINE
from app.common.job_paths import sanitize_label
from app.core.models import Job, JobStatus
from app.core.queue import dispatch_to_gpu
from app.common.sequence_inputs import parse_fasta_chain_lengths, save_structure_upload
from worker.tasks import run_cic_profile_job

def parse_fasta_chains(fasta_text: str) -> dict[str, int]:
    return parse_fasta_chain_lengths(
        fasta_text,
        allowed_chain_ids={"H", "L"},
        extra_chains_error_template="第一版只接受抗体链 H / L，收到 {ids}",
        min_total_length=20,
        too_short_error="FASTA 序列过短",
    )


def create_and_queue_cic_profile_job(
    db,
    *,
    user_id: str,
    name: str,
    fasta_text: str,
    structure_path: Path | None = None,
    ph: float = 7.0,
) -> Job:
    fasta_text = fasta_text.strip()
    if not fasta_text.startswith(">"):
        fasta_text = ">H\n" + re.sub(r"\s+", "", fasta_text) + "\n"
    chains_json = parse_fasta_chains(fasta_text)
    try:
        ph = float(ph)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "pH 无效") from exc
    if ph < 4.0 or ph > 10.0:
        raise HTTPException(400, "第一版 pH 仅支持 4–10")

    slug = sanitize_label(name or "cic", max_len=32)
    settings.cic_profile_out_root.mkdir(parents=True, exist_ok=True)
    campaign = settings.cic_profile_out_root / f"{slug}__{uuid.uuid4().hex[:8]}"
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
        engine=CIC_PROFILE_ENGINE,
        status=JobStatus.queued.value,
        stage="queued",
        fasta_text=fasta_norm[:8000],
        sequence_hash=hashlib.sha256(fasta_norm.encode()).hexdigest(),
        chains_json=chains_json,
        total_length=sum(chains_json.values()),
        use_msa_server=True,
        params_json={
            "ph": ph,
            "structure_path": str(structure_path) if structure_path else None,
            "slug": slug,
        },
        work_dir=str(campaign),
    )
    db.add(job)
    db.flush()
    async_result = dispatch_to_gpu(run_cic_profile_job, job.id)
    job.celery_task_id = async_result.id
    return job
