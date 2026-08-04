"""IgGM affinity maturation job creation and helpers."""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.engines import is_fold_engine
from app.job_paths import job_output_dir
from app.job_service import fasta_from_seqs, sequence_hash
from app.md_service import resolve_structure_path
from app.models import Job, JobStatus
from app.queue_service import dispatch_to_gpu
from app.schemas import IgGMParams, MaturationJobCreate

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from boltz_runner import parse_fasta_text, validate_boltz_chain_ids
from iggm_mask_builder import build_maturation_fastas

from worker.tasks import run_maturation_job


def validate_maturation_fasta(
    fasta_text: str,
    binder_chain: str,
    antigen_chain: str,
    cdr_mask: list[str] | None = None,
) -> dict[str, str]:
    seqs = parse_fasta_text(fasta_text.strip())
    if len(seqs) < 2:
        raise HTTPException(400, "FASTA must contain binder and antigen chains (≥2 sequences)")
    try:
        build_maturation_fastas(
            seqs,
            binder_chain_id=binder_chain,
            antigen_chain_id=antigen_chain,
            cdr_mask=cdr_mask or ["CDR-H3"],
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return seqs


def build_params_json(body: MaturationJobCreate) -> dict:
    iggm = (body.iggm or IgGMParams()).model_dump()
    params: dict = {
        "structure_source": body.structure_source,
        "fold_job_id": body.fold_job_id,
        "binder_chain_id": body.binder_chain_id,
        "antigen_chain_id": body.antigen_chain_id,
        "cdr_mask": body.cdr_mask,
        "iggm": iggm,
        **iggm,
    }
    if body.structure_source == "boltz2":
        params["fold_params"] = body.fold_params or {
            "use_msa_server": body.use_msa_server,
            "recycling_steps": 3,
            "sampling_steps": 200,
            "diffusion_samples": 1,
        }
    elif body.structure_source == "esmfold2":
        params["fold_params"] = body.fold_params or {
            "num_loops": 10,
            "num_sampling_steps": 68,
            "num_diffusion_samples": 5,
            "seed": 0,
        }
    return params


def resolve_structure_for_maturation(db: Session, user_id: str, body: MaturationJobCreate) -> Path | None:
    if body.structure_source == "upload":
        return None
    if body.structure_source == "fold_job":
        if not body.fold_job_id:
            raise HTTPException(400, "fold_job_id required when structure_source=fold_job")
        parent = db.get(Job, body.fold_job_id)
        if not parent or parent.user_id != user_id:
            raise HTTPException(404, "Fold job not found")
        if not is_fold_engine(parent.engine):
            raise HTTPException(400, "Selected job is not a structure prediction job")
        if parent.status != JobStatus.done.value:
            raise HTTPException(409, f"Fold job status: {parent.status}")
        return resolve_structure_path(parent)
    if body.structure_source in ("boltz2", "esmfold2"):
        return None
    raise HTTPException(400, f"Unknown structure_source: {body.structure_source}")


def create_and_queue_maturation_job(
    db: Session,
    *,
    user_id: str,
    name: str,
    fasta_text: str,
    chains_json: dict[str, int],
    params_json: dict,
    structure_path: Path | None = None,
    fold_job_id: str | None = None,
) -> Job:
    from app.job_service import _check_user_queue_cap

    _check_user_queue_cap(db, user_id, "iggm_maturation")

    job = Job(
        user_id=user_id,
        parent_job_id=fold_job_id,
        name=name,
        engine="iggm_maturation",
        status=JobStatus.queued.value,
        stage="queued",
        fasta_text=fasta_text,
        sequence_hash=sequence_hash(parse_fasta_text(fasta_text)),
        chains_json=chains_json,
        total_length=sum(chains_json.values()),
        use_msa_server=False,
        params_json=params_json,
    )
    db.add(job)
    db.flush()

    work_dir = job_output_dir(settings.maturation_out_root, job.name, job.id, chains_json)
    work_dir.mkdir(parents=True, exist_ok=True)

    if structure_path and structure_path.is_file():
        struct_dir = work_dir / "input"
        struct_dir.mkdir(parents=True, exist_ok=True)
        dest = struct_dir / f"upload{structure_path.suffix.lower()}"
        if structure_path.resolve() != dest.resolve():
            shutil.copy2(structure_path, dest)
        job.params_json = {**(job.params_json or {}), "uploaded_structure": str(dest)}

    job.work_dir = str(work_dir)
    async_result = dispatch_to_gpu(run_maturation_job, job.id)
    job.celery_task_id = async_result.id
    return job


async def save_uploaded_structure(upload: UploadFile, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or "input.pdb").suffix.lower()
    if suffix not in {".cif", ".mmcif", ".pdb", ".ent"}:
        raise HTTPException(400, "Upload .pdb or .cif structure file")
    dest = dest_dir / f"upload{suffix}"
    content = await upload.read()
    if len(content) < 100:
        raise HTTPException(400, "Structure file too small or empty")
    dest.write_bytes(content)
    return dest


def prepare_maturation_from_body(
    db: Session,
    user_id: str,
    body: MaturationJobCreate,
    *,
    uploaded_structure: Path | None = None,
) -> tuple[str, dict[str, int], dict, Path | None]:
    seqs = validate_maturation_fasta(
        body.fasta, body.binder_chain_id, body.antigen_chain_id, body.cdr_mask
    )
    if body.structure_source in ("boltz2", "esmfold2"):
        normalized = {body.binder_chain_id: seqs[body.binder_chain_id], body.antigen_chain_id: seqs[body.antigen_chain_id]}
        try:
            validate_boltz_chain_ids({"H": normalized[body.binder_chain_id], "A": normalized[body.antigen_chain_id]})
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    structure_path = uploaded_structure
    if body.structure_source == "upload" and not structure_path:
        raise HTTPException(400, "Structure file required for upload mode")
    if body.structure_source == "fold_job":
        structure_path = resolve_structure_for_maturation(db, user_id, body)

    params = build_params_json(body)
    chains_json = {k: len(v) for k, v in seqs.items()}
    fasta_text = fasta_from_seqs(seqs)
    return fasta_text, chains_json, params, structure_path
