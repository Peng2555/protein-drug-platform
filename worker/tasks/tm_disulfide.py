"""Tm extra-disulfide Celery task."""

from __future__ import annotations

from sqlalchemy.orm import Session

from worker.task_runtime import (
    Job,
    JobStatus,
    Path,
    SessionLocal,
    celery_app,
    settings,
    utcnow,
    wall_seconds,
)
from tm_disulfide_runner import run_tm_disulfide_job as run_tm_disulfide_pipeline


@celery_app.task(bind=True, name="worker.tasks.run_tm_disulfide_job")
def run_tm_disulfide_job(self, job_id: str) -> dict:
    db: Session = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job or job.engine != "tm_disulfide":
            return {"error": "not a Tm disulfide job"}
        if job.status == JobStatus.cancelled.value:
            return {"status": "cancelled"}
        params = dict(job.params_json or {})
        job.status = JobStatus.running.value
        job.stage = "queued"
        if job.started_at is None:
            job.started_at = utcnow()
        job.celery_task_id = self.request.id
        db.commit()

        def on_stage(stage: str) -> None:
            current = db.get(Job, job_id)
            if current and current.status != JobStatus.cancelled.value:
                current.stage = stage
                db.commit()

        result = run_tm_disulfide_pipeline(
            work_dir=Path(job.work_dir or settings.tm_disulfide_out_root / job.id),
            params=params,
            fasta_text=job.fasta_text or "",
            on_stage=on_stage,
        )
        job = db.get(Job, job_id)
        if not job:
            return {"job_id": job_id, "status": "deleted"}
        job.finished_at = utcnow()
        wall = wall_seconds(job.started_at, job.finished_at)
        job.runtime_seconds = wall if wall is not None else result.seconds
        job.stage = result.stage
        payload = result.results or {}
        job.results_json = {
            "summary": payload.get("summary"),
            "n_energy_pass": payload.get("n_energy_pass"),
            "n_build_pass": payload.get("n_build_pass"),
            "n_geometry_pass": payload.get("n_geometry_pass"),
        }
        if result.status == "ok":
            job.status = JobStatus.done.value
            job.error_message = None
        else:
            job.status = JobStatus.failed.value
            job.error_message = (result.error or "Tm disulfide workflow failed")[:8000]
        db.commit()
        return {"job_id": job_id, "status": job.status}
    except Exception as exc:
        job = db.get(Job, job_id)
        if job:
            job.status = JobStatus.failed.value
            job.error_message = str(exc)[:8000]
            job.finished_at = utcnow()
            wall = wall_seconds(job.started_at, job.finished_at)
            if wall is not None:
                job.runtime_seconds = wall
            db.commit()
        raise
    finally:
        db.close()
