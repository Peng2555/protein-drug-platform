"""Affinity redesign workflow API."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.affinity_redesign_service import create_and_queue_affinity_redesign_job, save_structure_upload
from app.affinity_redesign_progress import collect_affinity_redesign_progress
from app.celery_app import celery_app
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.engines import AFFINITY_REDESIGN_ENGINE
from app.models import Job, JobStatus, User
from app.schemas import (
    AffinityRedesignJobCreate,
    AffinityRedesignJobListOut,
    AffinityRedesignJobOut,
    AffinityRedesignProgressOut,
    AffinityRedesignRankedOut,
)

router = APIRouter(prefix="/api/affinity-redesign-jobs", tags=["affinity-redesign"])


def _out(job: Job) -> AffinityRedesignJobOut:
    return AffinityRedesignJobOut.model_validate(job)


def _job_or_404(db: Session, user_id: str, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if not job or job.user_id != user_id or job.engine != AFFINITY_REDESIGN_ENGINE:
        raise HTTPException(404, "Affinity redesign job not found")
    return job


def _exports_dir(job: Job) -> Path:
    if not job.work_dir:
        raise HTTPException(404, "Job work_dir missing")
    return Path(job.work_dir) / "exports"


def _safe_export_path(job: Job, filename: str) -> Path:
    if Path(filename).name != filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")
    path = _exports_dir(job) / filename
    if not path.is_file():
        raise HTTPException(404, "Export file not found")
    if path.resolve().parent != _exports_dir(job).resolve():
        raise HTTPException(400, "Invalid path")
    return path


@router.post("", response_model=AffinityRedesignJobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    body: AffinityRedesignJobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    name = body.name.strip() if body.name and body.name.strip() else "affinity_redesign"
    job = create_and_queue_affinity_redesign_job(
        db,
        user_id=user.id,
        name=name,
        fasta_text=body.fasta,
        complex_path=None,
        skip_round1=body.skip_round1,
    )
    db.commit()
    db.refresh(job)
    return _out(job)


@router.post("/upload", response_model=AffinityRedesignJobOut, status_code=status.HTTP_201_CREATED)
async def create_job_upload(
    fasta: str = Form(...),
    name: str | None = Form(default=None),
    skip_round1: bool = Form(default=False),
    complex_pdb: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    complex_path: Path | None = None
    if complex_pdb and complex_pdb.filename:
        tmp = settings.affinity_redesign_out_root / "_uploads" / user.id
        suffix = Path(complex_pdb.filename).suffix.lower() or ".pdb"
        complex_path = await save_structure_upload(complex_pdb, tmp / f"complex{suffix}")

    job_name = name.strip() if name and name.strip() else "affinity_redesign"
    job = create_and_queue_affinity_redesign_job(
        db,
        user_id=user.id,
        name=job_name,
        fasta_text=fasta,
        complex_path=complex_path,
        skip_round1=skip_round1,
    )
    db.commit()
    db.refresh(job)
    return _out(job)


@router.get("", response_model=AffinityRedesignJobListOut)
def list_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    condition = (Job.user_id == user.id, Job.engine == AFFINITY_REDESIGN_ENGINE)
    rows = db.scalars(
        select(Job).where(*condition).order_by(Job.created_at.desc()).limit(limit).offset(offset)
    ).all()
    total = db.scalar(select(func.count()).select_from(Job).where(*condition)) or 0
    return AffinityRedesignJobListOut(items=[_out(j) for j in rows], total=total)


@router.get("/{job_id}", response_model=AffinityRedesignJobOut)
def get_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _out(_job_or_404(db, user.id, job_id))


@router.get("/{job_id}/progress", response_model=AffinityRedesignProgressOut)
def get_progress(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tail_lines: int = Query(250, ge=50, le=800),
):
    job = _job_or_404(db, user.id, job_id)
    return AffinityRedesignProgressOut(**collect_affinity_redesign_progress(job, tail_lines=tail_lines))


@router.get("/{job_id}/ranked", response_model=AffinityRedesignRankedOut)
def get_ranked(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _job_or_404(db, user.id, job_id)
    ranked = []
    wetlab = []
    summary = None
    if job.results_json:
        ranked = job.results_json.get("ranked") or []
        wetlab = job.results_json.get("wetlab") or []
        summary = job.results_json.get("summary")
    if not ranked:
        ranked_path = _exports_dir(job) / "ranked_mutations.csv"
        if ranked_path.is_file():
            import csv

            with ranked_path.open(newline="", encoding="utf-8") as f:
                ranked = list(csv.DictReader(f))
        wetlab_path = _exports_dir(job) / "wetlab_candidates.csv"
        if wetlab_path.is_file() and not wetlab:
            import csv

            with wetlab_path.open(newline="", encoding="utf-8") as f:
                wetlab = list(csv.DictReader(f))
        summary_path = _exports_dir(job) / "summary.json"
        if summary_path.is_file() and summary is None:
            import json

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return AffinityRedesignRankedOut(ranked=ranked, wetlab=wetlab, summary=summary)


def _ensure_sequences_fasta(job: Job) -> Path:
    from affinity_redesign.common.fasta import parse_fasta_file
    from affinity_redesign.pipeline.rescore import SEQUENCES_FASTA_NAME, build_wt_mutant_fasta

    exports = _exports_dir(job)
    path = exports / SEQUENCES_FASTA_NAME
    if path.is_file() and path.stat().st_size > 0:
        return path
    fasta_in = Path(job.work_dir) / "input" / "sequences.fasta"
    if not fasta_in.is_file():
        raise HTTPException(404, "缺少 input/sequences.fasta，无法导出突变序列")
    seqs = parse_fasta_file(fasta_in)
    ranked: list[dict] = []
    ranked_path = exports / "ranked_mutations.csv"
    if ranked_path.is_file():
        import csv

        with ranked_path.open(newline="", encoding="utf-8") as f:
            ranked = list(csv.DictReader(f))
    if not ranked and job.results_json:
        ranked = list(job.results_json.get("ranked") or [])
    antigen = None
    yaml_path = Path(job.work_dir) / "campaign.yaml"
    if yaml_path.is_file():
        try:
            from affinity_redesign.schemas import CampaignConfig

            antigen = CampaignConfig.from_yaml(yaml_path).chains.antigen
        except Exception:
            antigen = None
    exports.mkdir(parents=True, exist_ok=True)
    path.write_text(build_wt_mutant_fasta(seqs, ranked, antigen_chain=antigen), encoding="utf-8")
    return path


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
            raise HTTPException(404, "structures/ 不存在")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for pdb in sorted(struct_dir.glob("*.pdb")):
                zf.write(pdb, pdb.name)
            for cif in sorted(struct_dir.glob("*.cif")):
                zf.write(cif, cif.name)
        if not buf.tell():
            raise HTTPException(404, "structures/ 为空")
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="structures.zip"'},
        )
    if filename == "sequences_wt_mutants.fasta":
        path = _ensure_sequences_fasta(job)
        return FileResponse(path, filename=filename, media_type="text/plain; charset=utf-8")
    path = _safe_export_path(job, filename)
    return FileResponse(path, filename=filename, media_type="application/octet-stream")


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _job_or_404(db, user.id, job_id)
    if job.status in (JobStatus.queued.value, JobStatus.running.value) and job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
    db.delete(job)
    db.commit()
