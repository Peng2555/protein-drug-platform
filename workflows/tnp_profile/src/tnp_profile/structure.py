"""从 PDB/CIF 读取残基坐标（去氢）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

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


def load_residues(structure_path: Path) -> list[dict[str, Any]]:
    import gemmi

    st = gemmi.read_structure(str(structure_path))
    model = st[0]
    out: list[dict[str, Any]] = []
    for chain in model:
        for res in chain:
            aa = THREE_TO_ONE.get(res.name)
            if aa is None:
                continue
            atoms = []
            for atom in res:
                if atom.element.name == "H":
                    continue
                p = atom.pos
                atoms.append(
                    {
                        "name": atom.name.strip(),
                        "xyz": np.array([p.x, p.y, p.z], dtype=np.float64),
                    }
                )
            if not atoms:
                continue
            out.append(
                {
                    "chain": chain.name,
                    "position": int(res.seqid.num),
                    "aa": aa,
                    "resname": res.name,
                    "atoms": atoms,
                }
            )
    return out


def min_atom_distance(res1: dict[str, Any], res2: dict[str, Any]) -> float:
    best = 1e9
    for a in res1["atoms"]:
        for b in res2["atoms"]:
            d = float(np.linalg.norm(a["xyz"] - b["xyz"]))
            if d < best:
                best = d
    return best


def atom_named(res: dict[str, Any], names: frozenset[str]) -> list[np.ndarray]:
    return [a["xyz"] for a in res["atoms"] if a["name"] in names]


def salt_bridge_distance(res1: dict[str, Any], res2: dict[str, Any], donor_names: frozenset[str], acceptor_names: frozenset[str]) -> float:
    donors = atom_named(res1, donor_names)
    acceptors = atom_named(res2, acceptor_names)
    if not donors or not acceptors:
        return 1e9
    best = 1e9
    for a in donors:
        for b in acceptors:
            d = float(np.linalg.norm(a - b))
            if d < best:
                best = d
    return best


def pick_chain(residues: list[dict[str, Any]], sequence: str, preferred: str = "H") -> str:
    by_chain: dict[str, str] = {}
    for r in residues:
        by_chain.setdefault(r["chain"], "")
        by_chain[r["chain"]] += r["aa"]
    if preferred in by_chain:
        return preferred
    seq = sequence.upper()
    best_id, best_score = next(iter(by_chain)), -1
    for cid, s in by_chain.items():
        score = 0
        # 连续匹配长度
        for n in range(min(len(s), len(seq)), 20, -1):
            if s[:n] == seq[:n] or s in seq or seq in s:
                score = n
                break
        if score > best_score:
            best_id, best_score = cid, score
    return best_id
