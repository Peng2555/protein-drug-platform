"""Generic receptor/ligand docking API."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.database import get_db
from app.deps import get_current_user
from app.engines import SMALL_MOLECULE_DOCKING_ENGINE
from app.models import Job, JobStatus, User
from app.schemas import DockingJobListOut, DockingJobOut
from app.docking_service import create_and_queue_docking_job
from docking_runner import _pose_scores

router = APIRouter(prefix="/api/docking-jobs", tags=["docking"])


def _with_live_results(job: Job) -> DockingJobOut:
    payload = dict(job.results_json or {})
    work_dir = Path(job.work_dir) if job.work_dir else None
    if work_dir and work_dir.is_dir():
        payload["output_files"] = sorted(p.name for p in work_dir.iterdir() if p.is_file())
        if (work_dir / "docked_complex.pdb").is_file():
            payload["complex_pdb"] = str(work_dir / "docked_complex.pdb")
        if (work_dir / "docked_complex.pdbqt").is_file():
            payload["complex_pdbqt"] = str(work_dir / "docked_complex.pdbqt")
        summary = work_dir / "summary.json"
        if summary.is_file():
            try:
                saved = json.loads(summary.read_text(encoding="utf-8"))
                if isinstance(saved, dict):
                    if saved.get("poses"):
                        payload["poses"] = saved["poses"]
                    if saved.get("sampling"):
                        payload["sampling"] = saved["sampling"]
                    if saved.get("canonical_smiles"):
                        payload["canonical_smiles"] = saved["canonical_smiles"]
            except json.JSONDecodeError:
                pass
        output = work_dir / "docked_poses.pdbqt"
        if not payload.get("poses") and output.is_file():
            payload["poses"] = _pose_scores(output)
    data = DockingJobOut.model_validate(job)
    data.results_json = payload or None
    return data


def _float(value: str, label: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise HTTPException(400, f"{label}必须是数字") from exc


@router.post("", response_model=DockingJobOut, status_code=status.HTTP_201_CREATED)
async def create_job(
    receptor: UploadFile = File(...),
    ligand_smiles: str = Form(...),
    reference_ligand: UploadFile | None = File(default=None),
    name: str | None = Form(default=None),
    engine: str = Form(default="vina"),
    center_x: str = Form(...),
    center_y: str = Form(...),
    center_z: str = Form(...),
    size_x: str = Form(...),
    size_y: str = Form(...),
    size_z: str = Form(...),
    exhaustiveness: int = Form(default=8, ge=1, le=64),
    num_modes: int = Form(default=20, ge=1, le=50),
    energy_range: float = Form(default=5.0, ge=0, le=20),
    box_padding: float = Form(default=5.0, gt=0, le=20),
    n_starts: int = Form(default=10, ge=1, le=10),
    n_conformers: int = Form(default=128, ge=8, le=256),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if engine not in {"vina", "gnina"}:
        raise HTTPException(400, "engine 只能是 vina 或 gnina")
    params = {
        "engine": engine,
        "center_x": _float(center_x, "center_x"),
        "center_y": _float(center_y, "center_y"),
        "center_z": _float(center_z, "center_z"),
        "size_x": _float(size_x, "size_x"),
        "size_y": _float(size_y, "size_y"),
        "size_z": _float(size_z, "size_z"),
        "exhaustiveness": exhaustiveness,
        "num_modes": num_modes,
        "energy_range": energy_range,
        "box_padding": box_padding,
        "n_starts": n_starts,
        "n_conformers": n_conformers,
        "local_only": False,
        "cpu_per_job": 4,
    }
    if any(params[key] <= 0 for key in ("size_x", "size_y", "size_z")):
        raise HTTPException(400, "对接盒尺寸必须大于 0")
    if reference_ligand is None and all(params[key] == 0 for key in ("center_x", "center_y", "center_z")):
        raise HTTPException(400, "请填写真实搜索盒中心，或上传参考配体自动计算搜索盒")
    job_name = name.strip() if name and name.strip() else "docking"
    job = await create_and_queue_docking_job(
        db, user_id=user.id, name=job_name, receptor=receptor,
        ligand_smiles=ligand_smiles, reference_ligand=reference_ligand, params=params,
    )
    db.commit()
    db.refresh(job)
    return _with_live_results(job)


@router.get("", response_model=DockingJobListOut)
def list_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    condition = (Job.user_id == user.id, Job.engine == SMALL_MOLECULE_DOCKING_ENGINE)
    rows = db.scalars(select(Job).where(*condition).order_by(Job.created_at.desc()).limit(limit).offset(offset)).all()
    total = db.scalar(select(func.count()).select_from(Job).where(*condition)) or 0
    return DockingJobListOut(items=[DockingJobOut.model_validate(j) for j in rows], total=total)


@router.get("/{job_id}/files/{filename}")
def download_file(
    job_id: str,
    filename: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != SMALL_MOLECULE_DOCKING_ENGINE:
        raise HTTPException(404, "Docking job not found")
    if not job.work_dir or Path(filename).name != filename:
        raise HTTPException(400, "Invalid output filename")
    path = Path(job.work_dir) / filename
    if not path.is_file() or path.parent.resolve() != Path(job.work_dir).resolve():
        raise HTTPException(404, "Docking output file not found")
    return FileResponse(path, filename=filename, media_type="application/octet-stream")


@router.get("/{job_id}", response_model=DockingJobOut)
def get_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != SMALL_MOLECULE_DOCKING_ENGINE:
        raise HTTPException(404, "Docking job not found")
    return _with_live_results(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != SMALL_MOLECULE_DOCKING_ENGINE:
        raise HTTPException(404, "Docking job not found")
    if job.status in (JobStatus.queued.value, JobStatus.running.value) and job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
    db.delete(job)
    db.commit()
