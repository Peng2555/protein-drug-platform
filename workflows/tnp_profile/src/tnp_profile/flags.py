"""相对临床参考集切绿 / 黄 / 红（TAP/TNP 规则）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tnp_profile.constants import THRESHOLDS_PATH

TWO_SIDED = frozenset({"L", "L3", "C", "PSH"})
ONE_SIDED_HIGH = frozenset({"PPC", "PNC"})
INTEGER_METRICS = frozenset({"L", "L3"})


def _percentile(nums: list[float], p: float) -> float:
    n = len(nums)
    if n == 1:
        return nums[0]
    k = (n - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, n - 1)
    frac = k - lo
    return nums[lo] * (1 - frac) + nums[hi] * frac


def cut_from_values(
    values: list[float],
    *,
    two_sided: bool,
    integer: bool = False,
    decimals: int = 2,
) -> dict[str, Any]:
    """TNP/TAP：红=超出临床 min/max；黄≈两端 5%。整数长度高段外扩 1（与 bin/TNP 的 L/L3 一致）。"""
    nums = sorted(float(v) for v in values if v is not None)
    if len(nums) < 5:
        raise ValueError("参考集太小，无法切阈值")
    vmin, vmax = nums[0], nums[-1]
    p05, p95 = _percentile(nums, 5), _percentile(nums, 95)
    if integer:
        red_lt = int(vmin)
        red_gt = int(vmax) + 1
        p05_b = int(round(p05))
        p95_b = int(round(p95))
        p05_b = min(max(p05_b, red_lt), red_gt)
        p95_b = min(max(p95_b, red_lt), red_gt)
        if p95_b < p05_b:
            p95_b = p05_b
        return {
            "calibrated": True,
            "two_sided": two_sided,
            "integer": True,
            "min": vmin,
            "max": vmax,
            "p05": float(p05_b),
            "p95": float(p95_b),
            "red_lt": float(red_lt),
            "red_gt": float(red_gt),
            "n": len(nums),
        }
    red_lt = round(vmin, decimals)
    red_gt = round(vmax, decimals)
    p05_b = round(p05, decimals)
    p95_b = round(p95, decimals)
    p05_b = min(max(p05_b, red_lt), red_gt)
    p95_b = min(max(p95_b, red_lt), red_gt)
    return {
        "calibrated": True,
        "two_sided": two_sided,
        "integer": False,
        "min": vmin,
        "max": vmax,
        "p05": p05_b,
        "p95": p95_b,
        "red_lt": red_lt,
        "red_gt": red_gt,
        "n": len(nums),
    }


def load_thresholds(path: Path | None = None) -> dict[str, Any]:
    p = path or THRESHOLDS_PATH
    if not p.is_file():
        return {"metrics": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def assign_flag(metric: str, value: float | None, spec: dict[str, Any] | None) -> str:
    if value is None:
        return "pending"
    if not spec or not spec.get("calibrated"):
        return "pending"
    two_sided = bool(spec.get("two_sided", metric in TWO_SIDED))
    red_lt = float(spec.get("red_lt", spec["min"]))
    red_gt = float(spec.get("red_gt", spec["max"]))
    p05 = float(spec["p05"])
    p95 = float(spec["p95"])
    if two_sided:
        if value < red_lt or value > red_gt:
            return "red"
        if value <= p05 or value >= p95:
            return "amber"
        return "green"
    if value > red_gt:
        return "red"
    if value >= p95:
        return "amber"
    return "green"


def _threshold_view(spec: dict[str, Any]) -> dict[str, Any]:
    keys = ("min", "max", "p05", "p95", "red_lt", "red_gt", "n", "two_sided", "integer")
    return {k: spec.get(k) for k in keys}


def flag_metrics(raw: dict[str, float | None], thresholds: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    th = thresholds or load_thresholds()
    specs = th.get("metrics") or {}
    out: dict[str, dict[str, Any]] = {}
    for name in ("L", "L3", "C", "PSH", "PPC", "PNC"):
        val = raw.get(name)
        spec = specs.get(name) or {}
        out[name] = {
            "value": val,
            "flag": assign_flag(name, val, spec),
            "calibrated": bool(spec.get("calibrated")),
            "two_sided": name in TWO_SIDED or bool(spec.get("two_sided")),
            "thresholds": _threshold_view(spec) if spec.get("calibrated") else None,
        }
    return out
