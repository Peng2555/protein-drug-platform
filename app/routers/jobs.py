"""Job submission and management."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import settings
from app.engines import FOLD_ENGINES
from app.database import get_db
from app.deps import get_current_user
from app.job_paths import default_job_name, remove_job_outputs
from app.job_service import create_and_queue_job, dispatch_job, fasta_from_seqs, sequence_hash
from app.models import Job, JobStatus, User
from app.schemas import JobCreate, JobInterfaceOut, JobListOut, JobOut, JobSequencesOut

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from boltz_runner import parse_fasta_text, validate_boltz_chain_ids

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _seqs_from_body(body: JobCreate) -> dict[str, str]:
    if body.fasta and body.chains:
        raise HTTPException(400, "Provide fasta or chains, not both")
    if body.fasta:
        return parse_fasta_text(body.fasta)
    if body.chains:
        return {c.id.strip(): c.sequence.strip().upper() for c in body.chains}
    raise HTTPException(400, "Provide fasta or chains")


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_job(body: JobCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from boltz_runner import (
        build_boltz_yaml_text,
        chains_meta_from_components,
        polymer_seqs_from_components,
    )

    input_yaml: str | None = None
    complex_payload: dict | None = None

    if body.components:
        components = [c.model_dump() for c in body.components]
        constraints = [c.model_dump() for c in (body.constraints or [])]
        affinity_binder = body.affinity.binder if body.affinity else None
        try:
            input_yaml = build_boltz_yaml_text(
                components,
                constraints=constraints or None,
                affinity_binder=affinity_binder,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

        polymer_seqs = polymer_seqs_from_components(components)
        chains_json = chains_meta_from_components(components)
        if polymer_seqs:
            try:
                validate_boltz_chain_ids(polymer_seqs)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            seqs = polymer_seqs
            fasta_text = fasta_from_seqs(seqs)
        else:
            # 仅配体极少见；仍写占位 FASTA 满足非空列
            seqs = {components[0]["ids"][0]: "X"}
            fasta_text = fasta_from_seqs(seqs)
        total_len = sum(chains_json.values())
        complex_payload = {
            "components": components,
            "constraints": constraints,
            "affinity": {"binder": affinity_binder} if affinity_binder else None,
        }
    else:
        seqs = _seqs_from_body(body)
        chains_json = {k: len(v) for k, v in seqs.items()}
        total_len = sum(chains_json.values())
        fasta_text = fasta_from_seqs(seqs)
        if body.engine == "boltz2":
            try:
                validate_boltz_chain_ids(seqs)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc

    if total_len > settings.max_total_sequence_length:
        raise HTTPException(400, f"Total length {total_len} exceeds limit {settings.max_total_sequence_length}")

    boltz_dump = body.boltz_params.model_dump() if body.engine == "boltz2" and body.boltz_params else None
    if body.engine == "boltz2":
        if boltz_dump is None:
            boltz_dump = {"use_msa_server": body.use_msa_server}
        use_msa = bool(boltz_dump.get("use_msa_server", body.use_msa_server))
        if input_yaml:
            boltz_dump["input_yaml"] = input_yaml
        if complex_payload:
            boltz_dump["complex"] = complex_payload
    else:
        use_msa = False
        # ESMFold2：从 components 导出蛋白 FASTA
        if body.components:
            polymer = polymer_seqs_from_components([c.model_dump() for c in body.components])
            if not polymer:
                raise HTTPException(400, "ESMFold2 仅支持蛋白/核酸序列，请至少添加一条 polymer 链")
            seqs = polymer
            fasta_text = fasta_from_seqs(seqs)
            chains_json = {k: len(v) for k, v in seqs.items()}
            total_len = sum(chains_json.values())

    job = create_and_queue_job(
        db,
        user_id=user.id,
        name=body.name.strip() if body.name and body.name.strip() else default_job_name(chains_json),
        fasta_text=fasta_text,
        chains_json=chains_json,
        total_length=total_len,
        seq_hash=sequence_hash(seqs),
        use_msa_server=use_msa,
        engine=body.engine,
        boltz_params=boltz_dump if body.engine == "boltz2" else None,
        esmfold_params=body.esmfold_params.model_dump() if body.engine == "esmfold2" and body.esmfold_params else None,
        defer_dispatch=True,
    )
    db.commit()
    dispatch_job(db, job)
    db.commit()
    db.refresh(job)
    return JobOut.model_validate(job)


@router.post("/submit", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def create_job_multipart(
    fasta: str = Form(...),
    name: str | None = Form(default=None),
    engine: str = Form(default="boltz2"),
    use_msa_server: bool = Form(default=True),
    reference_pdb: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Submit FASTA with optional reference PDB for DockQ evaluation."""
    seqs = parse_fasta_text(fasta.strip())
    total_len = sum(len(s) for s in seqs.values())
    if total_len > settings.max_total_sequence_length:
        raise HTTPException(400, f"Total length {total_len} exceeds limit {settings.max_total_sequence_length}")
    if engine == "boltz2":
        try:
            validate_boltz_chain_ids(seqs)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    job = create_and_queue_job(
        db,
        user_id=user.id,
        name=name.strip() if name and name.strip() else default_job_name({k: len(v) for k, v in seqs.items()}),
        fasta_text=fasta_from_seqs(seqs),
        chains_json={k: len(v) for k, v in seqs.items()},
        total_length=total_len,
        seq_hash=sequence_hash(seqs),
        use_msa_server=use_msa_server if engine == "boltz2" else False,
        engine=engine,
        defer_dispatch=True,
    )

    if reference_pdb and reference_pdb.filename:
        suffix = Path(reference_pdb.filename).suffix.lower()
        if suffix not in {".pdb", ".ent"}:
            raise HTTPException(400, "Reference structure must be .pdb")
        ref_dir = settings.boltz2_out_root / "_references" / job.id
        ref_dir.mkdir(parents=True, exist_ok=True)
        ref_path = ref_dir / "native.pdb"
        content = await reference_pdb.read()
        if len(content) < 100:
            raise HTTPException(400, "Reference PDB file too small")
        ref_path.write_bytes(content)
        job.params_json = {
            **(job.params_json or {}),
            "reference_pdb": str(ref_path),
            "compute_dockq": True,
        }

    db.commit()
    dispatch_job(db, job)
    db.commit()
    db.refresh(job)
    return JobOut.model_validate(job)


@router.get("", response_model=JobListOut)
def list_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    singles_only: bool = Query(False, description="Exclude jobs that belong to a batch"),
):
    q = select(Job).where(Job.user_id == user.id, Job.engine.in_(FOLD_ENGINES))
    count_q = select(func.count()).select_from(Job).where(Job.user_id == user.id, Job.engine.in_(FOLD_ENGINES))
    if singles_only:
        q = q.where(Job.batch_id.is_(None))
        count_q = count_q.where(Job.batch_id.is_(None))
    total = db.scalar(count_q) or 0
    rows = db.scalars(q.order_by(Job.created_at.desc()).limit(limit).offset(offset)).all()
    return JobListOut(items=[JobOut.model_validate(j) for j in rows], total=total)


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(404, "Job not found")
    return JobOut.model_validate(job)


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(404, "Job not found")
    if job.status not in (JobStatus.queued.value, JobStatus.running.value):
        raise HTTPException(409, f"Cannot cancel job in status {job.status}")
    job.status = JobStatus.cancelled.value
    db.commit()
    db.refresh(job)
    return JobOut.model_validate(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(404, "Job not found")

    if job.status in (JobStatus.queued.value, JobStatus.running.value):
        job.status = JobStatus.cancelled.value
        db.commit()
        if job.celery_task_id:
            celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")

    remove_job_outputs(
        settings.boltz2_out_root,
        job.id,
        job.name,
        job.chains_json,
        job.work_dir,
    )
    db.delete(job)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{job_id}/sequences", response_model=JobSequencesOut)
def get_job_sequences(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.cdr_annotation import annotate_fasta

    job = db.get(Job, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(404, "Job not found")
    chains = annotate_fasta(job.fasta_text)
    return JobSequencesOut(job_id=job_id, chains=chains)


@router.get("/{job_id}/interface", response_model=JobInterfaceOut)
def get_job_interface(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.interface_service import build_job_interface_analysis

    job = db.get(Job, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatus.done.value:
        raise HTTPException(409, f"Job status: {job.status}")
    try:
        data = build_job_interface_analysis(job, db)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"界面分析失败: {exc}") from exc
    return JobInterfaceOut.model_validate(data)


@router.get("/{job_id}/structure")
def download_structure(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatus.done.value:
        raise HTTPException(409, f"Job status: {job.status}")

    cif: Path | None = None
    if job.structure_path:
        cif = Path(job.structure_path)
    elif job.work_dir:
        cif = Path(job.work_dir) / "pred.cif"
    else:
        cif = settings.boltz2_out_root / job.id / "pred.cif"
    if not cif.is_file() and job.work_dir:
        cif = Path(job.work_dir) / "pred.cif"
    if not cif.is_file():
        legacy = settings.boltz2_out_root / job.id / "pred.cif"
        if legacy.is_file():
            cif = legacy
    if not cif.is_file():
        raise HTTPException(404, f"Structure file not found: {cif}")
    # Do not put raw non-ASCII names in Content-Disposition; HTTP headers are latin-1.
    # Starlette quotes filename*=utf-8''… when the name is not ASCII.
    return FileResponse(
        cif,
        filename=f"{job.name or job.id}.cif",
        media_type="chemical/x-mmcif",
    )
