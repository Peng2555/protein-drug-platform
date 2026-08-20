"""ProteinMPNN sequence design job service."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.engines import DESIGN_ENGINE, is_fold_engine
from app.job_paths import job_output_dir
from app.md_service import resolve_structure_path
from app.models import Job, JobStatus
from app.queue_service import dispatch_to_gpu
from worker.tasks import run_design_job

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def _copy_structure(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = src.suffix.lower() or ".pdb"
    if suffix == ".mmcif":
        suffix = ".cif"
    dest = dest_dir / f"structure{suffix}"
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    return dest


async def save_uploaded_structure(upload: UploadFile, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or "input.pdb").suffix.lower()
    if suffix not in {".cif", ".mmcif", ".pdb"}:
        raise HTTPException(400, "ProteinMPNN 需要 .pdb 或 .cif 结构文件")
    if suffix == ".mmcif":
        suffix = ".cif"
    dest = dest_dir / f"structure{suffix}"
    content = await upload.read()
    if len(content) < 80:
        raise HTTPException(400, "结构文件太小或为空")
    dest.write_bytes(content)
    return dest


def create_and_queue_design_job(
    db: Session,
    *,
    user_id: str,
    name: str,
    params: dict,
    structure_src: Path | None = None,
    fold_job_id: str | None = None,
) -> Job:
    parent: Job | None = None
    if fold_job_id:
        parent = db.get(Job, fold_job_id)
        if not parent or parent.user_id != user_id:
            raise HTTPException(404, "折叠任务不存在")
        if parent.status != JobStatus.done.value or not is_fold_engine(parent.engine):
            raise HTTPException(400, "请选择已完成的结构预测任务")
        structure_src = resolve_structure_path(parent)

    if not structure_src or not Path(structure_src).is_file():
        raise HTTPException(400, "请上传结构文件或选择已完成的折叠任务")

    chains_json = dict(parent.chains_json) if parent and parent.chains_json else {"X": 0}
    total_length = int(parent.total_length) if parent and parent.total_length else 0

    job = Job(
        user_id=user_id,
        name=name,
        engine=DESIGN_ENGINE,
        status=JobStatus.queued.value,
        stage="queued",
        fasta_text=parent.fasta_text if parent else "",
        sequence_hash=parent.sequence_hash if parent else None,
        chains_json=chains_json,
        total_length=total_length,
        use_msa_server=False,
        parent_job_id=parent.id if parent else None,
        params_json={
            **params,
            "fold_job_id": fold_job_id,
            "proteinmpnn_python": settings.proteinmpnn_python,
            "proteinmpnn_script": str(settings.proteinmpnn_script),
            "proteinmpnn_weights_dir": str(settings.proteinmpnn_weights_dir),
            "proteinmpnn_model_name": settings.proteinmpnn_model_name,
            "gemmi_py": settings.gemmi_py,
        },
    )
    db.add(job)
    db.flush()
    work_dir = job_output_dir(settings.design_out_root, name, job.id, job.chains_json)
    work_dir.mkdir(parents=True, exist_ok=True)
    job.work_dir = str(work_dir)
    dest = _copy_structure(Path(structure_src), work_dir)
    job.structure_path = str(dest)
    job.params_json = {**(job.params_json or {}), "structure_path": str(dest)}
    async_result = dispatch_to_gpu(run_design_job, job.id)
    job.celery_task_id = async_result.id
    return job
