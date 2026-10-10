"""Kabat 口径的 TNP 公式常数（方案 B：非官方 IMGT 阈值）。"""

from __future__ import annotations

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR / "data"
CLINICAL_FASTA = DATA_DIR / "clinical_vhh.fasta"
THRESHOLDS_PATH = DATA_DIR / "thresholds.json"

# Kabat CDR（重链）
KABAT_CDR_H1 = (31, 35)
KABAT_CDR_H2 = (50, 65)
KABAT_CDR_H3 = (95, 102)

# CDR ±2，对齐官方 IMGT vicinity 的扩边方式
KABAT_VICINITY = {
    "H1": (29, 37),
    "H2": (48, 67),
    "H3": (93, 104),
}

# Compactness：Kabat/Chothia H3 环与锚点（官方 IMGT 为 105–117 / 102,103,118,119）
KABAT_H3_LOOP = (95, 102)
KABAT_H3_ANCHORS = (92, 93, 103, 104)
KABAT_H3_C_TERM_REF = 103

KABAT_TETRAD = (37, 44, 45, 47)

SURFACE_ASA = 7.5
VICINITY_CUTOFF = 4.0
PAIR_CUTOFF = 7.5
SALT_BRIDGE_CUTOFF = 3.2
HIS_CHARGE = 0.1

# Kyte–Doolittle (1982)，与 TNP Hydrophobics.txt 第 1 列一致
KYTE_DOOLITTLE = {
    "I": 4.5,
    "V": 4.2,
    "L": 3.8,
    "F": 2.8,
    "C": 2.5,
    "M": 1.9,
    "A": 1.8,
    "G": -0.4,
    "T": -0.7,
    "S": -0.8,
    "W": -0.9,
    "Y": -1.3,
    "P": -1.6,
    "H": -3.2,
    "E": -3.5,
    "Q": -3.5,
    "D": -3.5,
    "N": -3.5,
    "K": -3.9,
    "R": -4.5,
}

BACKBONE_ATOMS = frozenset({"N", "CA", "C"})
DONOR_ATOMS = {
    "K": frozenset({"NZ"}),
    "R": frozenset({"NH1", "NH2"}),
}
ACCEPTOR_ATOMS = {
    "D": frozenset({"OD1", "OD2"}),
    "E": frozenset({"OE1", "OE2"}),
}

DISCLAIMER = (
    "Kabat 编号；L / L3 / C / PSH / PPC / PNC 相对 36 条临床 VHH 参考集切绿、黄、红"
    "（红=超出临床 min/max，黄≈两端 5%；L/L3 高段外扩 1）。"
)
