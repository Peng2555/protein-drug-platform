"""Shrake–Rupley 残基 SASA（保持原 Hydro 数值参数）。"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

MAX_ASA = {
    "A": 129.0, "R": 274.0, "N": 195.0, "D": 193.0, "C": 167.0,
    "Q": 225.0, "E": 223.0, "G": 104.0, "H": 224.0, "I": 197.0,
    "L": 201.0, "K": 265.0, "M": 224.0, "F": 240.0, "P": 159.0,
    "S": 155.0, "T": 172.0, "W": 285.0, "Y": 263.0, "V": 174.0,
}
VDW_RADII = {"C": 1.70, "N": 1.55, "O": 1.52, "S": 1.80, "H": 1.20, "P": 1.80, "SE": 1.90}
PROBE_RADIUS = 1.4
N_SPHERE = 92
BACKBONE_ATOMS = frozenset({"N", "CA", "C", "O", "OXT"})
# Miller et al. 1987 侧链最大可及面积；Gly 用 CA 近似。
MAX_SC_ASA = {
    "A": 67.0, "R": 196.0, "N": 113.0, "D": 106.0, "C": 104.0,
    "Q": 144.0, "E": 138.0, "G": 32.0, "H": 151.0, "I": 140.0,
    "L": 137.0, "K": 167.0, "M": 160.0, "F": 175.0, "P": 105.0,
    "S": 80.0, "T": 102.0, "W": 217.0, "Y": 187.0, "V": 117.0,
}
THREE_TO_ONE = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V", "MSE": "M",
}


def _sphere_points(n: int) -> np.ndarray:
    pts = []
    offset = 2.0 / n
    increment = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(n):
        y = ((i * offset) - 1) + offset / 2
        r = math.sqrt(max(0.0, 1 - y * y))
        phi = i * increment
        pts.append((math.cos(phi) * r, y, math.sin(phi) * r))
    return np.asarray(pts, dtype=np.float64)


def _atom_radius(atom) -> float | None:
    if atom.element.name == "H":
        return None
    return VDW_RADII.get(atom.element.name, 1.70)


def res_iter(chain):
    for res in chain:
        if res.name in THREE_TO_ONE or res.name == "MSE":
            yield res


def load_atoms(structure_path: Path) -> list[dict[str, Any]]:
    import gemmi

    model = gemmi.read_structure(str(structure_path))[0]
    atoms: list[dict[str, Any]] = []
    for chain in model:
        for res in res_iter(chain):
            aa = THREE_TO_ONE.get(res.name, "X")
            seq = int(res.seqid.num)
            for atom in res:
                rad = _atom_radius(atom)
                if rad is None:
                    continue
                p = atom.pos
                name = atom.name.strip()
                atoms.append({
                    "xyz": np.array([p.x, p.y, p.z], dtype=np.float64),
                    "radius": rad, "chain": chain.name, "seq": seq,
                    "aa": aa, "resname": res.name, "name": name,
                    "backbone": name in BACKBONE_ATOMS,
                })
    return atoms


def _exposed_areas(atoms: list[dict[str, Any]]) -> np.ndarray:
    if not atoms:
        return np.zeros(0, dtype=np.float64)
    xyz = np.stack([a["xyz"] for a in atoms])
    radii = np.array([a["radius"] + PROBE_RADIUS for a in atoms], dtype=np.float64)
    sphere = _sphere_points(N_SPHERE)
    area_unit = 4.0 * math.pi / N_SPHERE
    per_atom = np.zeros(len(atoms), dtype=np.float64)
    rmax = float(radii.max())
    for i, _atom in enumerate(atoms):
        ri = radii[i]
        cutoff = ri + rmax
        d2 = ((xyz - xyz[i]) ** 2).sum(axis=1)
        neigh = [j for j in range(len(atoms)) if j != i and d2[j] <= cutoff * cutoff]
        exposed = 0
        for pt in sphere:
            p = xyz[i] + pt * ri
            if all(float(np.sum((p - xyz[j]) ** 2)) > radii[j] * radii[j] for j in neigh):
                exposed += 1
        per_atom[i] = exposed * area_unit * ri * ri
    return per_atom


def atom_sasa(structure_path: Path) -> list[dict[str, Any]]:
    """每个重原子的蛋白内 SASA，以及该残基单独存在时的 SAA_max。"""
    atoms = load_atoms(structure_path)
    if not atoms:
        return []
    protein = _exposed_areas(atoms)
    by_res: dict[tuple[str, int], list[int]] = {}
    for i, atom in enumerate(atoms):
        by_res.setdefault((atom["chain"], int(atom["seq"])), []).append(i)
    sasa_max = np.zeros(len(atoms), dtype=np.float64)
    for idxs in by_res.values():
        sub = [atoms[i] for i in idxs]
        areas = _exposed_areas(sub)
        for k, i in enumerate(idxs):
            sasa_max[i] = areas[k]
    out: list[dict[str, Any]] = []
    for i, atom in enumerate(atoms):
        row = dict(atom)
        ri = float(atom["radius"]) + PROBE_RADIUS
        isolated = 4.0 * math.pi * ri * ri
        row["sasa"] = round(float(protein[i]), 4)
        row["sasa_max"] = round(float(sasa_max[i]) if sasa_max[i] > 1e-6 else isolated, 4)
        row["rsa"] = round(min(max(row["sasa"] / row["sasa_max"], 0.0), 1.0), 4) if row["sasa_max"] > 0 else 0.0
        out.append(row)
    return out


def residues_from_atoms(atoms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], dict[str, Any]] = {}
    for atom in atoms:
        key = (atom["chain"], int(atom["seq"]))
        row = grouped.setdefault(key, {
            "chain": atom["chain"], "position": int(atom["seq"]),
            "aa": atom["aa"], "sasa": 0.0, "sc_sasa": 0.0, "ca_sasa": 0.0,
        })
        sasa = float(atom.get("sasa") or 0.0)
        row["sasa"] += sasa
        if atom.get("name") == "CA":
            row["ca_sasa"] += sasa
        if not atom.get("backbone"):
            row["sc_sasa"] += sasa
    out = []
    for row in grouped.values():
        max_asa = MAX_ASA.get(row["aa"], 200.0)
        rsa = row["sasa"] / max_asa if max_asa > 0 else 0.0
        row["rsa"] = round(min(rsa, 3.0), 4)
        row["sasa"] = round(row["sasa"], 3)
        if row["aa"] == "G" or row["sc_sasa"] <= 0:
            row["sc_sasa"] = round(float(row.get("ca_sasa") or 0.0), 3)
        else:
            row["sc_sasa"] = round(float(row["sc_sasa"]), 3)
        max_sc = MAX_SC_ASA.get(row["aa"], 120.0)
        sc_rsa = row["sc_sasa"] / max_sc if max_sc > 0 else 0.0
        row["sc_rsa"] = round(min(max(sc_rsa, 0.0), 3.0), 4)
        row.pop("ca_sasa", None)
        out.append(row)
    out.sort(key=lambda row: (row["chain"], row["position"]))
    return out


def residue_sasa(structure_path: Path) -> list[dict[str, Any]]:
    return residues_from_atoms(atom_sasa(structure_path))
