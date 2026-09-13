"""Shrake–Rupley 残基 SASA（不依赖 FreeSASA）。"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from hydro_redesign.constants import MAX_ASA, PROBE_RADIUS, N_SPHERE, VDW_RADII

THREE_TO_ONE = {
    "ALA": "A",
    "ARG": "R",
    "ASN": "N",
    "ASP": "D",
    "CYS": "C",
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
    "MSE": "M",
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


def load_atoms(structure_path: Path) -> list[dict[str, Any]]:
    import gemmi

    st = gemmi.read_structure(str(structure_path))
    model = st[0]
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
                atoms.append(
                    {
                        "xyz": np.array([p.x, p.y, p.z], dtype=np.float64),
                        "radius": rad,
                        "chain": chain.name,
                        "seq": seq,
                        "aa": aa,
                        "resname": res.name,
                    }
                )
    return atoms


def res_iter(chain):
    for res in chain:
        if res.name in THREE_TO_ONE or res.name == "MSE":
            yield res


def residue_sasa(structure_path: Path) -> list[dict[str, Any]]:
    atoms = load_atoms(structure_path)
    if not atoms:
        return []
    xyz = np.stack([a["xyz"] for a in atoms])
    radii = np.array([a["radius"] + PROBE_RADIUS for a in atoms], dtype=np.float64)
    sphere = _sphere_points(N_SPHERE)
    area_unit = 4.0 * math.pi / N_SPHERE

    per_atom = np.zeros(len(atoms), dtype=np.float64)
    for i, a in enumerate(atoms):
        ri = radii[i]
        cutoff = ri + radii.max()
        d2 = ((xyz - xyz[i]) ** 2).sum(axis=1)
        neigh = [j for j in range(len(atoms)) if j != i and d2[j] <= cutoff * cutoff]
        exposed = 0
        for pt in sphere:
            p = xyz[i] + pt * ri
            ok = True
            for j in neigh:
                rj = radii[j]
                if float(np.sum((p - xyz[j]) ** 2)) <= rj * rj:
                    ok = False
                    break
            if ok:
                exposed += 1
        per_atom[i] = exposed * area_unit * ri * ri

    grouped: dict[tuple[str, int], dict[str, Any]] = {}
    for a, sasa in zip(atoms, per_atom):
        key = (a["chain"], a["seq"])
        row = grouped.setdefault(
            key,
            {
                "chain": a["chain"],
                "position": a["seq"],
                "aa": a["aa"],
                "sasa": 0.0,
            },
        )
        row["sasa"] += float(sasa)

    out = []
    for row in grouped.values():
        max_asa = MAX_ASA.get(row["aa"], 200.0)
        rsa = row["sasa"] / max_asa if max_asa > 0 else 0.0
        row["rsa"] = round(min(rsa, 3.0), 4)
        row["sasa"] = round(row["sasa"], 3)
        out.append(row)
    out.sort(key=lambda r: (r["chain"], r["position"]))
    return out
