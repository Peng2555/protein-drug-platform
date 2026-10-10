"""用临床 36 条 VHH 切 L/L3；结构项需 Boltz2 标定后写入。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tnp_profile.constants import CLINICAL_FASTA, DISCLAIMER, THRESHOLDS_PATH
from tnp_profile.flags import INTEGER_METRICS, ONE_SIDED_HIGH, TWO_SIDED, cut_from_values, load_thresholds
from tnp_profile.numbering import annotate_kabat, parse_fasta


def calibrate_sequence_metrics(fasta: Path | None = None) -> dict[str, Any]:
    text = (fasta or CLINICAL_FASTA).read_text(encoding="utf-8")
    seqs = parse_fasta(text)
    L_vals: list[float] = []
    L3_vals: list[float] = []
    failed = []
    for name, seq in seqs.items():
        try:
            ann = annotate_kabat(seq)
        except Exception as exc:
            failed.append(f"{name}: {exc}")
            continue
        L_vals.append(float(ann["L"]))
        L3_vals.append(float(ann["L3"]))
    if len(L_vals) < 10:
        raise RuntimeError("临床集 Kabat 编号失败过多: " + "; ".join(failed[:5]))
    existing = load_thresholds()
    metrics = dict(existing.get("metrics") or {})
    metrics["L"] = cut_from_values(L_vals, two_sided=True, integer=True)
    metrics["L3"] = cut_from_values(L3_vals, two_sided=True, integer=True)
    for key in ("C", "PSH", "PPC", "PNC"):
        metrics.setdefault(
            key,
            {"calibrated": False, "two_sided": key in TWO_SIDED and key not in ONE_SIDED_HIGH},
        )
        if key in ONE_SIDED_HIGH:
            metrics[key]["two_sided"] = False
    payload = {
        "scheme": "kabat",
        "structure_engine": "boltz2",
        "reference": "tnp_paper_36_vhh",
        "n_sequence": len(L_vals),
        "note": DISCLAIMER,
        "metrics": metrics,
        "numbering_failures": failed,
    }
    return payload


def write_thresholds(payload: dict[str, Any], path: Path | None = None) -> Path:
    dest = path or THRESHOLDS_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest


def merge_structure_values(values: dict[str, list[float]], path: Path | None = None) -> dict[str, Any]:
    payload = load_thresholds(path)
    metrics = dict(payload.get("metrics") or {})
    for key, vals in values.items():
        if key not in ("C", "PSH", "PPC", "PNC"):
            continue
        metrics[key] = cut_from_values(
            vals,
            two_sided=key in TWO_SIDED,
            integer=key in INTEGER_METRICS,
        )
    payload["metrics"] = metrics
    payload["structure_calibrated"] = True
    write_thresholds(payload, path)
    return payload
