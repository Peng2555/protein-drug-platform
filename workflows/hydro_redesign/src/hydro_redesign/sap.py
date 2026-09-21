"""原子级 Spatial Aggregation Propensity（Chennamsetty et al., PNAS 2009）。

SAP_i = Σ_{j: |r_i - r_j| < 5 Å} (SAA_j / SAA_j,max) * φ_j

i、j 均为重原子。φ 为所属残基的 Black–Mould 疏水性（Gly = 0）。
SAA 为蛋白环境中的原子可及面积；SAA_max 为该残基单独存在时同一原子的可及面积
（完全暴露残基近似）。残基 SAP 取侧链原子平均（Gly 用 CA）。
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from boltzfold_shared.geometry.sasa import atom_sasa, residues_from_atoms
from hydro_redesign.constants import BLACK_MOULD_GLY0, SAP_RADIUS


def hydrophobicity(aa: str) -> float:
    return float(BLACK_MOULD_GLY0.get(aa, 0.0))


def _residue_key(atom: dict[str, Any]) -> tuple[str, int]:
    return (str(atom["chain"]), int(atom["seq"]))


def apply_atom_sap(atoms: list[dict[str, Any]], *, radius: float = SAP_RADIUS) -> None:
    if not atoms:
        return
    xyz = np.stack([a["xyz"] for a in atoms])
    rsa = np.array([min(max(float(a.get("rsa") or 0.0), 0.0), 1.0) for a in atoms], dtype=np.float64)
    phi = np.array([hydrophobicity(str(a.get("aa") or "") ) for a in atoms], dtype=np.float64)
    contrib = rsa * phi
    r2 = float(radius) ** 2
    for i, atom in enumerate(atoms):
        d2 = ((xyz - xyz[i]) ** 2).sum(axis=1)
        atom["sap"] = round(float(contrib[d2 <= r2].sum()), 4)
        atom["phi"] = round(float(phi[i]), 4)


def residue_sap_from_atoms(atoms: list[dict[str, Any]]) -> dict[tuple[str, int], float]:
    buckets: dict[tuple[str, int], list[float]] = {}
    gly_ca: dict[tuple[str, int], list[float]] = {}
    aa_of: dict[tuple[str, int], str] = {}
    for atom in atoms:
        key = _residue_key(atom)
        aa_of[key] = str(atom.get("aa") or "")
        sap = float(atom.get("sap") or 0.0)
        if atom.get("name") == "CA":
            gly_ca.setdefault(key, []).append(sap)
        if not atom.get("backbone"):
            buckets.setdefault(key, []).append(sap)
    out: dict[tuple[str, int], float] = {}
    for key, aa in aa_of.items():
        values = buckets.get(key) or gly_ca.get(key) or []
        if aa == "G":
            values = gly_ca.get(key) or values
        out[key] = round(float(sum(values) / len(values)), 4) if values else 0.0
    return out


def compute_structure_sap(
    structure_path: Path,
    *,
    radius: float = SAP_RADIUS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    atoms = atom_sasa(structure_path)
    apply_atom_sap(atoms, radius=radius)
    residues = residues_from_atoms(atoms)
    sap_map = residue_sap_from_atoms(atoms)
    for row in residues:
        key = (row["chain"], int(row["position"]))
        phi = hydrophobicity(str(row["aa"]))
        row["phi"] = round(phi, 4)
        row["sap"] = sap_map.get(key, 0.0)
        row["hydrophobic"] = phi > 0
        row["surface"] = float(row.get("rsa") or 0.0) >= 0.25 or float(row.get("sc_rsa") or 0.0) >= 0.25
        row["hydro_sasa"] = row["sap"]
    return residues, atoms


def residue_atom_index(atoms: list[dict[str, Any]]) -> dict[tuple[str, int], list[int]]:
    index: dict[tuple[str, int], list[int]] = {}
    for i, atom in enumerate(atoms):
        index.setdefault(_residue_key(atom), []).append(i)
    return index


def residues_within_radius(
    atoms: list[dict[str, Any]],
    keys_a: tuple[str, int],
    keys_b: tuple[str, int],
    *,
    radius: float,
    sidechain_only: bool = False,
) -> bool:
    index = residue_atom_index(atoms)
    ia = index.get(keys_a) or []
    ib = index.get(keys_b) or []

    def take(idxs: list[int]) -> list[int]:
        if not sidechain_only:
            return idxs
        sc = [i for i in idxs if not atoms[i].get("backbone") or atoms[i].get("name") == "CA"]
        return sc or idxs

    ia, ib = take(ia), take(ib)
    if not ia or not ib:
        return False
    r2 = float(radius) ** 2
    xa = np.stack([atoms[i]["xyz"] for i in ia])
    xb = np.stack([atoms[i]["xyz"] for i in ib])
    for p in xa:
        if float(((xb - p) ** 2).sum(axis=1).min()) <= r2:
            return True
    return False


def discover_ensemble_structures(root: Path | None, selected: Path) -> list[Path]:
    """Boltz2 的 *_model_N 结构；没有多样本时退回当前结构。"""
    selected = selected.resolve()
    if root is None or not Path(root).is_dir():
        return [selected]
    by_idx: dict[int, Path] = {}
    for path in Path(root).rglob("*"):
        if not path.is_file():
            continue
        if path.name.lower().startswith("pred"):
            continue
        match = re.search(r"_model_(\d+)\.(cif|pdb)$", path.name, re.I)
        if not match:
            continue
        idx = int(match.group(1))
        prev = by_idx.get(idx)
        if prev is None or (path.suffix.lower() == ".cif" and prev.suffix.lower() != ".cif"):
            by_idx[idx] = path
    paths = [by_idx[i] for i in sorted(by_idx)]
    if not paths:
        return [selected]
    return [path.resolve() for path in paths]


def average_ensemble_sap(
    structures: Iterable[Path],
    *,
    radius: float = SAP_RADIUS,
) -> tuple[list[dict[str, Any]], int]:
    structures = [Path(p) for p in structures]
    if not structures:
        raise ValueError("SAP 需要至少一套结构")
    per_key: dict[tuple[str, int], list[float]] = {}
    template: dict[tuple[str, int], dict[str, Any]] | None = None
    n_ok = 0
    for idx, path in enumerate(structures):
        residues, _atoms = compute_structure_sap(path, radius=radius)
        if idx == 0:
            template = {(row["chain"], int(row["position"])): dict(row) for row in residues}
        n_ok += 1
        for row in residues:
            key = (row["chain"], int(row["position"]))
            per_key.setdefault(key, []).append(float(row["sap"]))
    assert template is not None
    out: list[dict[str, Any]] = []
    for key, row in sorted(template.items()):
        values = per_key.get(key) or [float(row.get("sap") or 0.0)]
        mean = sum(values) / len(values)
        if len(values) > 1:
            var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
            std = math.sqrt(var)
        else:
            std = 0.0
        row["sap"] = round(mean, 4)
        row["sap_std"] = round(std, 4)
        row["sap_n"] = len(values)
        row["hydro_sasa"] = row["sap"]
        out.append(row)
    return out, n_ok
