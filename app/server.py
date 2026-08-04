#!/usr/bin/env python3
"""Boltz2 web service — submit sequences/FASTA, poll job status, download structure."""

from __future__ import annotations

import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from boltz_runner import DEFAULT_OUT_ROOT, fold_sequences, parse_fasta_text

app = FastAPI(title="Boltz2 Fold Service", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIR = ROOT / "web"
JOBS_ROOT = DEFAULT_OUT_ROOT
_lock = threading.Lock()
_running: set[str] = set()


class ChainInput(BaseModel):
    id: str = Field(..., description="Chain ID, e.g. H, L, A")
    sequence: str = Field(..., description="Amino acid sequence")


class JobSubmit(BaseModel):
    chains: list[ChainInput] | None = None
    fasta: str | None = None
    name: str | None = None
    use_msa_server: bool = True


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_meta_path(job_id: str) -> Path:
    return JOBS_ROOT / job_id / "job_meta.json"


def _write_meta(job_id: str, data: dict) -> None:
    path = _job_meta_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    import json

    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_meta(job_id: str) -> dict:
    path = _job_meta_path(job_id)
    if not path.exists():
        raise HTTPException(404, f"Job {job_id} not found")
    import json

    return json.loads(path.read_text())


def _run_job(job_id: str, seqs: dict[str, str], use_msa_server: bool) -> None:
    meta = _read_meta(job_id)
    meta["status"] = "running"
    meta["started_at"] = _utcnow()
    _write_meta(job_id, meta)

    try:
        result = fold_sequences(
            seqs,
            out_root=JOBS_ROOT,
            job_id=job_id,
            use_msa_server=use_msa_server,
            skip_if_done=False,
            write_pdb=False,
        )
        meta["status"] = result.status
        meta["finished_at"] = _utcnow()
        meta["result"] = {
            "iptm": result.iptm,
            "ptm": result.ptm,
            "confidence_score": result.confidence_score,
            "complex_plddt": result.complex_plddt,
            "pred_cif": result.pred_cif,
            "seconds": result.seconds,
            "error": result.error,
        }
    except Exception as exc:
        meta["status"] = "failed"
        meta["finished_at"] = _utcnow()
        meta["result"] = {"error": str(exc)}
    finally:
        _write_meta(job_id, meta)
        with _lock:
            _running.discard(job_id)


@app.get("/api/health")
def health():
    with _lock:
        n_running = len(_running)
    return {"status": "ok", "running_jobs": n_running}


@app.post("/api/jobs")
def submit_job(body: JobSubmit, background_tasks: BackgroundTasks):
    if body.chains and body.fasta:
        raise HTTPException(400, "Provide either chains or fasta, not both")
    if body.chains:
        seqs = {c.id: c.sequence.strip().upper() for c in body.chains}
    elif body.fasta:
        seqs = parse_fasta_text(body.fasta)
    else:
        raise HTTPException(400, "Provide chains or fasta")

    job_id = body.name or str(uuid.uuid4())[:12]
    job_id = job_id.replace("/", "_")

    if _job_meta_path(job_id).exists():
        existing = _read_meta(job_id)
        if existing.get("status") in ("queued", "running"):
            return {"job_id": job_id, "status": existing["status"], "message": "Job already exists"}

    meta = {
        "job_id": job_id,
        "status": "queued",
        "created_at": _utcnow(),
        "chains": list(seqs.keys()),
        "total_length": sum(len(s) for s in seqs.values()),
        "use_msa_server": body.use_msa_server,
    }
    _write_meta(job_id, meta)

    with _lock:
        _running.add(job_id)
    background_tasks.add_task(_run_job, job_id, seqs, body.use_msa_server)

    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    return _read_meta(job_id)


@app.get("/api/jobs/{job_id}/structure")
def download_structure(job_id: str):
    meta = _read_meta(job_id)
    if meta.get("status") != "ok":
        raise HTTPException(409, f"Job status: {meta.get('status')}")
    cif = JOBS_ROOT / job_id / "pred.cif"
    if not cif.exists():
        raise HTTPException(404, "Structure file not found")
    return FileResponse(cif, filename=f"{job_id}.cif", media_type="chemical/x-cif")


if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
