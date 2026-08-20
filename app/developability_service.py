"""ESM-2 developability redesign job service."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.engines import DEVELOPABILITY_ENGINE, is_fold_engine
from app.job_paths import job_output_dir
from app.job_service import fasta_from_seqs, sequence_hash
from app.md_service import resolve_structure_path
from app.models import Job, JobStatus
from app.queue_service import dispatch_to_gpu
from worker.tasks import run_developability_job

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from boltz_runner import parse_fasta_text


def _copy_structure(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"structure{src.suffix.lower() or '.cif'}"
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    return dest


async def save_uploaded_structure(upload: UploadFile, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or "input.cif").suffix.lower()
    if suffix not in {".cif", ".mmcif", ".pdb"}:
        raise HTTPException(400, "MAXWELL 需要 .cif 或 .pdb")
    dest = dest_dir / f"structure{suffix}"
    content = await upload.read()
    if len(content) < 80:
        raise HTTPException(400, "结构文件太小或为空")
    dest.write_bytes(content)
    return dest


def create_and_queue_developability_job(
    db: Session,
    *,
    user_id: str,
    name: str,
    fasta_text: str,
    params: dict,
    structure_src: Path | None = None,
    fold_job_id: str | None = None,
) -> Job:
    try:
        seqs = parse_fasta_text(fasta_text)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not seqs:
        raise HTTPException(400, "FASTA 为空")
    chains_json = {cid: len(seq) for cid, seq in seqs.items()}
    total_length = sum(chains_json.values())
    if total_length > settings.max_total_sequence_length:
        raise HTTPException(400, f"序列总长 {total_length} 超过上限")

    stored = fasta_from_seqs(seqs)
    parent: Job | None = None
    if fold_job_id:
        parent = db.get(Job, fold_job_id)
        if not parent or parent.user_id != user_id:
            raise HTTPException(404, "折叠任务不存在")
        if parent.status != JobStatus.done.value or not is_fold_engine(parent.engine):
            raise HTTPException(400, "请选择已完成的折叠任务作为 MAXWELL 结构")
        structure_src = resolve_structure_path(parent)

    job = Job(
        user_id=user_id,
        name=name,
        engine=DEVELOPABILITY_ENGINE,
        status=JobStatus.queued.value,
        stage="queued",
        fasta_text=stored,
        sequence_hash=sequence_hash(seqs),
        chains_json=chains_json,
        total_length=total_length,
        use_msa_server=False,
        parent_job_id=parent.id if parent else None,
        params_json={
            **params,
            "model_path": str(settings.esm2_3b_path),
            "parent_id": name,
            "run_maxwell": bool(params.get("run_maxwell", True)),
            "maxwell_python": str(settings.maxwell_python),
            "maxwell_ckpt": str(settings.maxwell_ckpt),
            "fold_job_id": fold_job_id,
        },
    )
    db.add(job)
    db.flush()
    work_dir = job_output_dir(settings.developability_out_root, name, job.id, job.chains_json)
    work_dir.mkdir(parents=True, exist_ok=True)
    job.work_dir = str(work_dir)
    if structure_src:
        dest = _copy_structure(structure_src, work_dir)
        job.params_json = {**(job.params_json or {}), "structure_path": str(dest)}
        job.structure_path = str(dest)
    async_result = dispatch_to_gpu(run_developability_job, job.id)
    job.celery_task_id = async_result.id
    return job
