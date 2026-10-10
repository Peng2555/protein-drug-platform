"""CIC 第一版固定参数。"""

from __future__ import annotations

# Kyte–Doolittle，疏水斑分用
KYTE_DOOLITTLE: dict[str, float] = {
    "A": 1.8,
    "R": -4.5,
    "N": -3.5,
    "D": -3.5,
    "C": 2.5,
    "Q": -3.5,
    "E": -3.5,
    "G": -0.4,
    "H": -3.2,
    "I": 4.5,
    "L": 3.8,
    "K": -3.9,
    "M": 1.9,
    "F": 2.8,
    "P": -1.6,
    "S": -0.8,
    "T": -0.7,
    "W": -0.9,
    "Y": -1.3,
    "V": 4.2,
}

HYDROPHOBIC = frozenset("WFYLIVM")
POSITIVE_AA = frozenset("KRH")
NEGATIVE_AA = frozenset("DE")

HIS_PKA = 6.0
ASP_PKA = 4.0
GLU_PKA = 4.4
LYS_PKA = 10.4
ARG_PKA = 12.0

KD_SCALE = 4.5
SURFACE_RSA_CHARGE = 0.20
SURFACE_RSA_HYDRO = 0.25
PATCH_CUTOFF = 8.0
CHARGE_ABS_MIN = 0.3
DEFAULT_PH = 7.0
