"""Celery application."""

from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "boltzfold",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    broker_connection_retry_on_startup=True,
    task_routes={
        "worker.tasks.run_fold_job": {"queue": settings.celery_gpu_queue},
        "worker.tasks.run_md_job": {"queue": settings.celery_gpu_queue},
    },
    task_default_queue=settings.celery_gpu_queue,
)
