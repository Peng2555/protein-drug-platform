"""抗体疏水性改造 API。"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.engines import HYDRO_REDESIGN_ENGINE
from app.hydro_redesign_service import create_and_queue_hydro_redesign_job, save_structure_upload
from app.models import Job, JobStatus, User
from app.schemas import (
    HydroRedesignJobCreate,
    HydroRedesignJobListOut,
    HydroRedesignJobOut,
    HydroRedesignProgressOut,
    HydroRedesignRankedOut,
)

ROOT = Path(__file__).resolve().parents[1]
_HYDRO_SRC = str(ROOT / "hydro_redesign" / "src")
if _HYDRO_SRC not in sys.path:
    sys.path.insert(0, _HYDRO_SRC)

from hydro_redesign.sequences import (  # noqa: E402
    ALL_MUTANT_FASTA,
    TOP20_MUTANT_FASTA,
    build_mutant_sequences_fasta,
    parse_fasta,
    select_top20_rows,
)

router = APIRouter(prefix="/api/hydro-redesign-jobs", tags=["hydro-redesign"])


def _out(job: Job) -> HydroRedesignJobOut:
    return HydroRedesignJobOut.model_validate(job)


def _job_or_404(db: Session, user_id: str, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if not job or job.user_id != user_id or job.engine != HYDRO_REDESIGN_ENGINE:
        raise HTTPException(404, "Hydro redesign job not found")
    return job


def _work(job: Job) -> Path:
    if not job.work_dir:
        raise HTTPException(404, "Job work_dir missing")
    return Path(job.work_dir)


def _exports(job: Job) -> Path:
    return _work(job) / "exports"


def _read_csv_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load_wt_sequences(job: Job) -> dict[str, str]:
    fasta_path = _work(job) / "input" / "sequences.fasta"
    if fasta_path.is_file():
        return parse_fasta(fasta_path.read_text(encoding="utf-8"))
    params = job.params_json or {}
    text = params.get("fasta") or params.get("fasta_text") or ""
    if text:
        return parse_fasta(str(text))
    return {}


def _ensure_mutant_fasta(job: Job, filename: str) -> Path | None:
    """新任务已写出；旧任务按需从 mutations/wetlab + WT FASTA 生成。"""
    exports = _exports(job)
    exports.mkdir(parents=True, exist_ok=True)
    dest = exports / filename
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    seqs = _load_wt_sequences(job)
    if not seqs:
        return None
    mutations = _read_csv_rows(exports / "mutations.csv")
    wetlab = _read_csv_rows(exports / "wetlab.csv")
    if not mutations and job.results_json:
        mutations = list(job.results_json.get("mutations") or [])
        wetlab = list(job.results_json.get("wetlab") or [])
    if filename == ALL_MUTANT_FASTA:
        rows = mutations
    elif filename == TOP20_MUTANT_FASTA:
        rows = select_top20_rows(mutations, wetlab)
    else:
        return None
    if not rows:
        return None
    text = build_mutant_sequences_fasta(seqs, rows)
    dest.write_text(text, encoding="utf-8")
    return dest


@router.post("", response_model=HydroRedesignJobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    body: HydroRedesignJobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    name = body.name.strip() if body.name and body.name.strip() else "hydro_redesign"
    job = create_and_queue_hydro_redesign_job(
        db,
        user_id=user.id,
        name=name,
        fasta_text=body.fasta,
        allow_cdr=body.allow_cdr,
        allow_charged=body.allow_charged,
    )
    db.commit()
    db.refresh(job)
    return _out(job)


@router.post("/upload", response_model=HydroRedesignJobOut, status_code=status.HTTP_201_CREATED)
async def create_job_upload(
    fasta: str = Form(...),
    name: str | None = Form(default=None),
    allow_cdr: bool = Form(default=False),
    allow_charged: bool = Form(default=False),
    structure: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    structure_path: Path | None = None
    if structure and structure.filename:
        tmp = settings.hydro_redesign_out_root / "_uploads" / user.id
        suffix = Path(structure.filename).suffix.lower() or ".pdb"
        structure_path = await save_structure_upload(structure, tmp / f"structure{suffix}")
    job_name = name.strip() if name and name.strip() else "hydro_redesign"
    job = create_and_queue_hydro_redesign_job(
        db,
        user_id=user.id,
        name=job_name,
        fasta_text=fasta,
        structure_path=structure_path,
        allow_cdr=allow_cdr,
        allow_charged=allow_charged,
    )
    db.commit()
    db.refresh(job)
    return _out(job)


@router.get("", response_model=HydroRedesignJobListOut)
def list_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    condition = (Job.user_id == user.id, Job.engine == HYDRO_REDESIGN_ENGINE)
    rows = db.scalars(
        select(Job).where(*condition).order_by(Job.created_at.desc()).limit(limit).offset(offset)
    ).all()
    total = db.scalar(select(func.count()).select_from(Job).where(*condition)) or 0
    return HydroRedesignJobListOut(items=[_out(j) for j in rows], total=total)


@router.get("/{job_id}", response_model=HydroRedesignJobOut)
def get_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _out(_job_or_404(db, user.id, job_id))


@router.get("/{job_id}/progress", response_model=HydroRedesignProgressOut)
def get_progress(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _job_or_404(db, user.id, job_id)
    stage = job.stage or "queued"
    summary = None
    if job.work_dir:
        wf = Path(job.work_dir) / "workflow_status.json"
        if wf.is_file():
            try:
                data = json.loads(wf.read_text(encoding="utf-8"))
                stage = str(data.get("stage") or stage)
                summary = data.get("summary")
            except json.JSONDecodeError:
                pass
    return HydroRedesignProgressOut(stage=stage, status=job.status, summary=summary)


@router.get("/{job_id}/ranked", response_model=HydroRedesignRankedOut)
def get_ranked(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _job_or_404(db, user.id, job_id)
    mutations: list[dict] = []
    wetlab: list[dict] = []
    patches: list[dict] = []
    residues: list[dict] = []
    summary = None
    if job.results_json:
        mutations = list(job.results_json.get("mutations") or [])
        wetlab = list(job.results_json.get("wetlab") or [])
        patches = list(job.results_json.get("patches") or [])
        summary = job.results_json.get("summary")
    exports = _exports(job)
    if (exports / "mutations.csv").is_file():
        mutations = _read_csv_rows(exports / "mutations.csv")
    if (exports / "wetlab.csv").is_file():
        wetlab = _read_csv_rows(exports / "wetlab.csv")
    if (exports / "patches.csv").is_file():
        patches = _read_csv_rows(exports / "patches.csv")
    res_csv = _work(job) / "patches" / "residue_sasa.csv"
    if res_csv.is_file():
        residues = _read_csv_rows(res_csv)
    if (exports / "summary.json").is_file() and summary is None:
        summary = json.loads((exports / "summary.json").read_text(encoding="utf-8"))
    return HydroRedesignRankedOut(
        mutations=mutations,
        wetlab=wetlab,
        patches=patches,
        residues=residues,
        summary=summary,
    )


@router.get("/{job_id}/files/{filename}")
def download_file(
    job_id: str,
    filename: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = _job_or_404(db, user.id, job_id)
    if Path(filename).name != filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")
    exports = _exports(job)
    path = exports / filename
    if filename in {ALL_MUTANT_FASTA, TOP20_MUTANT_FASTA}:
        generated = _ensure_mutant_fasta(job, filename)
        if generated is not None:
            path = generated
        elif not path.is_file():
            raise HTTPException(404, "突变序列尚未生成（缺少 WT FASTA 或突变表）")
    if not path.is_file():
        for alt_dir in (_work(job) / "patches", _work(job) / "fold", _work(job) / "input"):
            alt = alt_dir / filename
            if alt.is_file():
                path = alt
                break
    if not path.is_file():
        raise HTTPException(404, "File not found")
    media = "chemical/x-cif" if path.suffix.lower() == ".cif" else "application/octet-stream"
    if path.suffix.lower() == ".csv":
        media = "text/csv; charset=utf-8"
    if path.suffix.lower() == ".json":
        media = "application/json"
    if path.suffix.lower() == ".fasta":
        media = "text/x-fasta; charset=utf-8"
    return FileResponse(path, filename=filename, media_type=media)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _job_or_404(db, user.id, job_id)
    if job.status in (JobStatus.queued.value, JobStatus.running.value) and job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
    db.delete(job)
    db.commit()
