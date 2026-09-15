"""Pure helpers shared by Celery task implementations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def wall_seconds(started: datetime | None, finished: datetime | None) -> float | None:
    start, end = aware_utc(started), aware_utc(finished)
    if start is None or end is None:
        return None
    return max(0.0, (end - start).total_seconds())


def compact_profile_results(
    results: dict[str, Any] | None,
    *,
    include_metrics: bool = False,
    include_patch_count: bool = False,
) -> dict[str, Any]:
    payload = results or {}
    compact = {
        "summary": payload.get("summary"),
        "pred_cif": payload.get("pred_cif"),
    }
    if include_metrics:
        compact["metrics"] = payload.get("metrics")
    if include_patch_count:
        compact["n_patches"] = len(payload.get("patches") or [])
    return compact
