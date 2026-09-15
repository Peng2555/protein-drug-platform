"""Structure prediction task."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.job_paths import job_output_dir, write_job_info
from boltz_runner import fold_sequences as boltz_fold_sequences, parse_fasta_text
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


def _needs_pdockq(job: Job) -> bool:
    """Recompute when missing or stuck at 0 (ESMFold subprocess often wrote 0 before worker fix)."""
    if len(job.chains_json or {}) <= 1:
        return False
    return job.pdockq is None or job.pdockq == 0.0


def _ensure_pdockq(work_dir: Path, job: Job) -> None:
    """Compute pDockQ in the worker env (has gemmi); ESMFold subprocess lacks it."""
    if not _needs_pdockq(job):
        return
    try:
        from pdockq_runner import compute_pdockq_from_boltz_dir

        pq = compute_pdockq_from_boltz_dir(work_dir)
        if pq.pdockq is None and pq.pdockq2 is None:
            return
        if pq.pdockq is not None:
            job.pdockq = pq.pdockq
        if pq.pdockq2 is not None:
            job.pdockq2 = pq.pdockq2
        metrics_path = work_dir / "metrics.json"
        if metrics_path.is_file() and job.pdockq is not None:
            payload = json.loads(metrics_path.read_text(encoding="utf-8"))
            payload["pdockq"] = job.pdockq
            if job.pdockq2 is not None:
                payload["pdockq2"] = job.pdockq2
            if job.confidence_score is None:
                iptm = payload.get("iptm", job.iptm)
                ptm = payload.get("ptm", job.ptm)
                n_chains = len(job.chains_json or {})
                if n_chains <= 1 or payload.get("has_interface") is False:
                    if ptm is not None:
                        job.confidence_score = float(ptm)
                        payload["confidence_score"] = job.confidence_score
                elif iptm is not None and ptm is not None:
                    job.confidence_score = 0.8 * float(iptm) + 0.2 * float(ptm)
                    payload["confidence_score"] = job.confidence_score
                elif iptm is not None:
                    job.confidence_score = float(iptm)
                    payload["confidence_score"] = job.confidence_score
            metrics_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass


def _run_structure_fold(job: Job, seqs: dict[str, str], work_dir: Path):
    common = {
        "seqs": seqs,
        "out_root": settings.boltz2_out_root,
        "job_id": work_dir.name,
        "skip_if_done": False,
    }
    params = job.params_json or {}
    if job.engine == "esmfold2":
        from esmfold_runner import fold_sequences as esmfold_fold_sequences

        return esmfold_fold_sequences(
            **common,
            num_loops=params.get("num_loops"),
            num_sampling_steps=params.get("num_sampling_steps"),
            num_diffusion_samples=params.get("num_diffusion_samples"),
            seed=params.get("seed"),
        )
    return boltz_fold_sequences(
        **common,
        use_msa_server=bool(params.get("use_msa_server", job.use_msa_server)),
        recycling_steps=int(params.get("recycling_steps", 3)),
        sampling_steps=int(params.get("sampling_steps", 200)),
        diffusion_samples=int(params.get("diffusion_samples", 1)),
        max_parallel_samples=params.get("max_parallel_samples", 5),
        step_scale=params.get("step_scale"),
        seed=params.get("seed"),
        output_format=str(params.get("output_format") or "mmcif"),
        model=str(params.get("model") or "boltz2"),
        method=params.get("method"),
        use_potentials=bool(params.get("use_potentials", False)),
        msa_pairing_strategy=str(params.get("msa_pairing_strategy") or "greedy"),
        max_msa_seqs=int(params.get("max_msa_seqs", 8192)),
        subsample_msa=bool(params.get("subsample_msa", False)),
        num_subsampled_msa=int(params.get("num_subsampled_msa", 1024)),
        write_full_pae=bool(params.get("write_full_pae", False)),
        write_full_pde=bool(params.get("write_full_pde", False)),
        write_embeddings=bool(params.get("write_embeddings", False)),
        write_pdb=False,
        yaml_text=params.get("input_yaml"),
    )


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
        job.started_at = utcnow()
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

        job.finished_at = utcnow()
        job.runtime_seconds = result.seconds

        if result.status == "ok":
            job.status = JobStatus.done.value
            job.iptm = result.iptm
            job.ptm = result.ptm
            if len(job.chains_json or {}) <= 1 or result.num_chains <= 1:
                job.iptm = None
            job.confidence_score = result.confidence_score
            if job.iptm is None and job.ptm is not None and job.confidence_score is None:
                job.confidence_score = job.ptm
            job.complex_plddt = result.complex_plddt
            job.pdockq = result.pdockq
            job.pdockq2 = result.pdockq2
            job.structure_path = result.pred_cif or result.pred_pdb
            job.error_message = None
            _ensure_pdockq(work_dir, job)

            metrics_path = work_dir / "metrics.json"
            if metrics_path.is_file():
                try:
                    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
                    job.results_json = {
                        **(job.results_json or {}),
                        "has_interface": metrics.get("has_interface"),
                        "n_samples": metrics.get("n_samples"),
                        "selected_model": metrics.get("selected_model"),
                        "iptm_median": metrics.get("iptm_median"),
                        "iptm_max": metrics.get("iptm_max"),
                        "samples": metrics.get("samples"),
                    }
                except json.JSONDecodeError:
                    pass

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
            job.finished_at = utcnow()
            db.commit()
        raise
    finally:
        db.close()
