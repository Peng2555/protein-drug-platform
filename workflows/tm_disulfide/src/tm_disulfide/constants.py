"""Boltz2 结构质控用的固定规则。"""

from __future__ import annotations

THREE_TO_ONE = {
    "ALA": "A",
    "ARG": "R",
    "ASN": "N",
    "ASP": "D",
    "CYS": "C",
    "CYD": "C",
    "CYX": "C",
    "CSS": "C",
    "GLN": "Q",
    "GLU": "E",
    "GLY": "G",
    "HIS": "H",
    "ILE": "I",
    "LEU": "L",
    "LYS": "K",
    "MET": "M",
    "PHE": "F",
    "PRO": "P",
    "SER": "S",
    "THR": "T",
    "TRP": "W",
    "TYR": "Y",
    "VAL": "V",
}

BACKBONE_ATOMS = ("N", "CA", "C", "O")
# SG–SG 落在此区间则记为「已有二硫键」，只记录不设计。
SS_SG_MIN = 1.6
SS_SG_MAX = 2.5
COORD_DUP_EPS = 1e-3
# 第二次叠合丢掉 RMSF 最高的这一比例残基，避免环区带偏刚体。
CORE_RMSF_DROP_FRACTION = 0.20
MIN_ALIGNMENT_CA = 3

# 可设计位点硬过滤（Kabat 插入码按整数位归入同一 CDR/FR）。
KABAT_CDR_HEAVY = {
    "CDR-H1": (31, 35),
    "CDR-H2": (50, 65),
    "CDR-H3": (95, 102),
}
KABAT_CDR_LIGHT = {
    "CDR-L1": (24, 34),
    "CDR-L2": (50, 56),
    "CDR-L3": (89, 97),
}
MINIMUM_CONFIDENCE = 80.0
MAXIMUM_CA_RMSF = 1.0
EXCLUDE_GLYCINE = True
EXCLUDE_PROLINE = True
EXCLUDE_CDR = True

# 残基对距离粗筛（宽松窗；SG 几何留给下一步）。
MINIMUM_SEQUENCE_SEPARATION = 8
MAXIMUM_CA_DISTANCE = 7.0
MAXIMUM_CB_DISTANCE = 6.0
MAXIMUM_CA_DISTANCE_ANY = 8.0
MAXIMUM_CB_DISTANCE_ANY = 7.0
# 面对面：两边 CA→CB 都朝向对方 CA（夹角≤90°），且两侧链不完全同向。
MAXIMUM_CB_TOWARD_ANGLE = 90.0
MAXIMUM_CA_CB_DOT = 0.0
MINIMUM_MODELS_PASSED = 4

# 虚拟 Cys SG 几何（不改真实结构、不上 PyRosetta）。
CB_SG_BOND_LENGTH = 1.81
CA_CB_SG_ANGLE = 113.8
SG_ROTATION_STEP = 5.0
SS_DISTANCE_MIN = 1.80
SS_DISTANCE_MAX = 2.30
SS_DISTANCE_TARGET = 2.03
CB_SG_SG_ANGLE_MIN = 90.0
CB_SG_SG_ANGLE_MAX = 120.0
CB_SG_SG_ANGLE_TARGET = 105.0
CHI3_TARGETS = (-87.0, 97.0)
CHI3_DEVIATION_MAX = 40.0
CHI1_TARGETS = (-60.0, 60.0, 180.0)
CHI1_DEVIATION_MAX = 40.0
SG_CLASH_DISTANCE = 2.0
GEOMETRY_TOP_N = 10

# 显式成键验收：SG–SG 与质控原生窗一致。
# χ3 放宽到覆盖本套结构原生 22–96（约 43–45°）；虚拟预筛仍用 CHI3_DEVIATION_MAX。
BUILD_SS_MIN = SS_SG_MIN
BUILD_SS_MAX = SS_SG_MAX
BUILD_CHI3_DEVIATION_MAX = 45.0
BUILD_CB_SG_MIN = 1.70
BUILD_CB_SG_MAX = 1.95
BUILD_LOCAL_CA_RADIUS = 8.0
BUILD_SS_CONSTRAINT = 2.03
BUILD_SS_CONSTRAINT_SD = 0.08
BUILD_ANGLE_CONSTRAINT_SD = 10.0

# WT / 突变体同一套局部打包+松弛后比折叠态。
# ΔΔG = E_mut(无ref) − E_wt(无ref)，只用于排序；通过与否看成键和碰撞。
ENERGY_LOCAL_RADIUS = BUILD_LOCAL_CA_RADIUS
ENERGY_DDG_MAX = 0.0
ENERGY_REP_DELTA_MAX = 40.0
