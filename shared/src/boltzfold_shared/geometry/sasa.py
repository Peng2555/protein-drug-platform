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
                atoms.append({
                    "xyz": np.array([p.x, p.y, p.z], dtype=np.float64),
                    "radius": rad, "chain": chain.name, "seq": seq,
                    "aa": aa, "resname": res.name,
                })
    return atoms


def residue_sasa(structure_path: Path) -> list[dict[str, Any]]:
    atoms = load_atoms(structure_path)
    if not atoms:
        return []
    xyz = np.stack([a["xyz"] for a in atoms])
    radii = np.array([a["radius"] + PROBE_RADIUS for a in atoms], dtype=np.float64)
    sphere = _sphere_points(N_SPHERE)
    area_unit = 4.0 * math.pi / N_SPHERE
    per_atom = np.zeros(len(atoms), dtype=np.float64)
    for i, _atom in enumerate(atoms):
        ri = radii[i]
        cutoff = ri + radii.max()
        d2 = ((xyz - xyz[i]) ** 2).sum(axis=1)
        neigh = [j for j in range(len(atoms)) if j != i and d2[j] <= cutoff * cutoff]
        exposed = 0
        for pt in sphere:
            p = xyz[i] + pt * ri
            if all(float(np.sum((p - xyz[j]) ** 2)) > radii[j] * radii[j] for j in neigh):
                exposed += 1
        per_atom[i] = exposed * area_unit * ri * ri

    grouped: dict[tuple[str, int], dict[str, Any]] = {}
    for atom, sasa in zip(atoms, per_atom):
        key = (atom["chain"], atom["seq"])
        row = grouped.setdefault(key, {
            "chain": atom["chain"], "position": atom["seq"],
            "aa": atom["aa"], "sasa": 0.0,
        })
        row["sasa"] += float(sasa)
    out = []
    for row in grouped.values():
        max_asa = MAX_ASA.get(row["aa"], 200.0)
        rsa = row["sasa"] / max_asa if max_asa > 0 else 0.0
        row["rsa"] = round(min(rsa, 3.0), 4)
        row["sasa"] = round(row["sasa"], 3)
        out.append(row)
    out.sort(key=lambda row: (row["chain"], row["position"]))
    return out
