"""IgGM affinity maturation job API."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.engines import MATURATION_ENGINE
from app.job_paths import remove_job_outputs
from app.maturation_service import (
    create_and_queue_maturation_job,
    prepare_maturation_from_body,
    save_uploaded_structure,
)
from app.models import Job, JobStatus, User
from app.schemas import (
    IgGMParams,
    MaturationJobCreate,
    MaturationJobListOut,
    MaturationJobOut,
    MaturationVariantOut,
    MaturationVariantsOut,
)

router = APIRouter(prefix="/api/maturation-jobs", tags=["maturation"])


def _out(job: Job) -> MaturationJobOut:
    return MaturationJobOut.model_validate(job)


@router.post("", response_model=MaturationJobOut, status_code=status.HTTP_201_CREATED)
def create_maturation_job(
    body: MaturationJobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if body.structure_source == "upload":
        raise HTTPException(400, "Use POST /api/maturation-jobs/upload for structure upload mode")

    fasta_text, chains_json, params, structure_path = prepare_maturation_from_body(db, user.id, body)
    name = body.name.strip() if body.name and body.name.strip() else f"maturation_{chains_json.get(body.binder_chain_id, 0)}"

    job = create_and_queue_maturation_job(
        db,
        user_id=user.id,
        name=name,
        fasta_text=fasta_text,
        chains_json=chains_json,
        params_json=params,
        structure_path=structure_path,
        fold_job_id=body.fold_job_id,
    )
    db.commit()
    db.refresh(job)
    return _out(job)


@router.post("/upload", response_model=MaturationJobOut, status_code=status.HTTP_201_CREATED)
async def create_maturation_upload(
    fasta: str = Form(...),
    structure: UploadFile = File(...),
    name: str | None = Form(default=None),
    binder_chain_id: str = Form(default="H"),
    antigen_chain_id: str = Form(default="A"),
    cdr_mask: str = Form(default="CDR-H3"),
    num_samples: int = Form(default=100),
    steps: int = Form(default=10),
    max_antigen_size: int = Form(default=384),
    temperature: float = Form(default=1.0),
    chunk_size: int = Form(default=64),
    relax: bool = Form(default=False),
    gpu_count: int = Form(default=2),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cdr_list = [x.strip() for x in cdr_mask.split(",") if x.strip()]
    body = MaturationJobCreate(
        fasta=fasta,
        name=name,
        structure_source="upload",
        binder_chain_id=binder_chain_id,
        antigen_chain_id=antigen_chain_id,
        cdr_mask=cdr_list or ["CDR-H3"],
        iggm=IgGMParams(
            num_samples=num_samples,
            steps=steps,
            max_antigen_size=max_antigen_size,
            temperature=temperature,
            chunk_size=chunk_size,
            relax=relax,
            gpu_count=gpu_count,
        ),
    )
    tmp_dir = settings.maturation_out_root / "_uploads" / user.id
    struct_path = await save_uploaded_structure(structure, tmp_dir)
    fasta_text, chains_json, params, _ = prepare_maturation_from_body(
        db, user.id, body, uploaded_structure=struct_path
    )
    job_name = name.strip() if name and name.strip() else f"maturation_{struct_path.stem}"

    job = create_and_queue_maturation_job(
        db,
        user_id=user.id,
        name=job_name,
        fasta_text=fasta_text,
        chains_json=chains_json,
        params_json=params,
        structure_path=struct_path,
    )
    db.commit()
    db.refresh(job)
    return _out(job)


@router.get("", response_model=MaturationJobListOut)
def list_maturation_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    q = select(Job).where(Job.user_id == user.id, Job.engine == MATURATION_ENGINE)
    count_q = (
        select(func.count())
        .select_from(Job)
        .where(Job.user_id == user.id, Job.engine == MATURATION_ENGINE)
    )
    total = db.scalar(count_q) or 0
    rows = db.scalars(q.order_by(Job.created_at.desc()).limit(limit).offset(offset)).all()
    return MaturationJobListOut(items=[_out(j) for j in rows], total=total)


@router.get("/{job_id}", response_model=MaturationJobOut)
def get_maturation_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != MATURATION_ENGINE:
        raise HTTPException(404, "Maturation job not found")
    return _out(job)


@router.get("/{job_id}/variants", response_model=MaturationVariantsOut)
def list_variants(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    min_frequency: int = Query(0, ge=0),
):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != MATURATION_ENGINE:
        raise HTTPException(404, "Maturation job not found")

    csv_path: Path | None = None
    if job.results_json and job.results_json.get("dedup_csv"):
        csv_path = Path(job.results_json["dedup_csv"])
    elif job.work_dir:
        for candidate in Path(job.work_dir).rglob("dedup_diff_freq.csv"):
            csv_path = candidate
            break

    if not csv_path or not csv_path.is_file():
        raise HTTPException(404, "Variant results not ready")

    rows: list[dict] = []
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        for row in reader:
            freq = int(float(row.get("Frequency", 0) or 0))
            if freq < min_frequency:
                continue
            rows.append(row)

    total = len(rows)
    page = rows[offset : offset + limit]
    items = []
    for row in page:
        items.append(
            MaturationVariantOut(
                method=row.get("Method"),
                antibody_seq_h=row.get("antibody_seq_h") or row.get("antibody_seq_h"),
                frequency=int(float(row.get("Frequency", 0) or 0)) if row.get("Frequency") else None,
                diff=row.get("diff") or row.get("Diff"),
                mutations=row.get("mutations") or row.get("Mutations"),
                extra={k: v for k, v in row.items() if k not in {"Method", "antibody_seq_h", "Frequency", "diff", "Mutations"}},
            )
        )
    return MaturationVariantsOut(items=items, total=total, columns=columns)


@router.get("/{job_id}/variants.csv")
def download_variants_csv(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != MATURATION_ENGINE:
        raise HTTPException(404, "Maturation job not found")
    csv_path = None
    if job.results_json:
        csv_path = job.results_json.get("dedup_csv")
    if not csv_path and job.work_dir:
        for candidate in Path(job.work_dir).rglob("dedup_diff_freq.csv"):
            csv_path = str(candidate)
            break
    if not csv_path or not Path(csv_path).is_file():
        raise HTTPException(404, "Variant CSV not found")
    return FileResponse(
        Path(csv_path),
        filename=f"{job.name or job.id}_variants.csv",
        media_type="text/csv",
    )


@router.get("/{job_id}/structure")
def download_complex_structure(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != MATURATION_ENGINE:
        raise HTTPException(404, "Maturation job not found")
    pdb = None
    if job.results_json and job.results_json.get("complex_pdb"):
        pdb = Path(job.results_json["complex_pdb"])
    elif job.work_dir:
        candidate = Path(job.work_dir) / "input" / "complex.pdb"
        if candidate.is_file():
            pdb = candidate
    if not pdb or not pdb.is_file():
        raise HTTPException(404, "Complex structure not found")
    return FileResponse(pdb, filename=f"{job.name or job.id}_complex.pdb", media_type="chemical/x-pdb")


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_maturation_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != MATURATION_ENGINE:
        raise HTTPException(404, "Maturation job not found")

    if job.status in (JobStatus.queued.value, JobStatus.running.value):
        job.status = JobStatus.cancelled.value
        db.commit()
        if job.celery_task_id:
            celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")

    remove_job_outputs(
        settings.maturation_out_root,
        job.id,
        job.name,
        job.chains_json,
        job.work_dir,
    )
    db.delete(job)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
