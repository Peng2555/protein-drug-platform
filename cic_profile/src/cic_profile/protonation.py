"""实验 pH 下的有效电荷（Henderson–Hasselbalch，第一版不用 PROPKA）。"""

from __future__ import annotations

from cic_profile.constants import ARG_PKA, ASP_PKA, DEFAULT_PH, GLU_PKA, HIS_PKA, LYS_PKA


def _acid_charge(pka: float, ph: float) -> float:
    return -1.0 / (1.0 + 10 ** (pka - ph))


def _base_charge(pka: float, ph: float) -> float:
    return 1.0 / (1.0 + 10 ** (ph - pka))


def effective_charge(aa: str, ph: float = DEFAULT_PH) -> float:
    aa = (aa or "").upper()
    if aa == "D":
        return round(_acid_charge(ASP_PKA, ph), 3)
    if aa == "E":
        return round(_acid_charge(GLU_PKA, ph), 3)
    if aa == "K":
        return round(_base_charge(LYS_PKA, ph), 3)
    if aa == "R":
        return round(_base_charge(ARG_PKA, ph), 3)
    if aa == "H":
        return round(_base_charge(HIS_PKA, ph), 3)
    return 0.0
