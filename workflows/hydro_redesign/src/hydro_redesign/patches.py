"""从原子级 SAP 切出可改造的表面疏水斑。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from hydro_redesign.constants import (
    PATCH_LINK_RADIUS,
    SAP_PATCH_CUTOFF,
    SAP_RADIUS,
    SURFACE_RSA,
)
from hydro_redesign.sap import (
    average_ensemble_sap,
    compute_structure_sap,
    hydrophobicity,
    residues_within_radius,
)


def hydro_sasa(aa: str, sasa: float) -> float:
    """兼容旧测试名。找斑请用 sap。"""
    del sasa
    return round(max(hydrophobicity(aa), 0.0), 3)


def _is_surface(row: dict[str, Any], rsa_cut: float) -> bool:
    return float(row.get("rsa") or 0.0) >= rsa_cut or float(row.get("sc_rsa") or 0.0) >= rsa_cut


def is_engineerable_patch_residue(
    row: dict[str, Any],
    *,
    sap_cut: float,
    rsa_cut: float,
) -> bool:
    """可改造斑成员：表面暴露、自身疏水、SAP 够高、不是 Cys。"""
    if str(row.get("aa") or "") == "C":
        return False
    if float(row.get("phi") or 0.0) <= 0:
        return False
    if float(row.get("sap") or 0.0) < sap_cut:
        return False
    return _is_surface(row, rsa_cut)


def cluster_patches(
    structure_path: Path,
    *,
    rsa_cut: float | None = SURFACE_RSA,
    patch_cut: float = PATCH_LINK_RADIUS,
    sap_cut: float = SAP_PATCH_CUTOFF,
    sap_radius: float = SAP_RADIUS,
    ensemble: Sequence[Path] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rsa_cut = SURFACE_RSA if rsa_cut is None else float(rsa_cut)
    selected = Path(structure_path)
    structures = [Path(p) for p in ensemble] if ensemble else [selected]
    residues, atoms = compute_structure_sap(selected, radius=sap_radius)
    if len(structures) <= 1:
        for row in residues:
            row.setdefault("sap_std", 0.0)
            row.setdefault("sap_n", 1)
    else:
        avg_rows, n_ok = average_ensemble_sap(structures, radius=sap_radius)
        avg_map = {(r["chain"], int(r["position"])): r for r in avg_rows}
        for row in residues:
            hit = avg_map.get((row["chain"], int(row["position"])))
            if not hit:
                row.setdefault("sap_std", 0.0)
                row.setdefault("sap_n", 1)
                continue
            row["sap"] = hit["sap"]
            row["sap_std"] = hit.get("sap_std", 0.0)
            row["sap_n"] = hit.get("sap_n", n_ok)
            row["hydro_sasa"] = row["sap"]

    for row in residues:
        row["surface"] = _is_surface(row, rsa_cut)
        row["hydrophobic"] = float(row.get("phi") or 0.0) > 0

    hot = [
        row
        for row in residues
        if is_engineerable_patch_residue(row, sap_cut=sap_cut, rsa_cut=rsa_cut)
    ]
    parent = list(range(len(hot)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        a, b = find(i), find(j)
        if a != b:
            parent[b] = a

    for i, a in enumerate(hot):
        ka = (a["chain"], int(a["position"]))
        for j in range(i + 1, len(hot)):
            b = hot[j]
            kb = (b["chain"], int(b["position"]))
            if residues_within_radius(atoms, ka, kb, radius=patch_cut, sidechain_only=True):
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(len(hot)):
        groups.setdefault(find(i), []).append(i)

    patches: list[dict[str, Any]] = []
    for idx, members in enumerate(
        sorted(groups.values(), key=lambda m: -sum(float(hot[i]["sap"]) for i in m)),
        start=1,
    ):
        pid = f"P{idx}"
        res_list = []
        score = 0.0
        for i in members:
            hot[i]["patch_id"] = pid
            score += float(hot[i]["sap"])
            res_list.append(f"{hot[i]['chain']}:{hot[i]['aa']}{hot[i]['position']}")
        patches.append(
            {
                "patch_id": pid,
                "n_residues": len(members),
                "score": round(score, 3),
                "mean_sap": round(score / len(members), 4) if members else 0.0,
                "residues": res_list,
            }
        )

    by_key = {(r["chain"], int(r["position"])): r for r in hot}
    for row in residues:
        hit = by_key.get((row["chain"], int(row["position"])))
        row["patch_id"] = hit["patch_id"] if hit else None
        row["hydro_sasa"] = float(row.get("sap") or 0.0)
    return residues, patches
