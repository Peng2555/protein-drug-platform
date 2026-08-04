#!/usr/bin/env python3
"""Backfill pDockQ for completed fold jobs missing scores."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Job, JobStatus
from pdockq_runner import compute_pdockq_from_boltz_dir


def backfill(*, batch_id: str | None = None, limit: int = 0, force: bool = False) -> int:
    db = SessionLocal()
    updated = 0
    try:
        q = select(Job).where(
            Job.status == JobStatus.done.value,
            Job.structure_path.isnot(None),
        )
        if batch_id:
            q = q.where(Job.batch_id == batch_id)
        if not force:
            q = q.where(Job.pdockq.is_(None))
        jobs = db.scalars(q).all()
        if limit > 0:
            jobs = jobs[:limit]
        for job in jobs:
            work_dir = Path(job.work_dir) if job.work_dir else Path(job.structure_path).parent
            if not work_dir.is_dir():
                continue
            pq = compute_pdockq_from_boltz_dir(work_dir)
            if pq.pdockq is None and pq.pdockq2 is None:
                continue
            job.pdockq = pq.pdockq
            job.pdockq2 = pq.pdockq2
            metrics_path = work_dir / "metrics.json"
            if metrics_path.is_file():
                payload = json.loads(metrics_path.read_text(encoding="utf-8"))
                payload["pdockq"] = job.pdockq
                payload["pdockq2"] = job.pdockq2
                metrics_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            updated += 1
        db.commit()
        return updated
    finally:
        db.close()


if __name__ == "__main__":
    batch = None
    force = False
    for arg in sys.argv[1:]:
        if arg == "--force":
            force = True
        else:
            batch = arg
    n = backfill(batch_id=batch, force=force)
    print(f"backfilled pdockq for {n} jobs")
