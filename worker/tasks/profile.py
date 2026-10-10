"""CIC and TNP profile tasks."""

from __future__ import annotations

from sqlalchemy.orm import Session

from worker.task_runtime import (
    Job,
    JobStatus,
    Path,
    SessionLocal,
    celery_app,
    compact_profile_results,
    settings,
    utcnow,
    wall_seconds,
)
from cic_profile_runner import run_cic_profile_job as run_cic_profile_pipeline
from tnp_profile_runner import run_tnp_profile_job as run_tnp_profile_pipeline


@celery_app.task(bind=True, name="worker.tasks.run_cic_profile_job")
def run_cic_profile_job(self, job_id: str) -> dict:
    db: Session = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job or job.engine != "cic_profile":
            return {"error": "not a CIC profile job"}
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

        result = run_cic_profile_pipeline(
            work_dir=Path(job.work_dir or settings.cic_profile_out_root / job.id),
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
        job.results_json = compact_profile_results(result.results, include_patch_count=True)
        if result.status == "ok":
            job.status = JobStatus.done.value
            job.error_message = None
        else:
            job.status = JobStatus.failed.value
            job.error_message = (result.error or "CIC profile workflow failed")[:8000]
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


@celery_app.task(bind=True, name="worker.tasks.run_tnp_profile_job")
def run_tnp_profile_job(self, job_id: str) -> dict:
    db: Session = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            raise self.retry(countdown=2, max_retries=10)
        if job.engine != "tnp_profile":
            return {"error": "not a TNP profile job"}
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

        result = run_tnp_profile_pipeline(
            work_dir=Path(job.work_dir or settings.tnp_profile_out_root / job.id),
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
        job.results_json = compact_profile_results(result.results, include_metrics=True)
        if result.status == "ok":
            job.status = JobStatus.done.value
            job.error_message = None
        else:
            job.status = JobStatus.failed.value
            job.error_message = (result.error or "TNP profile workflow failed")[:8000]
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
