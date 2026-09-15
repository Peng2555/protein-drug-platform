"""Shared batch status and response construction."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.models import Batch, Job, JobStatus
from app.schemas import BatchOut


def batch_counts(db: Session, batch_id: str) -> dict[str, int]:
    rows = db.execute(
        select(Job.status, func.count()).where(Job.batch_id == batch_id).group_by(Job.status)
    ).all()
    counts = {status: count for status, count in rows}
    return {
        "done": counts.get(JobStatus.done.value, 0),
        "running": counts.get(JobStatus.running.value, 0),
        "queued": counts.get(JobStatus.queued.value, 0),
        "failed": counts.get(JobStatus.failed.value, 0),
        "cancelled": counts.get(JobStatus.cancelled.value, 0),
    }


def batch_status(counts: dict[str, int], total: int) -> str:
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


def batch_out(batch: Batch, db: Session) -> BatchOut:
    counts = batch_counts(db, batch.id)
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
        status=batch_status(counts, total),
        done_count=counts["done"],
        running_count=counts["running"],
        queued_count=counts["queued"],
        failed_count=counts["failed"],
        cancelled_count=counts["cancelled"],
    )
