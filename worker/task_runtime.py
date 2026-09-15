"""Shared runtime imports and one-time path bootstrap for Celery tasks."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from algorithm_paths import bootstrap_algorithm_paths

bootstrap_algorithm_paths(include_scripts=True)

from app.core.celery import celery_app
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.models import Job, JobStatus, User
from worker.task_helpers import (
    compact_profile_results,
    utcnow,
    wall_seconds,
)

__all__ = [
    "Job",
    "JobStatus",
    "Path",
    "SessionLocal",
    "User",
    "celery_app",
    "compact_profile_results",
    "settings",
    "utcnow",
    "wall_seconds",
]
