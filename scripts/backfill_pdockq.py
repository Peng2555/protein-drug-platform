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


def backfill(
    *,
    batch_id: str | None = None,
    limit: int = 0,
    force: bool = False,
    commit_every: int = 50,
) -> int:
    db = SessionLocal()
    updated = 0
    skipped = 0
    try:
        q = select(Job).where(
            Job.status == JobStatus.done.value,
            Job.structure_path.isnot(None),
        )
        if batch_id:
            q = q.where(Job.batch_id == batch_id)
        if not force:
            q = q.where((Job.pdockq.is_(None)) | (Job.pdockq == 0.0))
        jobs = db.scalars(q).all()
        if limit > 0:
            jobs = jobs[:limit]
        total = len(jobs)
        print(f"processing {total} jobs...", flush=True)
        for i, job in enumerate(jobs, 1):
            work_dir = Path(job.work_dir) if job.work_dir else Path(job.structure_path).parent
            if not work_dir.is_dir():
                skipped += 1
                continue
            pq = compute_pdockq_from_boltz_dir(work_dir)
            if pq.pdockq is None and pq.pdockq2 is None:
                skipped += 1
                continue
            if pq.pdockq is not None and pq.pdockq > 0:
                job.pdockq = pq.pdockq
            elif pq.pdockq is not None:
                job.pdockq = pq.pdockq
            if pq.pdockq2 is not None and pq.pdockq2 > 0:
                job.pdockq2 = pq.pdockq2
            elif pq.pdockq2 is not None and job.pdockq2 in (None, 0.0):
                job.pdockq2 = pq.pdockq2
            if job.pdockq is None:
                skipped += 1
                continue
            metrics_path = work_dir / "metrics.json"
            if metrics_path.is_file():
                payload = json.loads(metrics_path.read_text(encoding="utf-8"))
                payload["pdockq"] = job.pdockq
                payload["pdockq2"] = job.pdockq2
                metrics_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            updated += 1
            if commit_every > 0 and updated % commit_every == 0:
                db.commit()
                print(f"  {i}/{total}: updated {updated}, skipped {skipped}", flush=True)
        db.commit()
        print(f"done: updated {updated}, skipped {skipped}", flush=True)
        return updated
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Backfill pDockQ for completed fold jobs")
    parser.add_argument("batch_id", nargs="?", default=None, help="Optional batch UUID")
    parser.add_argument("--force", action="store_true", help="Recompute even when pdockq is set")
    parser.add_argument("--limit", type=int, default=0, help="Max jobs to process (0 = all)")
    parser.add_argument("--commit-every", type=int, default=50, help="Commit interval")
    args = parser.parse_args()
    n = backfill(
        batch_id=args.batch_id,
        limit=args.limit,
        force=args.force,
        commit_every=args.commit_every,
    )
    print(f"backfilled pdockq for {n} jobs")
