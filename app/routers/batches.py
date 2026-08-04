"""VHH panel batch jobs: one target × many heavy chains."""

from __future__ import annotations

import base64
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.job_paths import remove_job_outputs
from app.job_service import create_and_queue_job, dispatch_job, sequence_hash
from app.models import Batch, Job, JobStatus, User
from app.schemas import (
    BatchDetailOut,
    BatchJobOut,
    BatchJobsListOut,
    BatchListOut,
    BatchOut,
    HeavyCsvParseOut,
    HeavyCsvParseRow,
    HeavyCsvParseB64,
    VhhPanelCreate,
    VhhPanelCreateOut,
)
from app.csv_decode import (
    decode_upload_bytes,
    format_heavy_chain_display,
    parse_heavy_chain_text,
)
from app.vhh_panel import HeavyChainSpec, prepare_panel_jobs

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from boltz_runner import parse_fasta_text, validate_boltz_chain_ids

router = APIRouter(prefix="/api/batches", tags=["batches"])


def _parse_heavy_csv_bytes(raw: bytes, filename: str) -> HeavyCsvParseOut:
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件过大（最大 10MB）")
    try:
        text, encoding = decode_upload_bytes(raw, filename)
        rows, fmt = parse_heavy_chain_text(text)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"文件解析失败: {exc}") from exc
    display = format_heavy_chain_display(rows, fmt) if rows else text
    return HeavyCsvParseOut(
        text=display,
        encoding=encoding,
        format=fmt,
        rows=[HeavyCsvParseRow(id=hid, sequence=seq) for hid, seq in rows],
        row_count=len(rows),
    )


@router.post("/parse-heavy-csv", response_model=HeavyCsvParseOut)
async def parse_heavy_csv_upload(file: UploadFile = File(...)):
    raw = await file.read()
    return _parse_heavy_csv_bytes(raw, file.filename or "")


@router.post("/parse-heavy-csv-b64", response_model=HeavyCsvParseOut)
def parse_heavy_csv_b64(body: HeavyCsvParseB64):
    try:
        raw = base64.b64decode(body.content_b64, validate=True)
    except Exception as exc:
        raise HTTPException(400, "文件内容无效") from exc
    return _parse_heavy_csv_bytes(raw, body.filename)


def _batch_counts(db: Session, batch_id: str) -> dict[str, int]:
    rows = db.execute(
        select(Job.status, func.count())
        .where(Job.batch_id == batch_id)
        .group_by(Job.status)
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


@router.post("/vhh-panel", response_model=VhhPanelCreateOut, status_code=status.HTTP_201_CREATED)
def create_vhh_panel(body: VhhPanelCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    heavy_chains = [HeavyChainSpec(id=hc.id, sequence=hc.sequence) for hc in body.heavy_chains]

    batch_name, target, job_specs, skipped = prepare_panel_jobs(
        batch_name=body.batch_name,
        target_name=body.target.name,
        target_chain_id=body.target.chain_id,
        target_sequence=body.target.sequence,
        heavy_chain_id=body.heavy_chain_id,
        heavy_chains=heavy_chains,
    )

    if body.engine == "boltz2":
        try:
            validate_boltz_chain_ids({target.chain_id: target.sequence, body.heavy_chain_id: "A"})
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    batch = Batch(
        user_id=user.id,
        name=batch_name,
        batch_type="vhh_panel",
        target_name=target.name,
        target_chain_id=target.chain_id,
        target_sequence=target.sequence,
        heavy_chain_id=body.heavy_chain_id,
        heavy_chain_count=len(job_specs),
        use_msa_server=body.use_msa_server,
    )
    db.add(batch)
    db.flush()

    job_ids: list[str] = []
    pending_jobs: list[Job] = []
    for job_name, hid, fasta_text in job_specs:
        seqs = parse_fasta_text(fasta_text)
        job = create_and_queue_job(
            db,
            user_id=user.id,
            name=job_name,
            fasta_text=fasta_text,
            chains_json={k: len(v) for k, v in seqs.items()},
            total_length=sum(len(v) for v in seqs.values()),
            seq_hash=sequence_hash(seqs),
            use_msa_server=body.use_msa_server if body.engine == "boltz2" else False,
            batch_id=batch.id,
            heavy_chain_id=hid,
            skip_running_limit=True,
            engine=body.engine,
            esmfold_params=body.esmfold_params.model_dump() if body.engine == "esmfold2" and body.esmfold_params else None,
            defer_dispatch=True,
        )
        pending_jobs.append(job)
        job_ids.append(job.id)

    db.commit()
    for job in pending_jobs:
        dispatch_job(db, job)
    db.commit()
    db.refresh(batch)
    return VhhPanelCreateOut(
        batch=_batch_out(batch, db),
        job_ids=job_ids,
        skipped_duplicates=skipped,
    )


@router.get("", response_model=BatchListOut)
def list_batches(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    total = db.scalar(select(func.count()).select_from(Batch).where(Batch.user_id == user.id)) or 0
    rows = db.scalars(
        select(Batch)
        .where(Batch.user_id == user.id)
        .order_by(Batch.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return BatchListOut(items=[_batch_out(b, db) for b in rows], total=total)


@router.get("/{batch_id}", response_model=BatchDetailOut)
def get_batch(batch_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    batch = db.get(Batch, batch_id)
    if not batch or batch.user_id != user.id:
        raise HTTPException(404, "Batch not found")

    base = _batch_out(batch, db)
    return BatchDetailOut(
        **base.model_dump(),
        target_sequence=batch.target_sequence,
    )


@router.get("/{batch_id}/jobs", response_model=BatchJobsListOut)
def list_batch_jobs(
    batch_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: str | None = Query(default=None, description="Filter: done, running, queued, failed"),
):
    batch = db.get(Batch, batch_id)
    if not batch or batch.user_id != user.id:
        raise HTTPException(404, "Batch not found")

    q = select(Job).where(Job.batch_id == batch_id)
    count_q = select(func.count()).select_from(Job).where(Job.batch_id == batch_id)
    if status:
        q = q.where(Job.status == status)
        count_q = count_q.where(Job.status == status)

    total = db.scalar(count_q) or 0
    jobs = db.scalars(
        q.order_by(Job.iptm.desc().nullslast(), Job.created_at).limit(limit).offset(offset)
    ).all()
    return BatchJobsListOut(
        items=[BatchJobOut.model_validate(j) for j in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_batch(batch_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    batch = db.get(Batch, batch_id)
    if not batch or batch.user_id != user.id:
        raise HTTPException(404, "Batch not found")

    jobs = db.scalars(select(Job).where(Job.batch_id == batch_id)).all()
    from app.celery_app import celery_app

    for job in jobs:
        if job.status in (JobStatus.queued.value, JobStatus.running.value):
            job.status = JobStatus.cancelled.value
            if job.celery_task_id:
                celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
        remove_job_outputs(
            settings.boltz2_out_root,
            job.id,
            job.name,
            job.chains_json,
            job.work_dir,
        )
        db.delete(job)

    db.delete(batch)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
