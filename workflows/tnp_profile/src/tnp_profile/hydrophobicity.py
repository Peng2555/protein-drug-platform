"""Kyte–Doolittle 缩放到 [1, 2]，与 TNP normalize() 一致。"""

from __future__ import annotations

from tnp_profile.constants import KYTE_DOOLITTLE


def _raw_minmax() -> tuple[float, float]:
    vals = list(KYTE_DOOLITTLE.values())
    return min(vals), max(vals)


_KD_MIN, _KD_MAX = _raw_minmax()


def scaled_hydrophobicity(aa: str) -> float:
    raw = KYTE_DOOLITTLE.get(aa.upper(), KYTE_DOOLITTLE["G"])
    return (raw - _KD_MIN) / (_KD_MAX - _KD_MIN) + 1.0


GLY_HYDROPHOBICITY = scaled_hydrophobicity("G")
