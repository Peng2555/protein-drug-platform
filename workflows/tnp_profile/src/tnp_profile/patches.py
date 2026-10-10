"""PSH / PPC / PNC：TAP/TNP 成对 Coulomb 斑分。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tnp_profile.constants import (
    ACCEPTOR_ATOMS,
    DONOR_ATOMS,
    HIS_CHARGE,
    PAIR_CUTOFF,
    SALT_BRIDGE_CUTOFF,
    SURFACE_ASA,
    VICINITY_CUTOFF,
)
from tnp_profile.hydrophobicity import GLY_HYDROPHOBICITY, scaled_hydrophobicity
from tnp_profile.structure import min_atom_distance, pick_chain, salt_bridge_distance


def _formal_charge(aa: str) -> float:
    if aa in {"D", "E"}:
        return -1.0
    if aa in {"K", "R"}:
        return 1.0
    if aa == "H":
        return HIS_CHARGE
    return 0.0


def _sasa_map(structure_path: Path) -> dict[tuple[str, int], float]:
    from boltzfold_shared.geometry.sasa import residue_sasa

    out: dict[tuple[str, int], float] = {}
    for row in residue_sasa(structure_path):
        out[(str(row["chain"]), int(row["position"]))] = float(row["sasa"])
    return out


def patch_scores(
    structure_path: Path,
    residues_struct: list[dict[str, Any]],
    annotation: dict[str, Any],
    sequence: str,
) -> dict[str, Any]:
    chain_id = pick_chain(residues_struct, sequence, preferred="H")
    chain_res = [r for r in residues_struct if r["chain"] == chain_id]
    by_pos = {r["position"]: r for r in chain_res}
    sasa = _sasa_map(structure_path)

    surface: dict[int, dict[str, Any]] = {}
    for ann in annotation["residues"]:
        pos = int(ann["pdb_pos"])
        st = by_pos.get(pos)
        if st is None:
            continue
        asa = sasa.get((chain_id, pos), 0.0)
        if asa < SURFACE_ASA:
            continue
        aa = st["aa"]
        charge = _formal_charge(aa)
        rec = {
            "ann": ann,
            "res": st,
            "aa": aa,
            "asa": asa,
            "hydrophobic": scaled_hydrophobicity(aa),
            "charge": charge,
            "positive": charge if charge > 0 else 0.0,
            "negative": charge if charge < 0 else 0.0,
            "in_cdr_pm2": bool(ann.get("vicinity_loop")),
        }
        surface[pos] = rec

    # salt bridges among surface residues
    positions = list(surface)
    for i, p1 in enumerate(positions):
        r1 = surface[p1]
        for p2 in positions[i + 1 :]:
            r2 = surface[p2]
            a1, a2 = r1["aa"], r2["aa"]
            d = 1e9
            if a1 in DONOR_ATOMS and a2 in ACCEPTOR_ATOMS:
                d = salt_bridge_distance(r1["res"], r2["res"], DONOR_ATOMS[a1], ACCEPTOR_ATOMS[a2])
            elif a2 in DONOR_ATOMS and a1 in ACCEPTOR_ATOMS:
                d = salt_bridge_distance(r2["res"], r1["res"], DONOR_ATOMS[a2], ACCEPTOR_ATOMS[a1])
            if d < SALT_BRIDGE_CUTOFF:
                for rec in (r1, r2):
                    rec["charge"] = 0.0
                    rec["positive"] = 0.0
                    rec["negative"] = 0.0
                    rec["hydrophobic"] = GLY_HYDROPHOBICITY
                    rec["salt_bridged"] = True

    vicinity: set[int] = {p for p, rec in surface.items() if rec["in_cdr_pm2"]}
    cdr_set = set(vicinity)
    for p1 in list(cdr_set):
        for p2, rec2 in surface.items():
            if p2 in vicinity:
                continue
            if min_atom_distance(surface[p1]["res"], rec2["res"]) < VICINITY_CUTOFF:
                vicinity.add(p2)

    # 官方对 i≠j 有序对累加，等价于无向对的 2 倍
    psh = ppc = pnc = 0.0
    vic_list = sorted(vicinity)
    for p1 in vic_list:
        r1 = surface[p1]
        for p2 in vic_list:
            if p1 == p2:
                continue
            r2 = surface[p2]
            d = min_atom_distance(r1["res"], r2["res"])
            if d > PAIR_CUTOFF or d <= 1e-9:
                continue
            inv = 1.0 / (d * d)
            psh += r1["hydrophobic"] * r2["hydrophobic"] * inv
            ppc += r1["positive"] * r2["positive"] * inv
            pnc += r1["negative"] * r2["negative"] * inv

    rows = []
    for ann in annotation["residues"]:
        pos = int(ann["pdb_pos"])
        rec = surface.get(pos)
        rows.append(
            {
                "chain": chain_id,
                "position": pos,
                "aa": ann["aa"],
                "kabat": ann.get("kabat_label") or "",
                "region": ann.get("region") or "",
                "sasa": rec["asa"] if rec else sasa.get((chain_id, pos), 0.0),
                "surface": rec is not None,
                "in_vicinity": pos in vicinity,
                "hydrophobic": rec["hydrophobic"] if rec else scaled_hydrophobicity(ann["aa"]),
                "charge": rec["charge"] if rec else _formal_charge(ann["aa"]),
                "salt_bridged": bool(rec.get("salt_bridged")) if rec else False,
            }
        )
    return {
        "PSH": round(psh, 4),
        "PPC": round(ppc, 4),
        "PNC": round(pnc, 4),
        "chain": chain_id,
        "n_surface": len(surface),
        "n_vicinity": len(vicinity),
        "residues": rows,
    }
