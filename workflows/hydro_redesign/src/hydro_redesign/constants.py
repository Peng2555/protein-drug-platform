"""疏水改造：SAP 找斑所用的固定参数与氨基酸表。"""

from __future__ import annotations

# Black & Mould 1991 疏水性，Phe=1、Arg=0。
# SAP 使用减去 Gly 后的相对值（Chennamsetty et al., PNAS 2009）。
BLACK_MOULD: dict[str, float] = {
    "A": 0.616,
    "R": 0.000,
    "N": 0.236,
    "D": 0.028,
    "C": 0.680,
    "Q": 0.251,
    "E": 0.043,
    "G": 0.501,
    "H": 0.165,
    "I": 0.943,
    "L": 0.943,
    "K": 0.283,
    "M": 0.738,
    "F": 1.000,
    "P": 0.711,
    "S": 0.359,
    "T": 0.450,
    "W": 0.878,
    "Y": 0.880,
    "V": 0.825,
}
BLACK_MOULD_GLY0: dict[str, float] = {
    aa: round(value - BLACK_MOULD["G"], 6) for aa, value in BLACK_MOULD.items()
}

# Kyte–Doolittle：仅用于突变亲水差值，不参与找斑。
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

HYDROPHOBIC = frozenset(aa for aa, phi in BLACK_MOULD_GLY0.items() if phi > 0)
# 中性替换。丙氨酸在 Kyte–Doolittle 上为 +1.8，不作为亲水选项。
HYDROPHILIC_DEFAULT = tuple("STNQ")
HYDROPHILIC_CHARGED = tuple("DEKR")

# Tien et al. 2013 empirical max ASA (Å²)
MAX_ASA: dict[str, float] = {
    "A": 129.0,
    "R": 274.0,
    "N": 195.0,
    "D": 193.0,
    "C": 167.0,
    "Q": 225.0,
    "E": 223.0,
    "G": 104.0,
    "H": 224.0,
    "I": 197.0,
    "L": 201.0,
    "K": 265.0,
    "M": 224.0,
    "F": 240.0,
    "P": 159.0,
    "S": 155.0,
    "T": 172.0,
    "W": 285.0,
    "Y": 263.0,
    "V": 174.0,
}

VDW_RADII = {
    "C": 1.70,
    "N": 1.55,
    "O": 1.52,
    "S": 1.80,
    "H": 1.20,
    "P": 1.80,
    "SE": 1.90,
}

PROBE_RADIUS = 1.4
SURFACE_RSA = 0.25
SAP_RADIUS = 5.0
# 可改造斑：自身疏水且表面暴露；0.15 是文献着色线，对本标尺过低。
SAP_PATCH_CUTOFF = 0.5
# 斑连通只用侧链，避免主链 5 Å 把整条链焊在一起。
PATCH_LINK_RADIUS = 6.0
PATCH_CUTOFF = PATCH_LINK_RADIUS
KD_SCALE = 4.5  # ILE
N_SPHERE = 92
FREEZE_NTERM = 4
FREEZE_CTERM = 4
WETLAB_TOP_N = 20
# 复折后的筛选门。位点 pLDDT 不低于 70，相对野生型下跌不超过 10；整链均值不低于 60。
SCREEN_PLDDT_MIN = 70.0
SCREEN_PLDDT_DROP_MAX = 10.0
SCREEN_CHAIN_PLDDT_MIN = 60.0
# 原斑 SAP 合计至少下降 0.2，且不出现分数 ≥ 0.5 的新斑。
SCREEN_SAP_DROP_MIN = 0.2
# 每个斑最多取 SAP 最高的 4 个框架区位点，再枚举全部非空组合。
SCREEN_MAX_SITES_PER_PATCH = 4
# 亲水差值相同时的替换顺序：谷氨酰胺优先于天冬酰胺。
SUBSTITUTION_PREFERENCE = {"Q": 0, "N": 1, "S": 2, "T": 3, "D": 4, "E": 5, "K": 6, "R": 7}
HYDROPHOBICITY_SCALE = "SAP atom-level / Black–Mould (Gly=0), R=5 Å"
