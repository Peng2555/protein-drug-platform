"""Web worker entry for affinity_redesign end-to-end workflow."""

from __future__ import annotations

import csv
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


def _ensure_affinity_redesign_path() -> None:
    try:
        from app.config import settings

        src = settings.antibody_redesign_root / "affinity_redesign" / "src"
        if src.is_dir():
            src_str = str(src)
            if src_str not in sys.path:
                sys.path.insert(0, src_str)
    except Exception:
        pass


@dataclass
class AffinityRedesignResult:
    status: str
    stage: str
    seconds: float
    results: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def _collect_exports(campaign_dir: Path) -> dict[str, Any]:
    exports = campaign_dir / "exports"
    ranked = exports / "ranked_mutations.csv"
    wetlab = exports / "wetlab_candidates.csv"
    summary = exports / "summary.json"
    structures = exports / "structures"
    out: dict[str, Any] = {
        "exports_dir": str(exports),
        "ranked_csv": str(ranked) if ranked.is_file() else None,
        "wetlab_csv": str(wetlab) if wetlab.is_file() else None,
        "structures_dir": str(structures) if structures.is_dir() else None,
        "summary_json": str(summary) if summary.is_file() else None,
    }
    if summary.is_file():
        try:
            out["summary"] = json.loads(summary.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    if ranked.is_file():
        with ranked.open(newline="", encoding="utf-8") as f:
            out["ranked"] = list(csv.DictReader(f))
    if wetlab.is_file():
        with wetlab.open(newline="", encoding="utf-8") as f:
            out["wetlab"] = list(csv.DictReader(f))
    wf = campaign_dir / "workflow_status.json"
    if wf.is_file():
        try:
            out["workflow_status"] = json.loads(wf.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return out


def run_affinity_redesign_job(
    *,
    work_dir: Path,
    params: dict[str, Any] | None = None,
    on_stage: Callable[[str], None] | None = None,
) -> AffinityRedesignResult:
    """Run affinity_redesign.pipeline.workflow.run_workflow on an existing campaign dir."""
    params = params or {}
    campaign_dir = work_dir.resolve()
    if not campaign_dir.is_dir():
        return AffinityRedesignResult(
            status="failed",
            stage="init",
            seconds=0.0,
            error=f"Campaign directory not found: {campaign_dir}",
        )

    t0 = time.monotonic()
    _ensure_affinity_redesign_path()
    try:
        from affinity_redesign.pipeline.workflow import run_workflow
    except ImportError as exc:
        return AffinityRedesignResult(
            status="failed",
            stage="init",
            seconds=time.monotonic() - t0,
            error=(
                "未安装 affinity_redesign 包；请在 worker 环境执行："
                "pip install -e /path/to/antibody_redesign"
            ),
            results={"import_error": str(exc)},
        )

    try:
        status = run_workflow(
            campaign_dir,
            skip_round1=bool(params.get("skip_round1")),
            skip_rescore=bool(params.get("skip_rescore")),
            on_stage=on_stage,
        )
    except Exception as exc:
        return AffinityRedesignResult(
            status="failed",
            stage="error",
            seconds=time.monotonic() - t0,
            error=str(exc),
            results=_collect_exports(campaign_dir),
        )

    results = _collect_exports(campaign_dir)
    results["workflow"] = status
    ok = status.get("status") == "ok"
    return AffinityRedesignResult(
        status="ok" if ok else "failed",
        stage=str(status.get("stage") or "done"),
        seconds=time.monotonic() - t0,
        results=results,
        error=None if ok else str(status.get("error") or "workflow failed"),
    )
