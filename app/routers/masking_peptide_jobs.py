"""Masking peptide design workflow API."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.engines import MASKING_PEPTIDE_ENGINE
from app.masking_peptide_service import (
    create_and_queue_masking_peptide_job,
    prepare_from_body,
    save_structure_upload,
)
from app.models import Job, JobStatus, User
from app.schemas import (
    MaskingPeptideJobCreate,
    MaskingPeptideJobListOut,
    MaskingPeptideJobOut,
    MaskingPeptideSequencesOut,
)

router = APIRouter(prefix="/api/masking-peptide-jobs", tags=["masking-peptide"])


def _out(job: Job) -> MaskingPeptideJobOut:
    return MaskingPeptideJobOut.model_validate(job)


def _job_or_404(db: Session, user_id: str, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if not job or job.user_id != user_id or job.engine != MASKING_PEPTIDE_ENGINE:
        raise HTTPException(404, "Masking peptide job not found")
    return job


def _exports_dir(job: Job) -> Path:
    if not job.work_dir:
        raise HTTPException(404, "Job work_dir missing")
    return Path(job.work_dir) / "exports"


@router.post("", response_model=MaskingPeptideJobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    body: MaskingPeptideJobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not body.fold_job_id:
        raise HTTPException(400, "请使用 /upload 上传抗体 PDB，或提供 fold_job_id")
    ab_path, params, parent_id, extracted_tmp = prepare_from_body(db, user.id, body)
    job = create_and_queue_masking_peptide_job(
        db,
        user_id=user.id,
        name=body.name.strip() if body.name else "masking_peptide",
        antibody_pdb=ab_path,
        params=params,
        parent_job_id=parent_id,
        extracted_tmp=extracted_tmp,
    )
    db.commit()
    db.refresh(job)
    return _out(job)


@router.post("/upload", response_model=MaskingPeptideJobOut, status_code=status.HTTP_201_CREATED)
async def create_job_upload(
    antibody_pdb: UploadFile = File(...),
    name: str | None = Form(default=None),
    fold_job_id: str | None = Form(default=None),
    hotspot_res: str = Form(default="H35,H47,H50,H104,H110"),
    target_chain: str = Form(default="H"),
    peptide_length: str = Form(default="12-18"),
    total_designs: int = Form(default=200),
    mpnn_rounds: int = Form(default=4),
    skip_backbone: bool = Form(default=False),
    relax_jobs: int = Form(default=8),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tmp = settings.masking_peptide_out_root / "_uploads" / user.id
    suffix = Path(antibody_pdb.filename or ".pdb").suffix.lower() or ".pdb"
    upload_path = await save_structure_upload(antibody_pdb, tmp / f"antibody{suffix}")

    body = MaskingPeptideJobCreate(
        name=name,
        fold_job_id=fold_job_id,
        hotspot_res=[h.strip() for h in hotspot_res.split(",") if h.strip()],
        target_chain=target_chain,
        peptide_length=peptide_length,
        total_designs=max(10, min(20000, total_designs)),
        mpnn_rounds=max(1, min(8, mpnn_rounds)),
        skip_backbone=skip_backbone,
        relax_jobs=max(1, min(32, relax_jobs)),
    )
    ab_path, params, parent_id, extracted_tmp = prepare_from_body(
        db, user.id, body, antibody_upload=upload_path
    )
    job = create_and_queue_masking_peptide_job(
        db,
        user_id=user.id,
        name=body.name.strip() if body.name else "masking_peptide",
        antibody_pdb=ab_path,
        params=params,
        parent_job_id=parent_id,
        extracted_tmp=extracted_tmp,
    )
    db.commit()
    db.refresh(job)
    return _out(job)


@router.get("", response_model=MaskingPeptideJobListOut)
def list_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    condition = (Job.user_id == user.id, Job.engine == MASKING_PEPTIDE_ENGINE)
    rows = db.scalars(
        select(Job).where(*condition).order_by(Job.created_at.desc()).limit(limit).offset(offset)
    ).all()
    total = db.scalar(select(func.count()).select_from(Job).where(*condition)) or 0
    return MaskingPeptideJobListOut(items=[_out(j) for j in rows], total=total)


@router.get("/{job_id}", response_model=MaskingPeptideJobOut)
def get_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _out(_job_or_404(db, user.id, job_id))


@router.get("/{job_id}/sequences", response_model=MaskingPeptideSequencesOut)
def get_sequences(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _job_or_404(db, user.id, job_id)
    sequences: list[dict] = []
    summary = None
    if job.results_json:
        sequences = job.results_json.get("sequences") or []
        summary = job.results_json.get("summary")
    if not sequences:
        csv_path = _exports_dir(job) / "sequences_final.csv"
        if not csv_path.is_file() and job.work_dir:
            rounds = int((job.params_json or {}).get("mpnn_rounds") or 4)
            alt = Path(job.work_dir) / "05_mpnn" / f"round{rounds}" / "sequences.csv"
            if alt.is_file():
                csv_path = alt
        if csv_path.is_file():
            with csv_path.open(newline="", encoding="utf-8") as f:
                sequences = list(csv.DictReader(f))
        summary_path = _exports_dir(job) / "summary.json"
        if summary_path.is_file() and summary is None:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return MaskingPeptideSequencesOut(sequences=sequences, summary=summary)


@router.get("/{job_id}/files/{filename}")
def download_file(
    job_id: str,
    filename: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = _job_or_404(db, user.id, job_id)
    if filename == "structures.zip":
        struct_dir = _exports_dir(job) / "structures"
        if not struct_dir.is_dir():
            rounds = int((job.params_json or {}).get("mpnn_rounds") or 4)
            struct_dir = Path(job.work_dir or "") / "05_mpnn" / f"round{rounds}" / "merged"
        if not struct_dir.is_dir():
            raise HTTPException(404, "structures/ 不存在")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for pdb in sorted(struct_dir.glob("*.pdb")):
                zf.write(pdb, pdb.name)
        if not buf.tell():
            raise HTTPException(404, "structures/ 为空")
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="structures.zip"'},
        )
    if Path(filename).name != filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")
    path = _exports_dir(job) / filename
    if not path.is_file():
        raise HTTPException(404, "Export file not found")
    return FileResponse(path, filename=filename, media_type="application/octet-stream")


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _job_or_404(db, user.id, job_id)
    if job.status in (JobStatus.queued.value, JobStatus.running.value) and job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
    db.delete(job)
    db.commit()
