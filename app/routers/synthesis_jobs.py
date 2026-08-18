"""Standalone synthesis candidate selection API."""

from __future__ import annotations

import csv
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.engines import SYNTHESIS_ENGINE
from app.job_paths import remove_job_outputs
from app.models import Job, User
from app.schemas import (
    SynthesisCandidateOut,
    SynthesisCandidatesOut,
    SynthesisJobListOut,
    SynthesisJobOut,
    SynthesisSelectOut,
)
from app.synthesis_service import run_and_record_synthesis_job, save_fasta_upload, save_table_upload

router = APIRouter(prefix="/api/synthesis-jobs", tags=["synthesis"])

SYNTHESIS_CSV_KINDS = {
    "order": "synthesis_order.csv",
    "matched": "iggm_cdr3_shm_matched.csv",
}


def _out(job: Job) -> SynthesisJobOut:
    return SynthesisJobOut.model_validate(job)


@router.post("/run", response_model=SynthesisSelectOut, status_code=status.HTTP_201_CREATED)
async def run_synthesis_job(
    shm_table: UploadFile = File(..., description="SHM 测序大表 (tsv/csv，含 kabat 区段列)"),
    iggm_table: UploadFile = File(..., description="IgGM CDR3 突变表 (cdr3_all_1to3.csv)"),
    origin_fasta: UploadFile | None = File(default=None, description="可选：母本 origin.fasta，用于定位母本参考行"),
    name: str | None = Form(default=None),
    min_seq_count: int = Form(default=30),
    min_extra_count: int = Form(default=100),
    chain_id: str = Form(default="H"),
    v_gene: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from iggm_shm_matcher import ShmMatchParams
    from iggm_synthesis_order import SynthesisOrderParams

    tmp_dir = settings.synthesis_out_root / "_uploads" / user.id
    shm_path = await save_table_upload(shm_table, tmp_dir, "shm")
    iggm_path = await save_table_upload(iggm_table, tmp_dir, "iggm")
    origin_path = None
    if origin_fasta and origin_fasta.filename:
        origin_path = await save_fasta_upload(origin_fasta, tmp_dir, "origin")

    job = run_and_record_synthesis_job(
        db,
        user_id=user.id,
        name=name,
        shm_path=shm_path,
        iggm_path=iggm_path,
        origin_path=origin_path,
        match_params=ShmMatchParams(
            min_seq_count=min_seq_count,
            v_gene=v_gene or None,
            chain_id=chain_id,
        ),
        order_params=SynthesisOrderParams(min_extra_count=min_extra_count),
    )
    db.commit()
    db.refresh(job)

    if job.status != "done" or not job.results_json:
        raise HTTPException(500, job.error_message or "筛选失败")

    r = job.results_json
    return SynthesisSelectOut(
        job_id=job.id,
        parent_cdr3=r.get("parent_cdr3"),
        parent_v_gene=r.get("parent_v_gene"),
        cdr3_region=r.get("cdr3_region"),
        shm_filtered=r["shm_filtered"],
        matched_count=r["matched_count"],
        matched_cdr3_kinds=r["matched_cdr3_kinds"],
        unmatched_iggm_count=r["unmatched_iggm_count"],
        order_count=r["order_count"],
        a_count=r["a_count"],
        b_count=r["b_count"],
        matched_csv=r["matched_csv"],
        unmatched_csv=r["unmatched_csv"],
        order_csv=r["order_csv"],
        order_txt=r["order_txt"],
        out_dir=r["out_dir"],
    )


@router.get("", response_model=SynthesisJobListOut)
def list_synthesis_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    q = select(Job).where(Job.user_id == user.id, Job.engine == SYNTHESIS_ENGINE)
    total = db.scalar(
        select(func.count()).select_from(Job).where(
            Job.user_id == user.id, Job.engine == SYNTHESIS_ENGINE
        )
    ) or 0
    rows = db.scalars(q.order_by(Job.created_at.desc()).limit(limit).offset(offset)).all()
    return SynthesisJobListOut(items=[_out(j) for j in rows], total=total)


@router.get("/{job_id}", response_model=SynthesisJobOut)
def get_synthesis_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != SYNTHESIS_ENGINE:
        raise HTTPException(404, "Synthesis job not found")
    return _out(job)


def _csv_path(job: Job, kind: str) -> Path:
    key = "order_csv" if kind == "order" else "matched_csv"
    if job.results_json and job.results_json.get(key):
        path = Path(job.results_json[key])
        if path.is_file():
            return path
    if job.work_dir:
        fname = SYNTHESIS_CSV_KINDS.get(kind, SYNTHESIS_CSV_KINDS["order"])
        candidate = Path(job.work_dir) / "results" / fname
        if candidate.is_file():
            return candidate
    raise HTTPException(404, "结果 CSV 未找到")


@router.get("/{job_id}/candidates", response_model=SynthesisCandidatesOut)
def list_candidates(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    kind: str = Query("order", pattern="^(order|matched)$"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != SYNTHESIS_ENGINE:
        raise HTTPException(404, "Synthesis job not found")
    if job.status != "done":
        raise HTTPException(409, f"任务状态: {job.status}")

    csv_path = _csv_path(job, kind)
    rows: list[dict] = []
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        for row in reader:
            rows.append(row)

    total = len(rows)
    page = rows[offset : offset + limit]
    known = {
        "synthesis_id", "priority", "recommend",
        "iggm_variant_id", "iggm_cdr3", "seq_count", "shm_row", "shm_file_line",
        "cdr3_mutation_sites", "extra_mutation_sites", "cdr3_mutation_sites_in_shm_row",
        "extra_mutation_sites_in_shm_row",
        "all_mutation_sites_for_synthesis", "n_total_mutations",
        "synthesis_sequence", "nucleotide_sequence", "aa_sequence",
        "v_gene", "j_gene", "PI", "note", "has_extra_shm",
        "iggm_frequency", "iggm_cdr3_mutations",
    }
    items = []
    for row in page:
        extra = {k: v for k, v in row.items() if k not in known}
        shm_row_val = row.get("shm_row") or row.get("shm_file_line")
        items.append(
            SynthesisCandidateOut(
                synthesis_id=row.get("synthesis_id"),
                priority=row.get("priority"),
                recommend=row.get("recommend"),
                iggm_variant_id=row.get("iggm_variant_id"),
                iggm_cdr3=row.get("iggm_cdr3"),
                seq_count=float(row["seq_count"]) if row.get("seq_count") else None,
                shm_row=int(shm_row_val) if shm_row_val else None,
                cdr3_mutation_sites=row.get("cdr3_mutation_sites"),
                extra_mutation_sites=row.get("extra_mutation_sites"),
                all_mutation_sites_for_synthesis=row.get("all_mutation_sites_for_synthesis"),
                n_total_mutations=int(row["n_total_mutations"]) if row.get("n_total_mutations") else None,
                synthesis_sequence=row.get("synthesis_sequence") or row.get("aa_sequence"),
                nucleotide_sequence=row.get("nucleotide_sequence"),
                v_gene=row.get("v_gene"),
                j_gene=row.get("j_gene"),
                PI=row.get("PI"),
                note=row.get("note"),
                has_extra_shm=row.get("has_extra_shm"),
                cdr3_mutation_sites_in_shm_row=row.get("cdr3_mutation_sites_in_shm_row"),
                extra_mutation_sites_in_shm_row=row.get("extra_mutation_sites_in_shm_row"),
                aa_sequence=row.get("aa_sequence"),
                iggm_frequency=float(row["iggm_frequency"]) if row.get("iggm_frequency") else None,
                iggm_cdr3_mutations=row.get("iggm_cdr3_mutations"),
                extra=extra,
            )
        )

    summary = None
    if job.results_json:
        r = job.results_json
        summary = {
            k: r[k]
            for k in (
                "parent_cdr3", "parent_v_gene", "cdr3_region",
                "shm_filtered", "matched_count", "matched_cdr3_kinds",
                "unmatched_iggm_count", "order_count", "a_count", "b_count",
            )
            if k in r
        }
        if job.params_json:
            summary["params"] = job.params_json

    return SynthesisCandidatesOut(items=items, total=total, columns=columns, summary=summary)


@router.get("/{job_id}/candidates.csv")
def download_candidates_csv(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    kind: str = Query("order", pattern="^(order|matched)$"),
):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != SYNTHESIS_ENGINE:
        raise HTTPException(404, "Synthesis job not found")
    csv_path = _csv_path(job, kind)
    suffix = "order" if kind == "order" else "matched"
    return FileResponse(
        csv_path,
        filename=f"{job.name or job.id}_synthesis_{suffix}.csv",
        media_type="text/csv",
    )


@router.get("/{job_id}/order.txt")
def download_order_txt(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != SYNTHESIS_ENGINE:
        raise HTTPException(404, "Synthesis job not found")
    if not job.results_json or not job.results_json.get("order_txt"):
        raise HTTPException(404, "文本清单未找到")
    txt_path = Path(job.results_json["order_txt"])
    if not txt_path.is_file():
        raise HTTPException(404, "文本清单未找到")
    return FileResponse(
        txt_path,
        filename=f"{job.name or job.id}_synthesis_order.txt",
        media_type="text/plain",
    )


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_synthesis_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != SYNTHESIS_ENGINE:
        raise HTTPException(404, "Synthesis job not found")
    remove_job_outputs(
        settings.synthesis_out_root,
        job.id,
        job.name,
        job.chains_json,
        job.work_dir,
    )
    db.delete(job)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
