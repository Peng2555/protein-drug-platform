"""Boltz 多样本：官方 ipTM=中位数，结构取 ipTM 最高。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from boltz_runner import extract_metrics  # noqa: E402


def _write_sample(root: Path, idx: int, iptm: float) -> None:
    pred = root / "predictions" / "job"
    pred.mkdir(parents=True, exist_ok=True)
    cif = pred / f"job_model_{idx}.cif"
    cif.write_text("data_test\n", encoding="utf-8")
    conf = pred / f"confidence_job_model_{idx}.json"
    conf.write_text(
        json.dumps(
            {
                "iptm": iptm,
                "ptm": 0.5,
                "confidence_score": iptm,
                "complex_plddt": 0.8,
            }
        ),
        encoding="utf-8",
    )


def test_extract_metrics_median_and_best_structure(tmp_path: Path):
    iptms = [0.10, 0.90, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.15]
    for i, v in enumerate(iptms):
        _write_sample(tmp_path, i, v)
    metrics = extract_metrics(tmp_path, seconds=1.0)
    assert metrics["n_samples"] == 10
    # median of sorted 10: avg of 5th and 6th → 0.40 and 0.50
    assert abs(metrics["iptm"] - 0.45) < 1e-9
    assert abs(metrics["iptm_median"] - 0.45) < 1e-9
    assert abs(metrics["iptm_max"] - 0.90) < 1e-9
    assert metrics["selected_model"] == 1
    copied = Path(metrics["pred_cif"]).read_text(encoding="utf-8")
    assert copied == (tmp_path / "predictions" / "job" / "job_model_1.cif").read_text(encoding="utf-8")


def test_extract_metrics_monomer_skips_zero_iptm(tmp_path: Path):
    pred = tmp_path / "predictions" / "job"
    pred.mkdir(parents=True, exist_ok=True)
    ptms = [0.40, 0.91, 0.55]
    for i, ptm in enumerate(ptms):
        (pred / f"job_model_{i}.cif").write_text(f"data_{i}\n", encoding="utf-8")
        (pred / f"confidence_job_model_{i}.json").write_text(
            json.dumps(
                {
                    "iptm": 0.0,
                    "ptm": ptm,
                    "confidence_score": ptm,
                    "complex_plddt": 0.9,
                    "pair_chains_iptm": {"0": {"0": ptm}},
                }
            ),
            encoding="utf-8",
        )
    metrics = extract_metrics(tmp_path, seconds=1.0, num_chains=1)
    assert metrics["has_interface"] is False
    assert metrics["iptm"] is None
    assert metrics["iptm_median"] is None
    assert abs(float(metrics["ptm"]) - 0.91) < 1e-9
    assert metrics["selected_model"] == 1
    assert all(s.get("iptm") is None for s in metrics["samples"])

