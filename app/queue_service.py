"""GPU queue helpers — unified dispatch for fold + MD tasks."""

from __future__ import annotations

from celery.canvas import Signature

from app.config import settings


def gpu_queue_name() -> str:
    return settings.celery_gpu_queue


def dispatch_to_gpu(task: Signature, job_id: str):
    """Send task to the shared GPU queue (FIFO, fills all workers)."""
    return task.apply_async(args=[job_id], queue=gpu_queue_name())
