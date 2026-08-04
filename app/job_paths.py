"""Human-readable output directory names and on-disk job metadata."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path


def sanitize_label(text: str, max_len: int = 48) -> str:
    s = re.sub(r"[^\w\-]+", "_", text.strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return (s or "job")[:max_len]


def default_job_name(chains_json: dict[str, int]) -> str:
    """Auto name from chain lengths, e.g. H134_A129."""
    return "_".join(f"{k}{v}" for k, v in sorted(chains_json.items()))


def job_output_dir_name(name: str | None, job_id: str, chains_json: dict[str, int] | None = None) -> str:
    """Folder name like vhh_demo__40a566cd (unique via UUID prefix)."""
    short = job_id.split("-", 1)[0]
    if name and name.strip():
        label = sanitize_label(name)
    elif chains_json:
        label = sanitize_label(default_job_name(chains_json))
    else:
        label = "job"
    return f"{label}__{short}"


def job_output_dir(
    out_root: Path,
    name: str | None,
    job_id: str,
    chains_json: dict[str, int] | None = None,
) -> Path:
    return out_root / job_output_dir_name(name, job_id, chains_json)


def write_job_info(
    work_dir: Path,
    *,
    job_id: str,
    name: str | None,
    username: str | None,
    status: str,
    chains_json: dict,
    engine: str = "boltz2",
    created_at: datetime | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    iptm: float | None = None,
    ptm: float | None = None,
    confidence_score: float | None = None,
    complex_plddt: float | None = None,
    pdockq: float | None = None,
    pdockq2: float | None = None,
    runtime_seconds: float | None = None,
    error_message: str | None = None,
    stage: str | None = None,
    results_json: dict | None = None,
) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "job_id": job_id,
        "name": name,
        "username": username,
        "engine": engine,
        "status": status,
        "stage": stage,
        "chains": chains_json,
        "created_at": created_at.isoformat() if created_at else None,
        "started_at": started_at.isoformat() if started_at else None,
        "finished_at": finished_at.isoformat() if finished_at else None,
        "iptm": iptm,
        "ptm": ptm,
        "confidence_score": confidence_score,
        "complex_plddt": complex_plddt,
        "pdockq": pdockq,
        "pdockq2": pdockq2,
        "runtime_seconds": runtime_seconds,
        "error_message": error_message,
        "results_json": results_json,
    }
    (work_dir / "job_info.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def job_output_candidates(
    out_root: Path,
    job_id: str,
    name: str | None = None,
    chains_json: dict[str, int] | None = None,
    work_dir: str | None = None,
) -> list[Path]:
    """All known output paths for a job (deduplicated)."""
    candidates = [
        out_root / job_id,
        job_output_dir(out_root, name, job_id, chains_json),
    ]
    if work_dir:
        candidates.append(Path(work_dir))
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in candidates:
        try:
            key = path.resolve()
        except OSError:
            key = path
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def remove_job_outputs(
    out_root: Path,
    job_id: str,
    name: str | None = None,
    chains_json: dict[str, int] | None = None,
    work_dir: str | None = None,
) -> None:
    """Remove output directories and symlinks for a job."""
    for path in job_output_candidates(out_root, job_id, name, chains_json, work_dir):
        if path.is_symlink():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
