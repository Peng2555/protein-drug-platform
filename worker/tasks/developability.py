"""ESM2 developability task."""

from __future__ import annotations

from sqlalchemy.orm import Session

from worker.task_runtime import Job, JobStatus, Path, SessionLocal, celery_app, settings, utcnow
from esm2_developability_runner import run_developability_job as run_developability_pipeline


@celery_app.task(bind=True, name="worker.tasks.run_developability_job")
def run_developability_job(self, job_id: str) -> dict:
    db: Session = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job or job.engine != "esm2_developability":
            return {"error": "not a developability job"}
        if job.status == JobStatus.cancelled.value:
            return {"status": "cancelled"}
        params = dict(job.params_json or {})
        job.status = JobStatus.running.value
        job.stage = "queued"
        job.started_at = utcnow()
        job.celery_task_id = self.request.id
        db.commit()

        def on_stage(stage: str) -> None:
            current = db.get(Job, job_id)
            if current and current.status != JobStatus.cancelled.value:
                current.stage = stage
                db.commit()

        result = run_developability_pipeline(
            work_dir=Path(job.work_dir or settings.developability_out_root / job.id),
            fasta_text=job.fasta_text,
            params=params,
            on_stage=on_stage,
        )
        job = db.get(Job, job_id)
        if not job:
            return {"job_id": job_id, "status": "deleted"}
        job.finished_at = utcnow()
        job.runtime_seconds = result.seconds
        job.stage = result.stage
        job.results_json = result.results
        if result.status == "ok":
            job.status = JobStatus.done.value
            job.error_message = None
        else:
            job.status = JobStatus.failed.value
            job.error_message = (result.error or "Developability scoring failed")[:8000]
        db.commit()
        return {"job_id": job_id, "status": job.status}
    except Exception as exc:
        job = db.get(Job, job_id)
        if job:
            job.status = JobStatus.failed.value
            job.error_message = str(exc)[:8000]
            job.finished_at = utcnow()
            db.commit()
        raise
    finally:
        db.close()
