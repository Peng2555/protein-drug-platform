"""CDR3 compactness：C = L3 / ρ，ρ 为环主链质心到锚点主链质心距离。"""

from __future__ import annotations

from typing import Any

import numpy as np

from tnp_profile.constants import BACKBONE_ATOMS, KABAT_H3_C_TERM_REF


def _backbone_xyz(res: dict[str, Any]) -> list[np.ndarray]:
    return [a["xyz"] for a in res["atoms"] if a["name"] in BACKBONE_ATOMS]


def compactness_rho(
    chain_residues: list[dict[str, Any]],
    annotation_residues: list[dict[str, Any]],
) -> float | None:
    by_pos = {r["position"]: r for r in chain_residues}
    loop_xyz: list[np.ndarray] = []
    anchor_xyz: list[np.ndarray] = []
    ref_ca: np.ndarray | None = None
    for ann in annotation_residues:
        struct = by_pos.get(ann["pdb_pos"])
        if struct is None:
            continue
        if ann.get("is_h3_loop"):
            loop_xyz.extend(_backbone_xyz(struct))
        if ann.get("is_h3_anchor"):
            anchor_xyz.extend(_backbone_xyz(struct))
        if ann.get("kabat") == KABAT_H3_C_TERM_REF and not ann.get("insertion"):
            cas = [a["xyz"] for a in struct["atoms"] if a["name"] == "CA"]
            if cas:
                ref_ca = cas[0]
    if len(loop_xyz) < 3 or len(anchor_xyz) < 3:
        return None
    h = np.mean(np.stack(loop_xyz), axis=0)
    c = np.mean(np.stack(anchor_xyz), axis=0)
    rho = float(np.linalg.norm(h - c))
    if rho <= 1e-6:
        return None
    return rho


def compactness_score(l3: int, rho: float | None) -> float | None:
    if rho is None or rho <= 0 or l3 <= 0:
        return None
    return float(l3) / rho
