"""Celery 入口：抗体额外二硫键 / 折叠态能量筛选。"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


def _ensure_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from algorithm_paths import bootstrap_algorithm_paths

    bootstrap_algorithm_paths()


@dataclass
class TmDisulfideResult:
    status: str
    stage: str
    seconds: float
    results: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def run_tm_disulfide_job(
    *,
    work_dir: Path,
    params: dict[str, Any] | None = None,
    fasta_text: str = "",
    on_stage: Callable[[str], None] | None = None,
) -> TmDisulfideResult:
    _ensure_paths()
    from tm_disulfide.workflow import run_workflow

    params = params or {}
    campaign = work_dir.resolve()
    t0 = time.time()
    fasta_file = campaign / "input" / "sequences.fasta"
    fasta = fasta_file.read_text(encoding="utf-8") if fasta_file.is_file() else fasta_text
    raw_paths = params.get("structure_paths") or []
    structure_paths = [Path(item) for item in raw_paths if item]
    source_dir = params.get("source_work_dir")
    if not structure_paths and source_dir:
        structure_paths = Path(source_dir)
    try:
        results = run_workflow(
            campaign,
            fasta_text=fasta,
            structure_paths=structure_paths,
            on_stage=on_stage,
        )
        return TmDisulfideResult(status="ok", stage="done", seconds=time.time() - t0, results=results)
    except Exception as exc:
        stage = "failed"
        wf = campaign / "workflow_status.json"
        if wf.is_file():
            try:
                stage = str(json.loads(wf.read_text(encoding="utf-8")).get("stage") or stage)
            except json.JSONDecodeError:
                pass
        return TmDisulfideResult(
            status="failed",
            stage=stage,
            seconds=time.time() - t0,
            error=str(exc)[:8000],
        )
