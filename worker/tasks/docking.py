"""RAS tricomplex and small-molecule docking tasks."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.job_paths import job_output_dir
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
from docking_runner import run_small_molecule_docking
from ras_docking_runner import run_ras_docking


@celery_app.task(bind=True, name="worker.tasks.run_ras_docking_job")
def run_ras_docking_job(self, job_id: str) -> dict:
    db: Session = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return {"error": "job not found"}
        if job.engine != "ras_tricomplex_docking":
            return {"error": "not a RAS docking job"}
        if job.status == JobStatus.cancelled.value:
            return {"status": "cancelled"}

        user = db.get(User, job.user_id)
        params = dict(job.params_json or {})
        work_dir = Path(job.work_dir or job_output_dir(
            settings.ras_docking_out_root, job.name, job.id, job.chains_json,
        ))
        work_dir.mkdir(parents=True, exist_ok=True)
        job.status = JobStatus.running.value
        job.stage = "queued"
        job.started_at = utcnow()
        job.celery_task_id = self.request.id
        job.work_dir = str(work_dir)
        db.commit()

        def on_stage(stage: str) -> None:
            current = db.get(Job, job_id)
            if not current or current.status == JobStatus.cancelled.value:
                return
            current.stage = stage
            db.commit()

        result = run_ras_docking(
            work_dir=work_dir,
            params=params,
            repo_root=settings.ras_docking_root,
            python_bin=settings.ras_docking_python,
            vina_bin=settings.vina_bin,
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
            job.error_message = (result.error or "RAS docking failed")[:8000]
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


@celery_app.task(bind=True, name="worker.tasks.run_small_molecule_docking_job")
def run_small_molecule_docking_job(self, job_id: str) -> dict:
    db: Session = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job or job.engine != "small_molecule_docking":
            return {"error": "not a small-molecule docking job"}
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

        ligand_path = params.get("ligand_path")
        result = run_small_molecule_docking(
            work_dir=Path(job.work_dir or settings.docking_out_root / job.id),
            receptor=Path(params["receptor_path"]),
            ligand=Path(ligand_path) if ligand_path else None,
            params=params,
            vina_bin=settings.vina_bin,
            gnina_bin=settings.gnina_bin,
            obabel_bin=settings.obabel_bin,
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
            job.error_message = (result.error or "Docking failed")[:8000]
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
