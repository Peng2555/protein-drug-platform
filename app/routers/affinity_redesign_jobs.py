"""Affinity redesign workflow API."""

from __future__ import annotations

import csv
import io
import shutil
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.affinity_redesign_service import create_and_queue_affinity_redesign_job, save_structure_upload
from app.affinity_redesign_progress import (
    collect_affinity_redesign_progress,
    collect_mutation_records,
    build_mutation_region_table,
    mutation_region_table_csv,
)
from app.celery_app import celery_app
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.engines import AFFINITY_REDESIGN_ENGINE
from app.models import Job, JobStatus, User
from app.schemas import (
    AffinityRedesignJobCreate,
    AffinityRedesignJobListOut,
    AffinityRedesignJobOut,
    AffinityRedesignProgressOut,
    AffinityRedesignRankedOut,
)

router = APIRouter(prefix="/api/affinity-redesign-jobs", tags=["affinity-redesign"])


def _out(job: Job) -> AffinityRedesignJobOut:
    return AffinityRedesignJobOut.model_validate(job)


def _job_or_404(db: Session, user_id: str, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if not job or job.user_id != user_id or job.engine != AFFINITY_REDESIGN_ENGINE:
        raise HTTPException(404, "Affinity redesign job not found")
    return job


def _exports_dir(job: Job) -> Path:
    if not job.work_dir:
        raise HTTPException(404, "Job work_dir missing")
    return Path(job.work_dir) / "exports"


def _safe_export_path(job: Job, filename: str) -> Path:
    if Path(filename).name != filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")
    path = _exports_dir(job) / filename
    if not path.is_file():
        raise HTTPException(404, "Export file not found")
    if path.resolve().parent != _exports_dir(job).resolve():
        raise HTTPException(400, "Invalid path")
    return path


@router.post("", response_model=AffinityRedesignJobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    body: AffinityRedesignJobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    name = body.name.strip() if body.name and body.name.strip() else "affinity_redesign"
    job = create_and_queue_affinity_redesign_job(
        db,
        user_id=user.id,
        name=name,
        fasta_text=body.fasta,
        complex_path=None,
        skip_round1=body.skip_round1,
        consensus_k=body.consensus_k,
    )
    db.commit()
    db.refresh(job)
    return _out(job)


@router.post("/upload", response_model=AffinityRedesignJobOut, status_code=status.HTTP_201_CREATED)
async def create_job_upload(
    fasta: str = Form(...),
    name: str | None = Form(default=None),
    skip_round1: bool = Form(default=False),
    consensus_k: int = Form(default=3),
    complex_pdb: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    complex_path: Path | None = None
    if complex_pdb and complex_pdb.filename:
        tmp = settings.affinity_redesign_out_root / "_uploads" / user.id
        suffix = Path(complex_pdb.filename).suffix.lower() or ".pdb"
        complex_path = await save_structure_upload(complex_pdb, tmp / f"complex{suffix}")

    job_name = name.strip() if name and name.strip() else "affinity_redesign"
    k = max(1, min(6, int(consensus_k or 3)))
    job = create_and_queue_affinity_redesign_job(
        db,
        user_id=user.id,
        name=job_name,
        fasta_text=fasta,
        complex_path=complex_path,
        skip_round1=skip_round1,
        consensus_k=k,
    )
    db.commit()
    db.refresh(job)
    return _out(job)


@router.get("", response_model=AffinityRedesignJobListOut)
def list_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    condition = (Job.user_id == user.id, Job.engine == AFFINITY_REDESIGN_ENGINE)
    rows = db.scalars(
        select(Job).where(*condition).order_by(Job.created_at.desc()).limit(limit).offset(offset)
    ).all()
    total = db.scalar(select(func.count()).select_from(Job).where(*condition)) or 0
    return AffinityRedesignJobListOut(items=[_out(j) for j in rows], total=total)


@router.get("/{job_id}", response_model=AffinityRedesignJobOut)
def get_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _out(_job_or_404(db, user.id, job_id))


@router.get("/{job_id}/progress", response_model=AffinityRedesignProgressOut)
def get_progress(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tail_lines: int = Query(250, ge=50, le=800),
):
    job = _job_or_404(db, user.id, job_id)
    return AffinityRedesignProgressOut(**collect_affinity_redesign_progress(job, tail_lines=tail_lines))


@router.get("/{job_id}/ranked", response_model=AffinityRedesignRankedOut)
def get_ranked(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _job_or_404(db, user.id, job_id)
    ranked = []
    wetlab = []
    summary = None
    if job.results_json:
        ranked = job.results_json.get("ranked") or []
        wetlab = job.results_json.get("wetlab") or []
        summary = job.results_json.get("summary")
    if not ranked:
        ranked_path = _exports_dir(job) / "ranked_mutations.csv"
        if ranked_path.is_file():
            import csv

            with ranked_path.open(newline="", encoding="utf-8") as f:
                ranked = list(csv.DictReader(f))
        wetlab_path = _exports_dir(job) / "wetlab_candidates.csv"
        if wetlab_path.is_file() and not wetlab:
            import csv

            with wetlab_path.open(newline="", encoding="utf-8") as f:
                wetlab = list(csv.DictReader(f))
        summary_path = _exports_dir(job) / "summary.json"
        if summary_path.is_file() and summary is None:
            import json

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
    mutation_table: list[dict] = []
    if job.work_dir:
        mutation_table = build_mutation_region_table(collect_mutation_records(Path(job.work_dir)))
    return AffinityRedesignRankedOut(
        ranked=ranked, wetlab=wetlab, summary=summary, mutation_table=mutation_table
    )


def _ensure_sequences_fasta(job: Job) -> Path:
    from affinity_redesign.common.fasta import parse_fasta_file
    from affinity_redesign.pipeline.rescore import SEQUENCES_FASTA_NAME, build_wt_mutant_fasta

    exports = _exports_dir(job)
    path = exports / SEQUENCES_FASTA_NAME
    fasta_in = Path(job.work_dir) / "input" / "sequences.fasta"
    if not fasta_in.is_file():
        raise HTTPException(404, "缺少 input/sequences.fasta，无法导出突变序列")
    seqs = parse_fasta_file(fasta_in)
    ranked: list[dict] = []
    ranked_path = exports / "ranked_mutations.csv"
    if ranked_path.is_file():
        import csv

        with ranked_path.open(newline="", encoding="utf-8") as f:
            ranked = list(csv.DictReader(f))
    if not ranked and job.results_json:
        ranked = list(job.results_json.get("ranked") or [])
    antigen = None
    antibody_chains: list[str] | None = None
    yaml_path = Path(job.work_dir) / "campaign.yaml"
    if yaml_path.is_file():
        try:
            from affinity_redesign.schemas import CampaignConfig

            chains = CampaignConfig.from_yaml(yaml_path).chains
            antigen = chains.antigen
            antibody_chains = [chains.heavy]
            if chains.light:
                antibody_chains.append(chains.light)
        except Exception:
            antigen = None
            antibody_chains = None
    exports.mkdir(parents=True, exist_ok=True)
    # 每次下载按当前规则重写，避免旧版（含抗原）FASTA 残留
    path.write_text(
        build_wt_mutant_fasta(
            seqs,
            ranked,
            antigen_chain=antigen,
            antibody_chains=antibody_chains,
        ),
        encoding="utf-8",
    )
    return path


def _ensure_structures_dir(job: Job) -> Path:
    """确保 exports/structures 含全部 Boltz2 pred.pdb（兼容旧任务只导出了 WT/湿实验）。"""
    exports = _exports_dir(job)
    struct_dir = exports / "structures"
    struct_dir.mkdir(parents=True, exist_ok=True)
    campaign = Path(job.work_dir) if job.work_dir else None
    if campaign and campaign.is_dir():
        fold_root = campaign / "round1" / "rescore" / "boltz2"
        if fold_root.is_dir():
            for pred in fold_root.glob("*/pred.pdb"):
                name = pred.parent.name
                dest = struct_dir / ("WT.pdb" if name == "WT" else f"{name}.pdb")
                if not dest.is_file() or dest.stat().st_mtime < pred.stat().st_mtime:
                    shutil.copy2(pred, dest)
        # ranked CSV 里的 pred_pdb 路径（若仍存在）
        ranked_path = exports / "ranked_mutations.csv"
        if ranked_path.is_file():
            with ranked_path.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    vid = str(row.get("variant_id") or "").strip()
                    src = str(row.get("pred_pdb") or "").strip()
                    if not vid or not src:
                        continue
                    src_path = Path(src)
                    dest = struct_dir / f"{vid}.pdb"
                    if src_path.is_file() and (not dest.is_file() or dest.stat().st_mtime < src_path.stat().st_mtime):
                        shutil.copy2(src_path, dest)
    return struct_dir


@router.get("/{job_id}/files/{filename}")
def download_file(
    job_id: str,
    filename: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = _job_or_404(db, user.id, job_id)
    if filename == "structures.zip":
        struct_dir = _ensure_structures_dir(job)
        pdbs = sorted(struct_dir.glob("*.pdb"))
        cifs = sorted(struct_dir.glob("*.cif"))
        if not pdbs and not cifs:
            raise HTTPException(404, "structures/ 为空（尚无 Boltz2 预测结构）")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for pdb in pdbs:
                zf.write(pdb, pdb.name)
            for cif in cifs:
                zf.write(cif, cif.name)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="structures.zip"'},
        )
    if filename == "mutation_sites.csv":
        if not job.work_dir:
            raise HTTPException(404, "缺少 campaign 目录")
        rows = build_mutation_region_table(collect_mutation_records(Path(job.work_dir)))
        if not rows:
            raise HTTPException(404, "尚无突变位点（Round1 完成后生成）")
        exports = _exports_dir(job)
        exports.mkdir(parents=True, exist_ok=True)
        path = exports / "mutation_sites.csv"
        path.write_text(mutation_region_table_csv(rows), encoding="utf-8-sig")
        return FileResponse(path, filename="mutation_sites.csv", media_type="text/csv; charset=utf-8")
    if filename == "sequences_wt_mutants.fasta":
        path = _ensure_sequences_fasta(job)
        return FileResponse(path, filename=filename, media_type="text/plain; charset=utf-8")
    path = _safe_export_path(job, filename)
    return FileResponse(path, filename=filename, media_type="application/octet-stream")


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _job_or_404(db, user.id, job_id)
    if job.status in (JobStatus.queued.value, JobStatus.running.value) and job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
    db.delete(job)
    db.commit()
