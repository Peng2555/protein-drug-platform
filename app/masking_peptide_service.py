"""Masking peptide (RFdiffusion + MPNN) workflow jobs."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.engines import MASKING_PEPTIDE_ENGINE, is_fold_engine
from app.job_paths import job_output_dir, sanitize_label
from app.md_service import resolve_structure_path
from app.models import Job, JobStatus
from app.queue_service import dispatch_to_gpu
from worker.tasks import run_masking_peptide_job

ALLOWED_STRUCT = {".pdb", ".cif", ".mmcif"}
DEFAULT_HOTSPOTS = ["H35", "H47", "H50", "H104", "H110"]


async def save_structure_upload(upload: UploadFile, dest: Path) -> Path:
    suffix = Path(upload.filename or "antibody.pdb").suffix.lower()
    if suffix not in ALLOWED_STRUCT:
        raise HTTPException(400, "结构文件需为 .pdb / .cif / .mmcif")
    if suffix == ".mmcif":
        suffix = ".cif"
        dest = dest.with_suffix(".cif")
    content = await upload.read()
    if len(content) < 80:
        raise HTTPException(400, "上传的结构文件太小或为空")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return dest


def _extract_chain_pdb(src: Path, chain_id: str, dest: Path) -> None:
    lines: list[str] = []
    for line in src.read_text(errors="replace").splitlines():
        if line.startswith(("ATOM", "HETATM")) and len(line) >= 22:
            if line[21:22].strip() == chain_id:
                lines.append(line)
    if not lines:
        raise HTTPException(400, f"结构中未找到链 {chain_id}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines) + "\nEND\n", encoding="utf-8")


def _resolve_antibody_pdb(
    db: Session,
    user_id: str,
    *,
    antibody_path: Path | None,
    fold_job_id: str | None,
    target_chain: str,
) -> Path:
    if antibody_path and antibody_path.is_file():
        return antibody_path
    if not fold_job_id:
        raise HTTPException(400, "请上传抗体单链 PDB，或选择 Boltz2 折叠任务")
    parent = db.get(Job, fold_job_id)
    if not parent or parent.user_id != user_id:
        raise HTTPException(404, "折叠任务不存在")
    if parent.status != JobStatus.done.value or not is_fold_engine(parent.engine):
        raise HTTPException(400, "请选择已完成的结构预测任务")
    complex_path = resolve_structure_path(parent)
    tmp = complex_path.parent / f"_extract_{target_chain}_{uuid.uuid4().hex[:8]}.pdb"
    _extract_chain_pdb(complex_path, target_chain, tmp)
    return tmp


def _parse_hotspots(raw: list[str] | str | None) -> list[str]:
    if not raw:
        return list(DEFAULT_HOTSPOTS)
    if isinstance(raw, str):
        parts = re.split(r"[\s,;]+", raw.strip())
    else:
        parts = raw
    out = [p.strip().upper() for p in parts if p and p.strip()]
    return out or list(DEFAULT_HOTSPOTS)


def _bootstrap_campaign(
    *,
    name: str,
    antibody_pdb: Path,
    params: dict,
) -> Path:
    slug = sanitize_label(name or "masking_peptide", max_len=32)
    campaign = settings.masking_peptide_out_root / f"{slug}__{uuid.uuid4().hex[:8]}"
    campaign.mkdir(parents=True, exist_ok=False)
    for sub in ("02_structures", "03_hotspots", "04_rfdiffusion", "05_mpnn", "logs", "exports", "input"):
        (campaign / sub).mkdir(parents=True, exist_ok=True)

    dest = campaign / "02_structures" / "antibody_H.pdb"
    shutil.copy2(antibody_pdb, dest)
    shutil.copy2(antibody_pdb, campaign / "input" / "antibody.pdb")

    (campaign / "03_hotspots" / "hotspots.json").write_text(
        json.dumps({"hotspot_res": params["hotspot_res"]}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (campaign / "campaign.yaml").write_text(
        json.dumps({"name": name, "slug": slug, **params}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return campaign


def _runner_params(params: dict) -> dict:
    gpus = params.get("gpus")
    if not gpus:
        n = max(1, int(settings.celery_gpu_count or 4))
        gpus = ",".join(str(i) for i in range(n))
    return {
        **params,
        "gpus": gpus,
        "rfdiffusion_root": str(settings.rfdiffusion_root),
        "rf_py": settings.se3nv_python,
        "se3_py": settings.se3nv_python,
        "mpnn_relax_script": str(
            settings.masking_peptide_project_root / "scripts" / "run_mpnn_relax_round.py"
        ),
    }


def create_and_queue_masking_peptide_job(
    db: Session,
    *,
    user_id: str,
    name: str,
    antibody_pdb: Path,
    params: dict,
    parent_job_id: str | None = None,
    extracted_tmp: Path | None = None,
) -> Job:
    if not settings.masking_peptide_project_root.is_dir():
        raise HTTPException(
            503,
            f"多肽遮蔽项目路径不存在: {settings.masking_peptide_project_root}",
        )
    mpnn_script = settings.masking_peptide_project_root / "scripts" / "run_mpnn_relax_round.py"
    if not mpnn_script.is_file():
        raise HTTPException(503, f"缺少 MPNN 脚本: {mpnn_script}")

    campaign_dir = _bootstrap_campaign(name=name, antibody_pdb=antibody_pdb, params=params)
    if extracted_tmp and extracted_tmp.is_file():
        extracted_tmp.unlink(missing_ok=True)

    runner_params = _runner_params(params)
    job = Job(
        user_id=user_id,
        name=name,
        engine=MASKING_PEPTIDE_ENGINE,
        status=JobStatus.queued.value,
        stage="queued",
        fasta_text=">masking_peptide\n.",
        sequence_hash=hashlib.sha256(str(antibody_pdb).encode()).hexdigest(),
        chains_json={"antibody": 1, "peptide_designs": params.get("total_designs", 200)},
        total_length=int(params.get("total_designs") or 200),
        use_msa_server=False,
        parent_job_id=parent_job_id,
        params_json=runner_params,
        work_dir=str(campaign_dir),
    )
    db.add(job)
    db.flush()
    async_result = dispatch_to_gpu(run_masking_peptide_job, job.id)
    job.celery_task_id = async_result.id
    return job


def prepare_from_body(
    db: Session,
    user_id: str,
    body,
    *,
    antibody_upload: Path | None = None,
) -> tuple[Path, dict, str | None, Path | None]:
    name = body.name.strip() if body.name and body.name.strip() else "masking_peptide"
    target_chain = (body.target_chain or "H").strip() or "H"
    extracted_tmp: Path | None = None

    if antibody_upload:
        ab_path = antibody_upload
    elif body.fold_job_id:
        ab_path = _resolve_antibody_pdb(
            db,
            user_id,
            antibody_path=None,
            fold_job_id=body.fold_job_id,
            target_chain=target_chain,
        )
        extracted_tmp = ab_path
    else:
        raise HTTPException(400, "请上传抗体 PDB 或选择 fold 任务")

    params = {
        "hotspot_res": _parse_hotspots(body.hotspot_res),
        "target_chain": target_chain,
        "peptide_length": body.peptide_length or "12-18",
        "total_designs": int(body.total_designs),
        "mpnn_rounds": int(body.mpnn_rounds),
        "skip_backbone": bool(body.skip_backbone),
        "relax_jobs": int(body.relax_jobs),
        "fold_job_id": body.fold_job_id,
        "entry_mode": "fold_job" if body.fold_job_id else "upload",
    }
    parent = body.fold_job_id if body.fold_job_id else None
    return ab_path, params, parent, extracted_tmp
