"""Antibody maturation task."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.job_paths import job_output_dir, write_job_info
from app.common.structure_paths import resolve_structure_path
from worker.task_runtime import (
    Job,
    JobStatus,
    Path,
    SessionLocal,
    User,
    celery_app,
    settings,
    utcnow,
)


def _write_maturation_job_info(db: Session, job: Job, user: User | None) -> None:
    if not job.work_dir:
        return
    write_job_info(
        Path(job.work_dir),
        job_id=job.id,
        name=job.name,
        username=user.username if user else None,
        status=job.status,
        chains_json=job.chains_json,
        engine=job.engine,
        stage=job.stage,
        results_json=job.results_json,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        runtime_seconds=job.runtime_seconds,
        error_message=job.error_message,
    )


@celery_app.task(bind=True, name="worker.tasks.run_maturation_job")
def run_maturation_job(self, job_id: str) -> dict:
    db: Session = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return {"error": "job not found"}
        if job.engine != "iggm_maturation":
            return {"error": "not a maturation job"}
        if job.status == JobStatus.cancelled.value:
            return {"status": "cancelled"}

        user = db.get(User, job.user_id)
        params = dict(job.params_json or {})
        work_dir = Path(job.work_dir) if job.work_dir else job_output_dir(
            settings.maturation_out_root, job.name, job.id, job.chains_json
        )

        structure_path: Path | None = None
        uploaded = params.get("uploaded_structure")
        if uploaded:
            structure_path = Path(uploaded)
        elif params.get("structure_source") == "fold_job" and job.parent_job_id:
            parent = db.get(Job, job.parent_job_id)
            if parent:
                structure_path = resolve_structure_path(parent)

        job.status = JobStatus.running.value
        job.stage = "queued"
        job.started_at = utcnow()
        job.celery_task_id = self.request.id
        job.work_dir = str(work_dir)
        db.commit()
        _write_maturation_job_info(db, job, user)

        def on_stage(stage: str) -> None:
            j = db.get(Job, job_id)
            if not j or j.status == JobStatus.cancelled.value:
                return
            j.stage = stage
            db.commit()
            _write_maturation_job_info(db, j, user)

        from iggm_maturation_runner import run_maturation_pipeline

        result = run_maturation_pipeline(
            work_dir=work_dir,
            fasta_text=job.fasta_text,
            params=params,
            structure_path=structure_path,
            on_stage=on_stage,
        )

        job = db.get(Job, job_id)
        if not job:
            return {"job_id": job_id, "status": "deleted"}

        job.finished_at = utcnow()
        job.runtime_seconds = result.seconds
        job.stage = result.stage or ("done" if result.status == "ok" else "failed")

        if result.status == "ok":
            job.status = JobStatus.done.value
            job.results_json = result.results
            job.structure_path = (result.results or {}).get("complex_pdb")
            job.error_message = None
        else:
            job.status = JobStatus.failed.value
            job.error_message = (result.error or "Maturation failed")[:8000]
            if result.results:
                job.results_json = result.results

        _write_maturation_job_info(db, job, user)
        db.commit()
        return {"job_id": job_id, "status": job.status}

    except Exception as exc:
        if job := db.get(Job, job_id):
            job.status = JobStatus.failed.value
            job.error_message = str(exc)[:8000]
            job.finished_at = utcnow()
            db.commit()
        raise
    finally:
        db.close()
