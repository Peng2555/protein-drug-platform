"""独立结构预测：从工作目录收集 Boltz 多次扩散采样。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.models import Job

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from boltz_runner import _model_index, discover_boltz_samples  # noqa: E402


def _metrics(work_dir: Path) -> dict:
    path = work_dir / "metrics.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _work_dir(job: Job) -> Path | None:
    if job.work_dir:
        p = Path(job.work_dir)
        if p.is_dir():
            return p
    return None


def list_fold_samples(job: Job) -> list[dict]:
    """返回各 sample 的指标与 cif 路径（路径仅内部使用）。"""
    work = _work_dir(job)
    if work is None:
        return []
    metrics = _metrics(work)
    selected = metrics.get("selected_model")
    discovered = discover_boltz_samples(work)
    rows: list[dict] = []
    for item in discovered:
        cif = item.get("cif")
        if not cif or not Path(cif).is_file():
            continue
        idx = int(item["index"])
        rows.append(
            {
                "index": idx,
                "iptm": item.get("iptm"),
                "ptm": item.get("ptm"),
                "confidence_score": item.get("confidence_score"),
                "complex_plddt": item.get("complex_plddt"),
                "is_selected": selected is not None and idx == selected,
                "cif": cif,
            }
        )
    if rows:
        if not any(r.get("is_selected") for r in rows):
            src = metrics.get("source_cif")
            src_idx = _model_index(Path(src)) if src else None
            marked = False
            if src_idx is not None:
                for row in rows:
                    if row["index"] == src_idx:
                        row["is_selected"] = True
                        marked = True
                        break
            if not marked:
                rows[0]["is_selected"] = True
        return rows
    pred = work / "pred.cif"
    if pred.is_file():
        return [
            {
                "index": 0,
                "iptm": job.iptm,
                "ptm": job.ptm,
                "confidence_score": job.confidence_score,
                "complex_plddt": job.complex_plddt,
                "is_selected": True,
                "cif": str(pred),
            }
        ]
    return []


def fold_sample_payload(job: Job) -> dict:
    rows = list_fold_samples(job)
    if not rows:
        return {}
    work = _work_dir(job)
    metrics = _metrics(work) if work else {}
    public = [{k: v for k, v in r.items() if k != "cif"} for r in rows]
    selected = next((r["index"] for r in rows if r.get("is_selected")), rows[0]["index"])
    return {
        "n_samples": len(rows),
        "selected_model": selected,
        "iptm_median": metrics.get("iptm_median", job.iptm),
        "iptm_max": metrics.get("iptm_max"),
        "samples": public,
    }


def resolve_fold_cif(job: Job, model: int | None = None) -> Path | None:
    work = _work_dir(job)
    if model is None:
        if job.structure_path:
            p = Path(job.structure_path)
            if p.is_file():
                return p
        if work and (work / "pred.cif").is_file():
            return work / "pred.cif"
        return None
    for row in list_fold_samples(job):
        if int(row["index"]) == int(model):
            p = Path(row["cif"])
            return p if p.is_file() else None
    return None
