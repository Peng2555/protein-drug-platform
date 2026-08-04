#!/usr/bin/env python3
"""Write job_info.json and readable symlinks for existing job output folders."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.job_paths import job_output_dir, job_output_dir_name, write_job_info
from app.models import Job, User


def main() -> None:
    db = SessionLocal()
    try:
        jobs = db.scalars(select(Job).order_by(Job.created_at)).all()
        if not jobs:
            print("No jobs in database.")
            return

        for job in jobs:
            user = db.get(User, job.user_id)
            label_dir = job_output_dir(settings.boltz2_out_root, job.name, job.id, job.chains_json)
            legacy_dir = settings.boltz2_out_root / job.id

            target: Path | None = None
            if job.work_dir and Path(job.work_dir).is_dir():
                target = Path(job.work_dir)
            elif legacy_dir.is_dir():
                target = legacy_dir
            elif label_dir.is_dir():
                target = label_dir

            if target is None:
                print(f"SKIP {job.id}: no output folder found")
                continue

            write_job_info(
                target,
                job_id=job.id,
                name=job.name,
                username=user.username if user else None,
                status=job.status,
                chains_json=job.chains_json,
                engine=job.engine,
                created_at=job.created_at,
                started_at=job.started_at,
                finished_at=job.finished_at,
                iptm=job.iptm,
                ptm=job.ptm,
                confidence_score=job.confidence_score,
                complex_plddt=job.complex_plddt,
                runtime_seconds=job.runtime_seconds,
                error_message=job.error_message,
            )
            print(f"Wrote {target / 'job_info.json'}")

            if target != label_dir:
                if label_dir.exists() or label_dir.is_symlink():
                    label_dir.unlink(missing_ok=True)
                label_dir.symlink_to(target.resolve())
                print(f"Link {label_dir.name} -> {target.name}")
                if job.work_dir != str(label_dir.resolve()):
                    job.work_dir = str(target.resolve())
            elif job.work_dir != str(target):
                job.work_dir = str(target)

        db.commit()
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
