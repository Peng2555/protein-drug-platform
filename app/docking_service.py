"""Generic small-molecule docking job service."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.engines import SMALL_MOLECULE_DOCKING_ENGINE
from app.job_paths import job_output_dir
from app.models import Job, JobStatus
from app.queue_service import dispatch_to_gpu
from worker.tasks import run_small_molecule_docking_job


async def create_and_queue_docking_job(
    db: Session,
    *,
    user_id: str,
    name: str,
    receptor: UploadFile,
    ligand_smiles: str,
    reference_ligand: UploadFile | None,
    params: dict,
) -> Job:
    smiles = ligand_smiles.strip()
    if not smiles:
        raise HTTPException(400, "请填写小分子 SMILES（结构式）")
    if len(smiles) > 4000:
        raise HTTPException(400, "SMILES 过长")
    job = Job(
        user_id=user_id,
        name=name,
        engine=SMALL_MOLECULE_DOCKING_ENGINE,
        status=JobStatus.queued.value,
        stage="queued",
        fasta_text=">docking\n.",
        sequence_hash="small-molecule-docking",
        chains_json={"receptor": 1, "ligand": 1},
        total_length=2,
        use_msa_server=False,
        params_json=params,
    )
    db.add(job)
    db.flush()
    work_dir = job_output_dir(settings.docking_out_root, name, job.id, job.chains_json)
    input_dir = work_dir / "00_input"
    receptor_path = await _save_upload_async(
        receptor, input_dir / f"receptor{Path(receptor.filename or '.pdb').suffix.lower()}",
        {".pdb", ".pdbqt", ".cif", ".mmcif"}, "受体",
    )
    input_dir.mkdir(parents=True, exist_ok=True)
    ligand_path = input_dir / "ligand.smi"
    ligand_path.write_text(smiles + "\n", encoding="utf-8")
    reference_path = None
    if reference_ligand and reference_ligand.filename:
        reference_path = await _save_upload_async(
            reference_ligand,
            input_dir / f"reference_ligand{Path(reference_ligand.filename).suffix.lower()}",
            {".sdf", ".sd", ".mol", ".mol2", ".pdbqt", ".pdb", ".cif", ".mmcif"},
            "参考配体",
        )
    job.work_dir = str(work_dir)
    job.params_json = {
        **params,
        "ligand_smiles": smiles,
        "receptor_path": str(receptor_path),
        "ligand_path": str(ligand_path),
        "reference_ligand_path": str(reference_path) if reference_path else None,
    }
    async_result = dispatch_to_gpu(run_small_molecule_docking_job, job.id)
    job.celery_task_id = async_result.id
    return job


async def _save_upload_async(upload: UploadFile, dest: Path, extensions: set[str], label: str) -> Path:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in extensions:
        raise HTTPException(400, f"{label}格式不支持，可用: {', '.join(sorted(extensions))}")
    content = await upload.read()
    if len(content) < 20:
        raise HTTPException(400, f"{label}文件为空或过小")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return dest
