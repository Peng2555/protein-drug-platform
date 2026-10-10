"""GROMACS molecular dynamics task."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.engines import GROMACS_MD_ENGINE
from app.common.job_paths import job_output_dir, write_job_info
from md_runner import run_md_validation
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


def _write_md_job_info(db: Session, job: Job, user: User | None) -> None:
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


@celery_app.task(bind=True, name="worker.tasks.run_md_job")
def run_md_job(self, job_id: str) -> dict:
    db: Session = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return {"error": "job not found"}
        if job.engine != GROMACS_MD_ENGINE:
            return {"error": "not an MD job"}
        if job.status == JobStatus.cancelled.value:
            return {"status": "cancelled"}

        user = db.get(User, job.user_id)
        params = job.params_json or {}
        work_dir = Path(job.work_dir) if job.work_dir else job_output_dir(
            settings.md_out_root, job.name, job.id, job.chains_json
        )
        input_structure = Path(
            params.get("input_structure", work_dir / "00_structure" / "complex.pdb")
        )
        if not input_structure.is_file():
            for candidate in (work_dir / "00_structure").glob("*"):
                if candidate.suffix.lower() in {".cif", ".mmcif", ".pdb"}:
                    input_structure = candidate
                    break

        job.status = JobStatus.running.value
        job.stage = "prep"
        job.started_at = utcnow()
        job.celery_task_id = self.request.id
        job.work_dir = str(work_dir)
        db.commit()
        _write_md_job_info(db, job, user)

        def on_stage(stage: str) -> None:
            j = db.get(Job, job_id)
            if not j or j.status == JobStatus.cancelled.value:
                return
            j.stage = stage
            db.commit()
            _write_md_job_info(db, j, user)

        result = run_md_validation(
            input_structure=input_structure,
            work_dir=work_dir,
            production_ns=float(params.get("production_ns", settings.md_production_ns)),
            replicas=int(params.get("replicas", settings.md_replicas)),
            gpu_id=0,  # worker binds one physical GPU via CUDA_VISIBLE_DEVICES
            antigen_chain=str(params.get("antigen_chain", "A")),
            binder_chain=str(params.get("binder_chain", "H")),
            on_stage=on_stage,
        )

        job = db.get(Job, job_id)
        if not job:
            return {"job_id": job_id, "status": "deleted"}

        job.finished_at = utcnow()
        job.runtime_seconds = result.seconds
        job.stage = result.stage

        if result.status == "ok":
            job.status = JobStatus.done.value
            job.results_json = result.results
            job.structure_path = result.structure_output
            job.error_message = None
        else:
            job.status = JobStatus.failed.value
            job.error_message = (result.error or "MD failed")[:8000]

        _write_md_job_info(db, job, user)
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
