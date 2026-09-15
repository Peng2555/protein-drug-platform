"""表面正电 / 负电 / 疏水斑（Cβ 8 Å）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from cic_profile.constants import (
    CHARGE_ABS_MIN,
    DEFAULT_PH,
    HYDROPHOBIC,
    KD_SCALE,
    KYTE_DOOLITTLE,
    PATCH_CUTOFF,
    SURFACE_RSA_CHARGE,
    SURFACE_RSA_HYDRO,
)
from cic_profile.protonation import effective_charge
from boltzfold_shared.geometry.sasa import res_iter, residue_sasa


def _cb_or_ca(res) -> np.ndarray | None:
    named = {atom.name.strip(): atom for atom in res}
    atom = named.get("CB") or named.get("CA")
    if atom is None:
        return None
    p = atom.pos
    return np.array([p.x, p.y, p.z], dtype=np.float64)


def _coords_map(structure_path: Path) -> dict[tuple[str, int], np.ndarray]:
    import gemmi

    st = gemmi.read_structure(str(structure_path))
    coords: dict[tuple[str, int], np.ndarray] = {}
    for chain in st[0]:
        for res in res_iter(chain):
            xyz = _cb_or_ca(res)
            if xyz is None:
                continue
            coords[(chain.name, int(res.seqid.num))] = xyz
    return coords


def hydro_sasa(aa: str, sasa: float) -> float:
    kd = max(float(KYTE_DOOLITTLE.get(aa, 0.0)), 0.0)
    return round(sasa * (kd / KD_SCALE), 3)


def _union_find_cluster(
    members: list[dict[str, Any]],
    coords: dict[tuple[str, int], np.ndarray],
    cutoff: float,
) -> list[list[int]]:
    n = len(members)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        a, b = find(i), find(j)
        if a != b:
            parent[b] = a

    for i, a in enumerate(members):
        xa = coords.get((a["chain"], a["position"]))
        if xa is None:
            continue
        for j in range(i + 1, n):
            b = members[j]
            xb = coords.get((b["chain"], b["position"]))
            if xb is None:
                continue
            if float(np.linalg.norm(xa - xb)) <= cutoff:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def cluster_cic_patches(
    structure_path: Path,
    *,
    ph: float = DEFAULT_PH,
    patch_cut: float = PATCH_CUTOFF,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    residues = residue_sasa(structure_path)
    coords = _coords_map(structure_path)

    pos_nodes: list[dict[str, Any]] = []
    neg_nodes: list[dict[str, Any]] = []
    hyd_nodes: list[dict[str, Any]] = []

    for row in residues:
        aa = row["aa"]
        rsa = float(row["rsa"])
        q = effective_charge(aa, ph)
        row["charge"] = q
        row["hydrophobic"] = aa in HYDROPHOBIC
        row["surface_charge"] = abs(q) >= CHARGE_ABS_MIN and rsa >= SURFACE_RSA_CHARGE
        row["surface_hydro"] = aa in HYDROPHOBIC and rsa >= SURFACE_RSA_HYDRO
        row["hydro_sasa"] = hydro_sasa(aa, float(row["sasa"])) if aa in HYDROPHOBIC else 0.0
        row["charge_sasa"] = round(q * float(row["sasa"]), 3)
        row["patch_id"] = None
        row["patch_kind"] = None
        row["hydro_patch_id"] = None
        row["charge_patch_id"] = None
        if row["surface_charge"] and q > 0:
            pos_nodes.append(row)
        elif row["surface_charge"] and q < 0:
            neg_nodes.append(row)
        if row["surface_hydro"]:
            hyd_nodes.append(row)

    patches: list[dict[str, Any]] = []

    def emit(kind: str, prefix: str, nodes: list[dict[str, Any]], score_key: str) -> None:
        if not nodes:
            return
        groups = _union_find_cluster(nodes, coords, patch_cut)
        ranked = sorted(
            groups,
            key=lambda m: -abs(sum(float(nodes[i].get(score_key) or 0.0) for i in m)),
        )
        for idx, members in enumerate(ranked, start=1):
            pid = f"{prefix}{idx}"
            res_list = []
            score = 0.0
            for i in members:
                if kind == "hydrophobic":
                    nodes[i]["hydro_patch_id"] = pid
                else:
                    nodes[i]["charge_patch_id"] = pid
                score += float(nodes[i].get(score_key) or 0.0)
                res_list.append(f"{nodes[i]['chain']}:{nodes[i]['aa']}{nodes[i]['position']}")
            patches.append(
                {
                    "patch_id": pid,
                    "kind": kind,
                    "n_residues": len(members),
                    "score": round(abs(score), 3),
                    "residues": res_list,
                }
            )

    emit("hydrophobic", "Hyd", hyd_nodes, "hydro_sasa")
    emit("positive", "Pos", pos_nodes, "charge_sasa")
    emit("negative", "Neg", neg_nodes, "charge_sasa")

    # 同一残基若既在电荷斑又在疏水斑，3D 优先显示电荷斑
    for row in residues:
        charge_pid = row.get("charge_patch_id")
        hydro_pid = row.get("hydro_patch_id")
        row["patch_id"] = charge_pid or hydro_pid
        if charge_pid:
            row["patch_kind"] = "positive" if str(charge_pid).startswith("Pos") else "negative"
        elif hydro_pid:
            row["patch_kind"] = "hydrophobic"
    return residues, patches
