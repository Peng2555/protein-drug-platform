"""抗体额外二硫键任务入队：复用已完成的 Boltz2 多模型作业。"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.job_paths import sanitize_label
from app.core.config import settings
from app.core.engines import TM_DISULFIDE_ENGINE
from app.core.models import Job, JobStatus
from app.core.queue import dispatch_to_cpu
from worker.tasks import run_tm_disulfide_job

from algorithm_paths import bootstrap_algorithm_paths

bootstrap_algorithm_paths()

from tm_disulfide.constants import MINIMUM_MODELS_PASSED
from tm_disulfide.qc import discover_boltz_models


def source_structure_paths(job: Job) -> list[Path]:
    roots: list[Path] = []
    if job.work_dir:
        roots.append(Path(job.work_dir))
    fallback = settings.boltz2_out_root / job.id
    if fallback not in roots:
        roots.append(fallback)
    for root in roots:
        if root.is_dir():
            found = discover_boltz_models(root)
            if found:
                return found
    return []


def list_source_fold_jobs(db: Session, user_id: str, *, limit: int = 50) -> list[tuple[Job, int]]:
    rows = db.scalars(
        select(Job)
        .where(
            Job.user_id == user_id,
            Job.engine == "boltz2",
            Job.status == JobStatus.done.value,
        )
        .order_by(Job.created_at.desc())
        .limit(200)
    ).all()
    out: list[tuple[Job, int]] = []
    for job in rows:
        n_models = len(source_structure_paths(job))
        if n_models >= MINIMUM_MODELS_PASSED:
            out.append((job, n_models))
        if len(out) >= limit:
            break
    return out


def create_and_queue_tm_disulfide_job(
    db,
    *,
    user_id: str,
    name: str,
    source_job_id: str,
) -> Job:
    source = db.get(Job, source_job_id)
    if not source or source.user_id != user_id:
        raise HTTPException(404, "找不到对应的 Boltz2 作业")
    if source.engine != "boltz2":
        raise HTTPException(400, "只接受已完成的 Boltz2 作业")
    if source.status != JobStatus.done.value:
        raise HTTPException(400, "源作业尚未完成")

    paths = source_structure_paths(source)
    if len(paths) < MINIMUM_MODELS_PASSED:
        raise HTTPException(
            400,
            f"源作业模型不足：需要至少 {MINIMUM_MODELS_PASSED} 套 *_model_N.cif，实际 {len(paths)}",
        )

    fasta_text = (source.fasta_text or "").strip()
    if source.work_dir:
        fasta_file = Path(source.work_dir) / "input" / "sequences.fasta"
        if fasta_file.is_file():
            fasta_text = fasta_file.read_text(encoding="utf-8").strip()
    if not fasta_text.startswith(">"):
        raise HTTPException(400, "源作业缺少 FASTA")

    slug = sanitize_label(name or "tm_disulfide", max_len=32)
    settings.tm_disulfide_out_root.mkdir(parents=True, exist_ok=True)
    campaign = settings.tm_disulfide_out_root / f"{slug}__{uuid.uuid4().hex[:8]}"
    (campaign / "input").mkdir(parents=True, exist_ok=True)
    fasta_norm = fasta_text if fasta_text.endswith("\n") else fasta_text + "\n"
    (campaign / "input" / "sequences.fasta").write_text(fasta_norm, encoding="utf-8")
    (campaign / "input" / "source.json").write_text(
        json.dumps(
            {
                "source_job_id": source.id,
                "n_models": len(paths),
                "paths": [str(path) for path in paths],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    chains_json = source.chains_json or {}
    job = Job(
        user_id=user_id,
        name=name,
        engine=TM_DISULFIDE_ENGINE,
        status=JobStatus.queued.value,
        stage="queued",
        parent_job_id=source.id,
        fasta_text=fasta_norm[:8000],
        sequence_hash=hashlib.sha256(fasta_norm.encode()).hexdigest(),
        chains_json=chains_json,
        total_length=source.total_length or sum(chains_json.values()),
        use_msa_server=False,
        params_json={
            "source_job_id": source.id,
            "source_work_dir": source.work_dir,
            "structure_paths": [str(path) for path in paths],
            "n_models": len(paths),
            "slug": slug,
        },
        work_dir=str(campaign),
    )
    db.add(job)
    db.flush()
    async_result = dispatch_to_cpu(run_tm_disulfide_job, job.id)
    job.celery_task_id = async_result.id
    return job
