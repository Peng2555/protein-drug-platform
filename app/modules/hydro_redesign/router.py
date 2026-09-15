"""抗体疏水性改造 API。"""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.common.batch_common import batch_out
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.engines import HYDRO_REDESIGN_ENGINE
from app.modules.hydro_redesign.service import (
    HYDRO_BATCH_TYPE,
    create_and_queue_hydro_redesign_batch,
    create_and_queue_hydro_redesign_job,
    dispatch_hydro_redesign_jobs,
    parse_vhh_records,
    save_structure_upload,
)
from app.common.job_paths import remove_job_outputs
from app.models import Batch, Job, JobStatus, User
from app.schemas import (
    BatchDetailOut,
    BatchJobOut,
    BatchJobsListOut,
    BatchListOut,
    HydroRedesignBatchCreate,
    HydroRedesignBatchCreateOut,
    HydroRedesignJobCreate,
    HydroRedesignJobListOut,
    HydroRedesignJobOut,
    HydroRedesignProgressOut,
    HydroRedesignRankedOut,
)

from algorithm_paths import bootstrap_algorithm_paths

bootstrap_algorithm_paths()

from hydro_redesign.sequences import (  # noqa: E402
    ALL_MUTANT_FASTA,
    TOP20_MUTANT_FASTA,
    build_mutant_sequences_fasta,
    parse_fasta,
    select_top20_rows,
)

router = APIRouter(prefix="/api/hydro-redesign-jobs", tags=["hydro-redesign"])


def _out(job: Job) -> HydroRedesignJobOut:
    return HydroRedesignJobOut.model_validate(job)


def _job_or_404(db: Session, user_id: str, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if not job or job.user_id != user_id or job.engine != HYDRO_REDESIGN_ENGINE:
        raise HTTPException(404, "Hydro redesign job not found")
    return job


def _work(job: Job) -> Path:
    if not job.work_dir:
        raise HTTPException(404, "Job work_dir missing")
    return Path(job.work_dir)


def _exports(job: Job) -> Path:
    return _work(job) / "exports"


def _hydro_batch_or_404(db: Session, user_id: str, batch_id: str) -> Batch:
    batch = db.get(Batch, batch_id)
    if not batch or batch.user_id != user_id or batch.batch_type != HYDRO_BATCH_TYPE:
        raise HTTPException(404, "疏水改造批次不存在")
    return batch


def _read_csv_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load_wt_sequences(job: Job) -> dict[str, str]:
    fasta_path = _work(job) / "input" / "sequences.fasta"
    if fasta_path.is_file():
        return parse_fasta(fasta_path.read_text(encoding="utf-8"))
    params = job.params_json or {}
    text = params.get("fasta") or params.get("fasta_text") or ""
    if text:
        return parse_fasta(str(text))
    return {}


def _ensure_mutant_fasta(job: Job, filename: str) -> Path | None:
    """新任务已写出；旧任务按需从 mutations/wetlab + WT FASTA 生成。"""
    exports = _exports(job)
    exports.mkdir(parents=True, exist_ok=True)
    dest = exports / filename
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    seqs = _load_wt_sequences(job)
    if not seqs:
        return None
    mutations = _read_csv_rows(exports / "mutations.csv")
    wetlab = _read_csv_rows(exports / "wetlab.csv")
    if not mutations and job.results_json:
        mutations = list(job.results_json.get("mutations") or [])
        wetlab = list(job.results_json.get("wetlab") or [])
    if filename == ALL_MUTANT_FASTA:
        rows = mutations
    elif filename == TOP20_MUTANT_FASTA:
        rows = select_top20_rows(mutations, wetlab)
    else:
        return None
    if not rows:
        return None
    text = build_mutant_sequences_fasta(seqs, rows)
    dest.write_text(text, encoding="utf-8")
    return dest


@router.post("", response_model=HydroRedesignJobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    body: HydroRedesignJobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    name = body.name.strip() if body.name and body.name.strip() else "hydro_redesign"
    job = create_and_queue_hydro_redesign_job(
        db,
        user_id=user.id,
        name=name,
        fasta_text=body.fasta,
        allow_cdr=body.allow_cdr,
        allow_charged=body.allow_charged,
        defer_dispatch=True,
    )
    db.commit()
    dispatch_hydro_redesign_jobs([job])
    db.commit()
    db.refresh(job)
    return _out(job)


@router.post("/upload", response_model=HydroRedesignJobOut, status_code=status.HTTP_201_CREATED)
async def create_job_upload(
    fasta: str = Form(...),
    name: str | None = Form(default=None),
    allow_cdr: bool = Form(default=False),
    allow_charged: bool = Form(default=False),
    structure: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    structure_path: Path | None = None
    if structure and structure.filename:
        tmp = settings.hydro_redesign_out_root / "_uploads" / user.id
        suffix = Path(structure.filename).suffix.lower() or ".pdb"
        structure_path = await save_structure_upload(structure, tmp / f"structure{suffix}")
    job_name = name.strip() if name and name.strip() else "hydro_redesign"
    job = create_and_queue_hydro_redesign_job(
        db,
        user_id=user.id,
        name=job_name,
        fasta_text=fasta,
        structure_path=structure_path,
        allow_cdr=allow_cdr,
        allow_charged=allow_charged,
        defer_dispatch=True,
    )
    db.commit()
    dispatch_hydro_redesign_jobs([job])
    db.commit()
    db.refresh(job)
    return _out(job)


@router.post("/batches", response_model=HydroRedesignBatchCreateOut, status_code=status.HTTP_201_CREATED)
def create_batch(
    body: HydroRedesignBatchCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    parse_vhh_records(body.fasta)
    batch, jobs = create_and_queue_hydro_redesign_batch(
        db,
        user_id=user.id,
        name=body.name.strip() if body.name and body.name.strip() else "",
        fasta_text=body.fasta,
        allow_cdr=body.allow_cdr,
        allow_charged=body.allow_charged,
    )
    db.commit()
    dispatch_hydro_redesign_jobs(jobs)
    db.commit()
    db.refresh(batch)
    return HydroRedesignBatchCreateOut(batch=batch_out(batch, db), job_ids=[j.id for j in jobs])


@router.get("", response_model=HydroRedesignJobListOut)
def list_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    condition = (
        Job.user_id == user.id,
        Job.engine == HYDRO_REDESIGN_ENGINE,
        Job.batch_id.is_(None),
    )
    rows = db.scalars(
        select(Job).where(*condition).order_by(Job.created_at.desc()).limit(limit).offset(offset)
    ).all()
    total = db.scalar(select(func.count()).select_from(Job).where(*condition)) or 0
    return HydroRedesignJobListOut(items=[_out(j) for j in rows], total=total)


@router.get("/batches", response_model=BatchListOut)
def list_batches(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    condition = (Batch.user_id == user.id, Batch.batch_type == HYDRO_BATCH_TYPE)
    total = db.scalar(select(func.count()).select_from(Batch).where(*condition)) or 0
    rows = db.scalars(
        select(Batch).where(*condition).order_by(Batch.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return BatchListOut(items=[batch_out(b, db) for b in rows], total=total)


@router.get("/batches/{batch_id}", response_model=BatchDetailOut)
def get_batch(batch_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    batch = _hydro_batch_or_404(db, user.id, batch_id)
    out = batch_out(batch, db)
    return BatchDetailOut(**out.model_dump(), target_sequence=batch.target_sequence or "")


@router.get("/batches/{batch_id}/jobs", response_model=BatchJobsListOut)
def list_batch_jobs(
    batch_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    _hydro_batch_or_404(db, user.id, batch_id)
    q = select(Job).where(Job.batch_id == batch_id).order_by(Job.created_at.asc())
    total = db.scalar(select(func.count()).select_from(Job).where(Job.batch_id == batch_id)) or 0
    rows = db.scalars(q.limit(limit).offset(offset)).all()
    return BatchJobsListOut(
        items=[BatchJobOut.model_validate(j) for j in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/batches/{batch_id}/export.csv")
def export_batch_csv(batch_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _hydro_batch_or_404(db, user.id, batch_id)
    jobs = db.scalars(select(Job).where(Job.batch_id == batch_id).order_by(Job.created_at.asc())).all()
    buf = StringIO()
    cols = [
        "id",
        "name",
        "status",
        "n_patches",
        "n_surface_hydro",
        "n_mutable_sites",
        "n_mutations",
        "n_wetlab",
        "n_skipped_cdr",
        "allow_cdr",
        "allow_charged",
    ]
    writer = csv.DictWriter(buf, fieldnames=cols)
    writer.writeheader()
    for job in jobs:
        summary = ((job.results_json or {}).get("summary") or {}) if job.results_json else {}
        params = job.params_json or {}
        writer.writerow(
            {
                "id": job.heavy_chain_id or job.id,
                "name": job.name or "",
                "status": job.status,
                "n_patches": summary.get("n_patches", ""),
                "n_surface_hydro": summary.get("n_surface_hydro", ""),
                "n_mutable_sites": summary.get("n_mutable_sites", ""),
                "n_mutations": summary.get("n_mutations", ""),
                "n_wetlab": summary.get("n_wetlab", ""),
                "n_skipped_cdr": summary.get("n_skipped_cdr", ""),
                "allow_cdr": summary.get("allow_cdr", params.get("allow_cdr", "")),
                "allow_charged": summary.get("allow_charged", params.get("allow_charged", "")),
            }
        )
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="hydro_batch_{batch_id[:8]}.csv"'},
    )


@router.delete("/batches/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_batch(batch_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    batch = _hydro_batch_or_404(db, user.id, batch_id)
    jobs = db.scalars(select(Job).where(Job.batch_id == batch_id)).all()
    for job in jobs:
        if job.status in (JobStatus.queued.value, JobStatus.running.value) and job.celery_task_id:
            celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
        remove_job_outputs(
            settings.hydro_redesign_out_root,
            job.id,
            job.name,
            job.chains_json,
            job.work_dir,
        )
        db.delete(job)
    db.delete(batch)
    db.commit()


@router.get("/{job_id}", response_model=HydroRedesignJobOut)
def get_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _out(_job_or_404(db, user.id, job_id))


@router.get("/{job_id}/progress", response_model=HydroRedesignProgressOut)
def get_progress(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _job_or_404(db, user.id, job_id)
    stage = job.stage or "queued"
    summary = None
    if job.work_dir:
        wf = Path(job.work_dir) / "workflow_status.json"
        if wf.is_file():
            try:
                data = json.loads(wf.read_text(encoding="utf-8"))
                stage = str(data.get("stage") or stage)
                summary = data.get("summary")
            except json.JSONDecodeError:
                pass
    return HydroRedesignProgressOut(stage=stage, status=job.status, summary=summary)


@router.get("/{job_id}/ranked", response_model=HydroRedesignRankedOut)
def get_ranked(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _job_or_404(db, user.id, job_id)
    mutations: list[dict] = []
    wetlab: list[dict] = []
    patches: list[dict] = []
    residues: list[dict] = []
    summary = None
    if job.results_json:
        mutations = list(job.results_json.get("mutations") or [])
        wetlab = list(job.results_json.get("wetlab") or [])
        patches = list(job.results_json.get("patches") or [])
        summary = job.results_json.get("summary")
    exports = _exports(job)
    if (exports / "mutations.csv").is_file():
        mutations = _read_csv_rows(exports / "mutations.csv")
    if (exports / "wetlab.csv").is_file():
        wetlab = _read_csv_rows(exports / "wetlab.csv")
    if (exports / "patches.csv").is_file():
        patches = _read_csv_rows(exports / "patches.csv")
    res_csv = _work(job) / "patches" / "residue_sasa.csv"
    if res_csv.is_file():
        residues = _read_csv_rows(res_csv)
    if (exports / "summary.json").is_file() and summary is None:
        summary = json.loads((exports / "summary.json").read_text(encoding="utf-8"))
    return HydroRedesignRankedOut(
        mutations=mutations,
        wetlab=wetlab,
        patches=patches,
        residues=residues,
        summary=summary,
    )


@router.get("/{job_id}/files/{filename}")
def download_file(
    job_id: str,
    filename: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = _job_or_404(db, user.id, job_id)
    if Path(filename).name != filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")
    exports = _exports(job)
    path = exports / filename
    if filename in {ALL_MUTANT_FASTA, TOP20_MUTANT_FASTA}:
        generated = _ensure_mutant_fasta(job, filename)
        if generated is not None:
            path = generated
        elif not path.is_file():
            raise HTTPException(404, "突变序列尚未生成（缺少 WT FASTA 或突变表）")
    if not path.is_file():
        for alt_dir in (_work(job) / "patches", _work(job) / "fold", _work(job) / "input"):
            alt = alt_dir / filename
            if alt.is_file():
                path = alt
                break
    if not path.is_file():
        raise HTTPException(404, "File not found")
    media = "chemical/x-cif" if path.suffix.lower() == ".cif" else "application/octet-stream"
    if path.suffix.lower() == ".csv":
        media = "text/csv; charset=utf-8"
    if path.suffix.lower() == ".json":
        media = "application/json"
    if path.suffix.lower() == ".fasta":
        media = "text/x-fasta; charset=utf-8"
    return FileResponse(path, filename=filename, media_type=media)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _job_or_404(db, user.id, job_id)
    if job.status in (JobStatus.queued.value, JobStatus.running.value) and job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
    db.delete(job)
    db.commit()
