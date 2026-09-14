"""VHH 可开发性画像 API。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.engines import TNP_PROFILE_ENGINE
from app.job_paths import remove_job_outputs
from app.tnp_profile_service import (
    TNP_BATCH_TYPE,
    create_and_queue_tnp_profile_batch,
    create_and_queue_tnp_profile_job,
    dispatch_tnp_profile_jobs,
    parse_vhh_records,
    save_structure_upload,
)
from app.models import Batch, Job, JobStatus, User
from app.schemas import (
    BatchDetailOut,
    BatchJobOut,
    BatchJobsListOut,
    BatchListOut,
    BatchOut,
    TnpProfileBatchCreate,
    TnpProfileBatchCreateOut,
    TnpProfileJobCreate,
    TnpProfileJobListOut,
    TnpProfileJobOut,
    TnpProfileProgressOut,
    TnpProfileRankedOut,
)

router = APIRouter(prefix="/api/tnp-profile-jobs", tags=["tnp-profile"])


def _out(job: Job) -> TnpProfileJobOut:
    return TnpProfileJobOut.model_validate(job)


def _job_or_404(db: Session, user_id: str, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if not job or job.user_id != user_id or job.engine != TNP_PROFILE_ENGINE:
        raise HTTPException(404, "TNP profile job not found")
    return job


def _work(job: Job) -> Path:
    if not job.work_dir:
        raise HTTPException(404, "Job work_dir missing")
    return Path(job.work_dir)


def _exports(job: Job) -> Path:
    return _work(job) / "exports"


def _tnp_batch_or_404(db: Session, user_id: str, batch_id: str) -> Batch:
    batch = db.get(Batch, batch_id)
    if not batch or batch.user_id != user_id or batch.batch_type != TNP_BATCH_TYPE:
        raise HTTPException(404, "画像批次不存在")
    return batch


def _batch_counts(db: Session, batch_id: str) -> dict[str, int]:
    rows = db.execute(
        select(Job.status, func.count()).where(Job.batch_id == batch_id).group_by(Job.status)
    ).all()
    counts = {s: c for s, c in rows}
    return {
        "done": counts.get(JobStatus.done.value, 0),
        "running": counts.get(JobStatus.running.value, 0),
        "queued": counts.get(JobStatus.queued.value, 0),
        "failed": counts.get(JobStatus.failed.value, 0),
        "cancelled": counts.get(JobStatus.cancelled.value, 0),
    }


def _batch_status(counts: dict[str, int], total: int) -> str:
    if counts["running"] or counts["queued"]:
        return "running" if counts["running"] else "queued"
    if counts["done"] == total:
        return "done"
    if counts["failed"] and counts["done"]:
        return "partial"
    if counts["failed"]:
        return "failed"
    if counts["cancelled"] == total:
        return "cancelled"
    return "done"


def _batch_out(batch: Batch, db: Session) -> BatchOut:
    counts = _batch_counts(db, batch.id)
    total = batch.heavy_chain_count
    return BatchOut(
        id=batch.id,
        name=batch.name,
        batch_type=batch.batch_type,
        target_name=batch.target_name,
        target_chain_id=batch.target_chain_id,
        heavy_chain_id=batch.heavy_chain_id,
        heavy_chain_count=total,
        use_msa_server=batch.use_msa_server,
        created_at=batch.created_at,
        status=_batch_status(counts, total),
        done_count=counts["done"],
        running_count=counts["running"],
        queued_count=counts["queued"],
        failed_count=counts["failed"],
        cancelled_count=counts["cancelled"],
    )


@router.post("", response_model=TnpProfileJobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    body: TnpProfileJobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    records = parse_vhh_records(body.fasta)
    if len(records) > 1:
        raise HTTPException(400, f"检测到 {len(records)} 条 VHH，请改用批量提交")
    name = body.name.strip() if body.name and body.name.strip() else "tnp_profile"
    job = create_and_queue_tnp_profile_job(
        db,
        user_id=user.id,
        name=name,
        fasta_text=body.fasta,
    )
    db.commit()
    dispatch_tnp_profile_jobs([job])
    db.commit()
    db.refresh(job)
    return _out(job)


@router.post("/upload", response_model=TnpProfileJobOut, status_code=status.HTTP_201_CREATED)
async def create_job_upload(
    fasta: str = Form(...),
    name: str | None = Form(default=None),
    structure: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    structure_path: Path | None = None
    if structure and structure.filename:
        tmp = settings.tnp_profile_out_root / "_uploads" / user.id
        suffix = Path(structure.filename).suffix.lower() or ".pdb"
        structure_path = await save_structure_upload(structure, tmp / f"structure{suffix}")
    job_name = name.strip() if name and name.strip() else "tnp_profile"
    job = create_and_queue_tnp_profile_job(
        db,
        user_id=user.id,
        name=job_name,
        fasta_text=fasta,
        structure_path=structure_path,
    )
    db.commit()
    dispatch_tnp_profile_jobs([job])
    db.commit()
    db.refresh(job)
    return _out(job)


@router.post("/batches", response_model=TnpProfileBatchCreateOut, status_code=status.HTTP_201_CREATED)
def create_batch(
    body: TnpProfileBatchCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    parse_vhh_records(body.fasta)
    batch, jobs = create_and_queue_tnp_profile_batch(
        db,
        user_id=user.id,
        name=body.name.strip() if body.name and body.name.strip() else "",
        fasta_text=body.fasta,
    )
    db.commit()
    dispatch_tnp_profile_jobs(jobs)
    db.commit()
    db.refresh(batch)
    return TnpProfileBatchCreateOut(batch=_batch_out(batch, db), job_ids=[j.id for j in jobs])


@router.get("", response_model=TnpProfileJobListOut)
def list_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    condition = (Job.user_id == user.id, Job.engine == TNP_PROFILE_ENGINE, Job.batch_id.is_(None))
    rows = db.scalars(
        select(Job).where(*condition).order_by(Job.created_at.desc()).limit(limit).offset(offset)
    ).all()
    total = db.scalar(select(func.count()).select_from(Job).where(*condition)) or 0
    return TnpProfileJobListOut(items=[_out(j) for j in rows], total=total)


@router.get("/batches", response_model=BatchListOut)
def list_batches(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    condition = (Batch.user_id == user.id, Batch.batch_type == TNP_BATCH_TYPE)
    total = db.scalar(select(func.count()).select_from(Batch).where(*condition)) or 0
    rows = db.scalars(
        select(Batch).where(*condition).order_by(Batch.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return BatchListOut(items=[_batch_out(b, db) for b in rows], total=total)


@router.get("/batches/{batch_id}", response_model=BatchDetailOut)
def get_batch(batch_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    batch = _tnp_batch_or_404(db, user.id, batch_id)
    out = _batch_out(batch, db)
    return BatchDetailOut(**out.model_dump(), target_sequence=batch.target_sequence or "")


@router.get("/batches/{batch_id}/jobs", response_model=BatchJobsListOut)
def list_batch_jobs(
    batch_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    _tnp_batch_or_404(db, user.id, batch_id)
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
    import csv
    from io import StringIO

    from fastapi.responses import Response

    _tnp_batch_or_404(db, user.id, batch_id)
    jobs = db.scalars(select(Job).where(Job.batch_id == batch_id).order_by(Job.created_at.asc())).all()
    buf = StringIO()
    cols = [
        "id",
        "name",
        "status",
        "L",
        "L3",
        "C",
        "PSH",
        "PPC",
        "PNC",
        "L_flag",
        "L3_flag",
        "C_flag",
        "PSH_flag",
        "PPC_flag",
        "PNC_flag",
        "tetrad",
    ]
    writer = csv.DictWriter(buf, fieldnames=cols)
    writer.writeheader()
    for job in jobs:
        summary = ((job.results_json or {}).get("summary") or {}) if job.results_json else {}
        flags = {m.get("id"): m.get("flag") for m in (summary.get("metrics") or [])}
        writer.writerow(
            {
                "id": job.heavy_chain_id or job.id,
                "name": job.name or "",
                "status": job.status,
                "L": summary.get("L", ""),
                "L3": summary.get("L3", ""),
                "C": summary.get("C", ""),
                "PSH": summary.get("PSH", ""),
                "PPC": summary.get("PPC", ""),
                "PNC": summary.get("PNC", ""),
                "L_flag": flags.get("L", ""),
                "L3_flag": flags.get("L3", ""),
                "C_flag": flags.get("C", ""),
                "PSH_flag": flags.get("PSH", ""),
                "PPC_flag": flags.get("PPC", ""),
                "PNC_flag": flags.get("PNC", ""),
                "tetrad": summary.get("tetrad_motif", ""),
            }
        )
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="tnp_batch_{batch_id[:8]}.csv"'},
    )


@router.delete("/batches/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_batch(batch_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    batch = _tnp_batch_or_404(db, user.id, batch_id)
    jobs = db.scalars(select(Job).where(Job.batch_id == batch_id)).all()
    for job in jobs:
        if job.status in (JobStatus.queued.value, JobStatus.running.value) and job.celery_task_id:
            celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
        remove_job_outputs(
            settings.tnp_profile_out_root,
            job.id,
            job.name,
            job.chains_json,
            job.work_dir,
        )
        db.delete(job)
    db.delete(batch)
    db.commit()


@router.get("/{job_id}", response_model=TnpProfileJobOut)
def get_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _out(_job_or_404(db, user.id, job_id))


@router.get("/{job_id}/progress", response_model=TnpProfileProgressOut)
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
    return TnpProfileProgressOut(stage=stage, status=job.status, summary=summary)


@router.get("/{job_id}/ranked", response_model=TnpProfileRankedOut)
def get_ranked(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    import csv

    job = _job_or_404(db, user.id, job_id)
    patches: list[dict] = []
    residues: list[dict] = []
    metrics: list[dict] = []
    summary = None
    if job.results_json:
        patches = list(job.results_json.get("patches") or [])
        residues = list(job.results_json.get("residues") or [])
        metrics = list(job.results_json.get("metrics") or [])
        summary = job.results_json.get("summary")
    exports = _exports(job)
    if (exports / "patches.csv").is_file():
        with (exports / "patches.csv").open(newline="", encoding="utf-8") as f:
            patches = list(csv.DictReader(f))
    res_csv = _work(job) / "score" / "residue_features.csv"
    if not res_csv.is_file():
        res_csv = exports / "residue_features.csv"
    if res_csv.is_file():
        with res_csv.open(newline="", encoding="utf-8") as f:
            residues = list(csv.DictReader(f))
    if (exports / "summary.json").is_file():
        summary = json.loads((exports / "summary.json").read_text(encoding="utf-8"))
        metrics = list((summary or {}).get("metrics") or metrics)
    return TnpProfileRankedOut(patches=patches, residues=residues, metrics=metrics, summary=summary)


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
    path = _exports(job) / filename
    if not path.is_file():
        for alt_dir in (_work(job) / "score", _work(job) / "fold", _work(job) / "input"):
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
    return FileResponse(path, filename=filename, media_type=media)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _job_or_404(db, user.id, job_id)
    if job.status in (JobStatus.queued.value, JobStatus.running.value) and job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
    db.delete(job)
    db.commit()
