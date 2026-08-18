"""Standalone synthesis candidate selection (IgGM table × SHM table)."""

from __future__ import annotations

import hashlib
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.engines import SYNTHESIS_ENGINE
from app.job_paths import job_output_dir
from app.models import Job, JobStatus

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from iggm_shm_matcher import ShmMatchParams, run_iggm_shm_match
from iggm_synthesis_order import SynthesisOrderParams, build_synthesis_order


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _input_hash(*paths: Path) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


async def save_table_upload(upload: UploadFile, dest_dir: Path, stem: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or f"{stem}.csv").suffix.lower()
    if suffix not in {".csv", ".tsv", ".xlsx", ".xls"}:
        raise HTTPException(400, f"{stem} 支持 .csv / .tsv / .xlsx")
    dest = dest_dir / f"{stem}{suffix}"
    content = await upload.read()
    if len(content) < 5:
        raise HTTPException(400, f"{stem} 文件过小或为空")
    dest.write_bytes(content)
    return dest


async def save_fasta_upload(upload: UploadFile, dest_dir: Path, stem: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or f"{stem}.fasta").suffix.lower()
    if suffix not in {".fasta", ".fa", ".faa"}:
        raise HTTPException(400, f"{stem} 请上传 .fasta 文件")
    dest = dest_dir / f"{stem}{suffix}"
    content = await upload.read()
    if len(content) < 10:
        raise HTTPException(400, f"{stem} 文件过小或为空")
    dest.write_bytes(content)
    return dest


def run_and_record_synthesis_job(
    db: Session,
    *,
    user_id: str,
    name: str | None,
    shm_path: Path,
    iggm_path: Path,
    origin_path: Path | None,
    match_params: ShmMatchParams,
    order_params: SynthesisOrderParams,
) -> Job:
    hash_paths = [shm_path, iggm_path]
    if origin_path:
        hash_paths.append(origin_path)

    job = Job(
        user_id=user_id,
        name=(name.strip() if name and name.strip() else None) or f"synthesis_{shm_path.stem}",
        engine=SYNTHESIS_ENGINE,
        status=JobStatus.running.value,
        stage="match",
        fasta_text=">synthesis\nN",
        sequence_hash=_input_hash(*hash_paths),
        chains_json={"synthesis": 1},
        total_length=1,
        use_msa_server=False,
        params_json={
            "min_seq_count": match_params.min_seq_count,
            "min_extra_count": order_params.min_extra_count,
            "v_gene": match_params.v_gene,
            "chain_id": match_params.chain_id,
            "shm_file": shm_path.name,
            "iggm_file": iggm_path.name,
            "origin_file": origin_path.name if origin_path else None,
        },
        started_at=_utcnow(),
    )
    db.add(job)
    db.flush()

    work_dir = job_output_dir(settings.synthesis_out_root, job.name, job.id, job.chains_json)
    work_dir.mkdir(parents=True, exist_ok=True)
    input_dir = work_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    shm_dest = input_dir / shm_path.name
    iggm_dest = input_dir / iggm_path.name
    copies: list[tuple[Path, Path]] = [
        (shm_path, shm_dest),
        (iggm_path, iggm_dest),
    ]
    origin_dest = None
    if origin_path:
        origin_dest = input_dir / origin_path.name
        copies.append((origin_path, origin_dest))

    for src, dest in copies:
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)

    out_dir = work_dir / "results"
    try:
        job.stage = "match"
        match_result = run_iggm_shm_match(
            iggm_table=iggm_dest,
            shm_table=shm_dest,
            out_dir=out_dir,
            params=match_params,
            origin_fasta=origin_dest,
        )

        job.stage = "order"
        order_result = build_synthesis_order(
            match_result["matched_csv"],
            out_dir,
            params=order_params,
            parent_cdr3=match_result.get("parent_cdr3"),
            parent_v_gene=match_result.get("parent_v_gene"),
        )

        result = {**match_result, **order_result}
        job.status = JobStatus.done.value
        job.stage = "done"
        job.results_json = result
        job.error_message = None
    except Exception as exc:
        job.status = JobStatus.failed.value
        job.stage = "failed"
        job.error_message = str(exc)[:8000]
        job.results_json = None

    job.work_dir = str(work_dir)
    job.finished_at = _utcnow()
    if job.started_at:
        job.runtime_seconds = (job.finished_at - job.started_at).total_seconds()
    return job
