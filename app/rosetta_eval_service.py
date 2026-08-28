"""Rosetta antibody–antigen structural evaluation jobs."""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.engines import ROSETTA_EVAL_ENGINE, is_fold_engine
from app.job_paths import job_output_dir
from app.md_service import resolve_structure_path
from app.models import Job, JobStatus
from app.queue_service import dispatch_to_gpu
from worker.tasks import run_rosetta_eval_job

ALLOWED = {".pdb", ".cif", ".mmcif"}


def _copy_structure(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    suffix = src.suffix.lower() or ".pdb"
    if suffix == ".mmcif":
        suffix = ".cif"
        dest = dest.with_suffix(".cif")
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    return dest


async def save_upload(upload: UploadFile, dest: Path) -> Path:
    suffix = Path(upload.filename or "input.pdb").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(400, "结构文件需为 .pdb / .cif")
    if suffix == ".mmcif":
        suffix = ".cif"
        dest = dest.with_suffix(".cif")
    content = await upload.read()
    if len(content) < 80:
        raise HTTPException(400, f"{upload.filename or dest.name} 太小或为空")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return dest


def _fold_variant(db: Session, user_id: str, job_id: str, *, is_wt: bool) -> dict:
    parent = db.get(Job, job_id)
    if not parent or parent.user_id != user_id:
        raise HTTPException(404, f"折叠任务不存在: {job_id}")
    if parent.status != JobStatus.done.value or not is_fold_engine(parent.engine):
        raise HTTPException(400, f"请选择已完成的结构预测任务: {job_id}")
    src = resolve_structure_path(parent)
    conf = parent.confidence_score
    if conf is None and parent.iptm is not None and parent.ptm is not None:
        conf = 0.8 * float(parent.iptm) + 0.2 * float(parent.ptm)
    elif conf is None:
        conf = parent.iptm
    return {
        "name": parent.name or parent.id[:8],
        "path": str(src),
        "is_wt": is_wt,
        "fold_job_id": parent.id,
        "confidence": conf,
        "iptm": parent.iptm,
        "ptm": parent.ptm,
        "complex_plddt": parent.complex_plddt,
    }


def create_and_queue_rosetta_eval_job(
    db: Session,
    *,
    user_id: str,
    name: str,
    params: dict,
    variants: list[dict],
    parent_job_id: str | None = None,
) -> Job:
    if not variants:
        raise HTTPException(400, "请提供 WT 与至少一个突变体结构")
    if not any(v.get("is_wt") for v in variants):
        variants[0]["is_wt"] = True
    if len(variants) < 2:
        raise HTTPException(400, "至少需要 WT + 1 个突变体才能计算 ΔΔG")
    if len(variants) > 100:
        raise HTTPException(400, "单次最多评价 100 个结构（含 WT）")
    try:
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from rosetta_eval_runner import resolve_eval_backend

        resolve_eval_backend(settings.rosetta_bin_dir or None, settings.pyrosetta_python or None)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc

    job = Job(
        user_id=user_id,
        name=name,
        engine=ROSETTA_EVAL_ENGINE,
        status=JobStatus.queued.value,
        stage="queued",
        fasta_text=">rosetta_eval\n.",
        sequence_hash=hashlib.sha256(
            "|".join(str(v.get("path") or "") for v in variants).encode()
        ).hexdigest(),
        chains_json={"complex": len(variants)},
        total_length=len(variants),
        use_msa_server=False,
        parent_job_id=parent_job_id,
        params_json=params,
    )
    db.add(job)
    db.flush()
    work_dir = job_output_dir(settings.rosetta_eval_out_root, name, job.id, job.chains_json)
    input_dir = work_dir / "00_input"
    input_dir.mkdir(parents=True, exist_ok=True)
    stored: list[dict] = []
    for item in variants:
        src = Path(item["path"])
        label = re_label(str(item.get("name") or src.stem), item.get("is_wt"))
        dest = _copy_structure(src, input_dir / f"{label}{src.suffix.lower() or '.pdb'}")
        stored.append({**item, "name": label, "path": str(dest)})
    job.work_dir = str(work_dir)
    job.params_json = {
        **params,
        "variants": stored,
        "rosetta_bin_dir": str(settings.rosetta_bin_dir) if settings.rosetta_bin_dir else None,
        "pyrosetta_python": settings.pyrosetta_python or None,
        "score_weights": "ref2015",
        "n_jobs": max(1, min(64, int(params.get("n_jobs") or settings.rosetta_n_jobs or 16))),
    }
    async_result = dispatch_to_gpu(run_rosetta_eval_job, job.id)
    job.celery_task_id = async_result.id
    return job


def re_label(name: str, is_wt: bool | None) -> str:
    s = re.sub(r"[^\w\-]+", "_", name.strip())
    s = re.sub(r"_+", "_", s).strip("_") or "variant"
    if is_wt and not s.upper().startswith("WT"):
        return f"WT_{s}"[:48]
    return s[:48]
