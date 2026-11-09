"""结构预测的读取范围：管理员可查看全部，普通用户只看自己的。"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.engines import FOLD_ENGINES
from app.core.models import Batch, Job, User

FOLD_BATCH_TYPES = frozenset({"vhh_panel", "antibody_only"})


def usernames_for(db: Session, user_ids: set[str]) -> dict[str, str]:
    if not user_ids:
        return {}
    rows = db.execute(select(User.id, User.username).where(User.id.in_(user_ids))).all()
    return {user_id: username for user_id, username in rows}


def can_read_fold_job(user: User, job: Job) -> bool:
    if job.user_id == user.id:
        return True
    return bool(user.is_admin) and job.engine in FOLD_ENGINES


def can_read_fold_batch(user: User, batch: Batch) -> bool:
    if batch.user_id == user.id:
        return True
    return bool(user.is_admin) and batch.batch_type in FOLD_BATCH_TYPES


def readable_fold_job(user: User, job: Job | None) -> Job:
    if job is None or not can_read_fold_job(user, job):
        raise HTTPException(404, "Job not found")
    return job


def owned_fold_job(user: User, job: Job | None) -> Job:
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.user_id == user.id:
        return job
    if user.is_admin and job.engine in FOLD_ENGINES:
        raise HTTPException(403, "只能修改自己的结构预测")
    raise HTTPException(404, "Job not found")


def readable_fold_batch(user: User, batch: Batch | None) -> Batch:
    if batch is None or not can_read_fold_batch(user, batch):
        raise HTTPException(404, "Batch not found")
    return batch


def owned_fold_batch(user: User, batch: Batch | None) -> Batch:
    if batch is None:
        raise HTTPException(404, "Batch not found")
    if batch.user_id == user.id:
        return batch
    if user.is_admin and batch.batch_type in FOLD_BATCH_TYPES:
        raise HTTPException(403, "只能修改自己的结构预测")
    raise HTTPException(404, "Batch not found")
