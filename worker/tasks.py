"""Celery tasks for structure prediction."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import settings
from app.database import SessionLocal
from app.job_paths import job_output_dir, write_job_info
from app.models import Job, JobStatus, User
from boltz_runner import fold_sequences as boltz_fold_sequences, parse_fasta_text
from md_runner import run_md_validation


def _ensure_pdockq(work_dir: Path, job: Job) -> None:
    """Compute pDockQ in the worker env (has gemmi); ESMFold subprocess lacks it."""
    if job.pdockq is not None:
        return
    try:
        from pdockq_runner import compute_pdockq_from_boltz_dir

        pq = compute_pdockq_from_boltz_dir(work_dir)
        if pq.pdockq is None and pq.pdockq2 is None:
            return
        job.pdockq = pq.pdockq
        job.pdockq2 = pq.pdockq2
        metrics_path = work_dir / "metrics.json"
        if metrics_path.is_file():
            payload = json.loads(metrics_path.read_text(encoding="utf-8"))
            if job.pdockq is not None:
                payload["pdockq"] = job.pdockq
            if job.pdockq2 is not None:
                payload["pdockq2"] = job.pdockq2
            metrics_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _run_structure_fold(job: Job, seqs: dict[str, str], work_dir: Path):
    common = {
        "seqs": seqs,
        "out_root": settings.boltz2_out_root,
        "job_id": work_dir.name,
        "skip_if_done": False,
    }
    if job.engine == "esmfold2":
        from esmfold_runner import fold_sequences as esmfold_fold_sequences

        params = job.params_json or {}
        return esmfold_fold_sequences(
            **common,
            num_loops=params.get("num_loops"),
            num_sampling_steps=params.get("num_sampling_steps"),
            num_diffusion_samples=params.get("num_diffusion_samples"),
            seed=params.get("seed"),
        )
    return boltz_fold_sequences(**common, use_msa_server=job.use_msa_server, write_pdb=False)


@celery_app.task(bind=True, name="worker.tasks.run_fold_job", max_retries=5)
def run_fold_job(self, job_id: str) -> dict:
    db: Session = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            if self.request.retries < self.max_retries:
                raise self.retry(countdown=2, exc=RuntimeError(f"job not found yet: {job_id}"))
            return {"error": "job not found"}
        if job.status == JobStatus.cancelled.value:
            return {"status": "cancelled"}

        job.status = JobStatus.running.value
        job.started_at = _utcnow()
        job.celery_task_id = self.request.id
        db.commit()

        seqs = parse_fasta_text(job.fasta_text)
        user = db.get(User, job.user_id)
        work_dir = job_output_dir(settings.boltz2_out_root, job.name, job.id, job.chains_json)
        job.work_dir = str(work_dir)
        db.commit()

        write_job_info(
            work_dir,
            job_id=job.id,
            name=job.name,
            username=user.username if user else None,
            status=job.status,
            chains_json=job.chains_json,
            engine=job.engine,
            created_at=job.created_at,
            started_at=job.started_at,
        )

        result = _run_structure_fold(job, seqs, work_dir)

        job.finished_at = _utcnow()
        job.runtime_seconds = result.seconds

        if result.status == "ok":
            job.status = JobStatus.done.value
            job.iptm = result.iptm
            job.ptm = result.ptm
            job.confidence_score = result.confidence_score
            job.complex_plddt = result.complex_plddt
            job.pdockq = result.pdockq
            job.pdockq2 = result.pdockq2
            job.structure_path = result.pred_cif
            job.error_message = None
            _ensure_pdockq(work_dir, job)

            params = job.params_json or {}
            ref_path = params.get("reference_pdb")
            if params.get("compute_dockq") and ref_path and result.pred_cif:
                try:
                    from dockq_runner import cif_to_pdb, dockq_score

                    pred_pdb = work_dir / "pred.pdb"
                    cif_to_pdb(Path(result.pred_cif), pred_pdb)
                    dq = dockq_score(pred_pdb, Path(ref_path))
                    job.dockq = dq.get("dockq")
                    if dq.get("dockq") is None and dq.get("error"):
                        job.error_message = f"DockQ failed: {dq['error'][:500]}"
                except Exception as exc:
                    job.error_message = f"DockQ failed: {exc}"[:800]
        else:
            job.status = JobStatus.failed.value
            job.error_message = (result.error or "unknown error")[:8000]

        if not db.get(Job, job_id):
            return {"job_id": job_id, "status": "deleted"}

        write_job_info(
            work_dir,
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
            pdockq=job.pdockq,
            pdockq2=job.pdockq2,
            runtime_seconds=job.runtime_seconds,
            error_message=job.error_message,
        )
        if job.pdockq is not None or job.pdockq2 is not None or job.dockq is not None:
            payload = json.loads((work_dir / "job_info.json").read_text(encoding="utf-8"))
            if job.pdockq is not None:
                payload["pdockq"] = job.pdockq
            if job.pdockq2 is not None:
                payload["pdockq2"] = job.pdockq2
            if job.dockq is not None:
                payload["dockq"] = job.dockq
            (work_dir / "job_info.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )

        db.commit()
        return {"job_id": job_id, "status": job.status}

    except Exception as exc:
        if job := db.get(Job, job_id):
            job.status = JobStatus.failed.value
            job.error_message = str(exc)[:8000]
            job.finished_at = _utcnow()
            db.commit()
        raise
    finally:
        db.close()


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
        if job.engine != "gromacs_md":
            return {"error": "not an MD job"}
        if job.status == JobStatus.cancelled.value:
            return {"status": "cancelled"}

        user = db.get(User, job.user_id)
        params = job.params_json or {}
        work_dir = Path(job.work_dir) if job.work_dir else job_output_dir(
            settings.md_out_root, job.name, job.id, job.chains_json
        )
        input_structure = Path(params.get("input_structure", work_dir / "00_structure" / "complex.pdb"))
        if not input_structure.is_file():
            for candidate in (work_dir / "00_structure").glob("*"):
                if candidate.suffix.lower() in {".cif", ".mmcif", ".pdb"}:
                    input_structure = candidate
                    break

        job.status = JobStatus.running.value
        job.stage = "prep"
        job.started_at = _utcnow()
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

        job.finished_at = _utcnow()
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
            job.finished_at = _utcnow()
            db.commit()
        raise
    finally:
        db.close()
