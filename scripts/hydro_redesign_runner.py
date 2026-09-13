"""Celery 入口：抗体疏水性改造第一版。"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


def _ensure_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    for extra in (root / "hydro_redesign" / "src", root / "affinity_redesign" / "src"):
        s = str(extra)
        if extra.is_dir() and s not in sys.path:
            sys.path.insert(0, s)


@dataclass
class HydroRedesignResult:
    status: str
    stage: str
    seconds: float
    results: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def run_hydro_redesign_job(
    *,
    work_dir: Path,
    params: dict[str, Any] | None = None,
    fasta_text: str = "",
    on_stage: Callable[[str], None] | None = None,
) -> HydroRedesignResult:
    _ensure_paths()
    from hydro_redesign.workflow import run_workflow

    params = params or {}
    campaign = work_dir.resolve()
    t0 = time.time()
    fasta_file = campaign / "input" / "sequences.fasta"
    if fasta_file.is_file():
        fasta = fasta_file.read_text(encoding="utf-8")
    else:
        fasta = fasta_text
    struct = params.get("structure_path")
    structure_path = Path(struct) if struct else None
    if structure_path and not structure_path.is_file():
        structure_path = None
    try:
        results = run_workflow(
            campaign,
            fasta_text=fasta,
            structure_path=structure_path,
            allow_cdr=bool(params.get("allow_cdr")),
            allow_charged=bool(params.get("allow_charged")),
            on_stage=on_stage,
        )
        return HydroRedesignResult(
            status="ok",
            stage="done",
            seconds=time.time() - t0,
            results=results,
        )
    except Exception as exc:
        stage = "failed"
        wf = campaign / "workflow_status.json"
        if wf.is_file():
            try:
                stage = str(json.loads(wf.read_text(encoding="utf-8")).get("stage") or stage)
            except json.JSONDecodeError:
                pass
        return HydroRedesignResult(
            status="failed",
            stage=stage,
            seconds=time.time() - t0,
            error=str(exc)[:8000],
        )
