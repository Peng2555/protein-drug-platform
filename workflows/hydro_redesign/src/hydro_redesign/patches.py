"""表面疏水残基与斑聚类。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from hydro_redesign.constants import (
    HYDROPHOBIC,
    KD_SCALE,
    KYTE_DOOLITTLE,
    PATCH_CUTOFF,
    SURFACE_RSA,
)
from hydro_redesign.sasa import THREE_TO_ONE, res_iter, residue_sasa


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


def cluster_patches(
    structure_path: Path,
    *,
    rsa_cut: float = SURFACE_RSA,
    patch_cut: float = PATCH_CUTOFF,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    residues = residue_sasa(structure_path)
    coords = _coords_map(structure_path)
    surface = []
    for row in residues:
        aa = row["aa"]
        rsa = float(row["rsa"])
        row["hydrophobic"] = aa in HYDROPHOBIC
        row["surface"] = rsa >= rsa_cut
        row["hydro_sasa"] = hydro_sasa(aa, float(row["sasa"])) if aa in HYDROPHOBIC else 0.0
        row["patch_id"] = None
        if row["hydrophobic"] and row["surface"]:
            surface.append(row)

    parent = list(range(len(surface)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        a, b = find(i), find(j)
        if a != b:
            parent[b] = a

    for i, a in enumerate(surface):
        xa = coords.get((a["chain"], a["position"]))
        if xa is None:
            continue
        for j in range(i + 1, len(surface)):
            b = surface[j]
            xb = coords.get((b["chain"], b["position"]))
            if xb is None:
                continue
            if float(np.linalg.norm(xa - xb)) <= patch_cut:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(len(surface)):
        groups.setdefault(find(i), []).append(i)

    patches: list[dict[str, Any]] = []
    for idx, members in enumerate(sorted(groups.values(), key=lambda m: -sum(surface[i]["hydro_sasa"] for i in m)), start=1):
        pid = f"P{idx}"
        res_list = []
        score = 0.0
        for i in members:
            surface[i]["patch_id"] = pid
            score += float(surface[i]["hydro_sasa"])
            res_list.append(f"{surface[i]['chain']}:{surface[i]['aa']}{surface[i]['position']}")
        patches.append(
            {
                "patch_id": pid,
                "n_residues": len(members),
                "score": round(score, 3),
                "residues": res_list,
            }
        )

    by_key = {(r["chain"], r["position"]): r for r in surface}
    for row in residues:
        hit = by_key.get((row["chain"], row["position"]))
        if hit:
            row["patch_id"] = hit["patch_id"]
            row["hydro_sasa"] = hit["hydro_sasa"]
            row["hydrophobic"] = True
            row["surface"] = True
        else:
            row.setdefault("hydrophobic", row["aa"] in HYDROPHOBIC)
            row.setdefault("surface", float(row["rsa"]) >= rsa_cut)
            row.setdefault("hydro_sasa", hydro_sasa(row["aa"], float(row["sasa"])) if row["aa"] in HYDROPHOBIC else 0.0)
            row.setdefault("patch_id", None)
    return residues, patches
