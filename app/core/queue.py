"""GPU / fold queue helpers."""

from __future__ import annotations

from celery.canvas import Signature

from app.core.config import settings


def gpu_queue_name() -> str:
    return settings.celery_gpu_queue


def fold_queue_name() -> str:
    return settings.celery_fold_queue


def cpu_queue_name() -> str:
    return settings.celery_cpu_queue


def dispatch_to_gpu(task: Signature, job_id: str):
    """Send task to the shared GPU queue (FIFO, fills all workers)."""
    return task.apply_async(args=[job_id], queue=gpu_queue_name())


def dispatch_to_fold(task: Signature, job_id: str):
    """Boltz2 远程折叠队列（本机不占 NVIDIA）。"""
    return task.apply_async(args=[job_id], queue=fold_queue_name())


def dispatch_fold_compute(task: Signature, job_id: str):
    """疏水/CIC 等：开启远程 NPU 时进 fold 队列，否则仍走 GPU。"""
    if settings.boltz_npu_remote:
        return dispatch_to_fold(task, job_id)
    return dispatch_to_gpu(task, job_id)


def dispatch_to_cpu(task: Signature, job_id: str):
    """PyRosetta / ANARCI 等 CPU 作业。"""
    return task.apply_async(args=[job_id], queue=cpu_queue_name())
