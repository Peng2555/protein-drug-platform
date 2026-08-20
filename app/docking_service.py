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

LIGAND_FILE_EXTS = {".sdf", ".sd", ".mol", ".mol2", ".pdb", ".pdbqt", ".smi", ".smiles"}


def _smiles_from_ligand_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".smi", ".smiles"}:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            token = line.strip().split()[0] if line.strip() else ""
            if token and not token.startswith("#"):
                return token
        raise HTTPException(400, "配体 SMILES 文件为空")
    try:
        from rdkit import Chem

        mol = None
        if suffix in {".sdf", ".sd"}:
            mol = next(iter(Chem.SDMolSupplier(str(path), removeHs=False)), None)
        elif suffix == ".mol2":
            mol = Chem.MolFromMol2File(str(path), removeHs=False)
        elif suffix == ".mol":
            mol = Chem.MolFromMolFile(str(path), removeHs=False)
        elif suffix in {".pdb", ".pdbqt"}:
            mol = Chem.MolFromPDBFile(str(path), removeHs=False)
        if mol is None:
            raise ValueError("RDKit 无法解析配体文件")
        smiles = Chem.MolToSmiles(mol)
        if not smiles:
            raise ValueError("无法从配体文件生成 SMILES")
        return smiles
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"配体文件解析失败: {exc}") from exc


async def create_and_queue_docking_job(
    db: Session,
    *,
    user_id: str,
    name: str,
    receptor: UploadFile,
    ligand_smiles: str,
    reference_ligand: UploadFile | None,
    params: dict,
    ligand_file: UploadFile | None = None,
) -> Job:
    smiles = (ligand_smiles or "").strip()
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
    ligand_upload_path = None
    if ligand_file and ligand_file.filename:
        ligand_upload_path = await _save_upload_async(
            ligand_file,
            input_dir / f"ligand_upload{Path(ligand_file.filename).suffix.lower()}",
            LIGAND_FILE_EXTS,
            "配体",
        )
        if not smiles:
            smiles = _smiles_from_ligand_file(ligand_upload_path)
    if not smiles:
        raise HTTPException(400, "请填写小分子 SMILES（结构式），或上传可解析的配体文件")
    if len(smiles) > 4000:
        raise HTTPException(400, "SMILES 过长")
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
    # auto_blind 忽略参考配体定盒；reference 模式强制用参考配体
    mode = str(params.get("dock_mode") or "auto_blind")
    if mode == "auto_blind":
        reference_path = None
    job.work_dir = str(work_dir)
    job.params_json = {
        **params,
        "ligand_smiles": smiles,
        "receptor_path": str(receptor_path),
        "ligand_path": str(ligand_path),
        "ligand_upload_path": str(ligand_upload_path) if ligand_upload_path else None,
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
    if len(content) < 20 and suffix not in {".smi", ".smiles"}:
        raise HTTPException(400, f"{label}文件为空或过小")
    if len(content) < 1:
        raise HTTPException(400, f"{label}文件为空或过小")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return dest
