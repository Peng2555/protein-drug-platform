#!/usr/bin/env python3
"""Protein–protein interactions via PLIP (receptor/ligand chain groups)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from pdockq_runner import _load_structure


def _cif_to_pdb(cif_path: Path) -> Path:
    structure = _load_structure(cif_path)
    tmp = tempfile.NamedTemporaryFile(suffix=".pdb", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    structure.write_pdb(str(tmp_path))
    return tmp_path


def _coord_list(coord) -> list[float]:
    if coord is None:
        return [0.0, 0.0, 0.0]
    if hasattr(coord, "x"):
        return [float(coord.x), float(coord.y), float(coord.z)]
    if isinstance(coord, (tuple, list)) and len(coord) >= 3:
        return [float(coord[0]), float(coord[1]), float(coord[2])]
    return [0.0, 0.0, 0.0]


def _mk_ix(
    itype: str,
    chain_a: str,
    resnum_a: int,
    resname_a: str,
    atom_a: str,
    coord_a,
    chain_b: str,
    resnum_b: int,
    resname_b: str,
    atom_b: str,
    coord_b,
    distance: float,
    detail: str = "",
) -> dict:
    return {
        "type": itype,
        "chain_a": chain_a,
        "resnum_a": int(resnum_a),
        "resname_a": resname_a,
        "atom_a": atom_a,
        "chain_b": chain_b,
        "resnum_b": int(resnum_b),
        "resname_b": resname_b,
        "atom_b": atom_b,
        "distance_angstrom": round(float(distance), 2),
        "coord_a": _coord_list(coord_a),
        "coord_b": _coord_list(coord_b),
        "detail": detail,
    }


def _empty_summary() -> dict:
    return {
        "n_hbonds": 0,
        "n_salt_bridges": 0,
        "n_hydrophobic": 0,
        "n_polar_contacts": 0,
        "n_pi_stacking": 0,
        "n_water_bridges": 0,
        "n_contacts": 0,
        "n_total": 0,
        "n_interface_residues_a": 0,
        "n_interface_residues_b": 0,
        "engine": "plip",
    }


def _summarize(interactions: list[dict], n_res_a: int, n_res_b: int) -> dict:
    counts: dict[str, int] = {}
    for ix in interactions:
        counts[ix["type"]] = counts.get(ix["type"], 0) + 1
    return {
        "n_hbonds": counts.get("hbond", 0),
        "n_salt_bridges": counts.get("salt_bridge", 0),
        "n_hydrophobic": counts.get("hydrophobic", 0),
        "n_polar_contacts": counts.get("pi_cation", 0),
        "n_pi_stacking": counts.get("pi_stacking", 0),
        "n_water_bridges": counts.get("water_bridge", 0),
        "n_contacts": 0,
        "n_total": len(interactions),
        "n_interface_residues_a": n_res_a,
        "n_interface_residues_b": n_res_b,
        "engine": "plip",
    }


def analyze_plip_ppi(cif_path: Path, receptor_chain: str, ligand_chain: str) -> dict:
    """Run PLIP with receptor/ligand chain groups (BindCraft / PLIP PPI mode)."""
    from plip.basic import config
    from plip.exchange.report import BindingSiteReport
    from plip.structure.preparation import PDBComplex

    pdb_path = _cif_to_pdb(cif_path)
    try:
        config.NOFIXFILE = True
        config.NOFIX = True
        config.PEPTIDES = []
        config.INTRA = None
        config.REGIONS = None
        config.CHAINS = [[receptor_chain], [ligand_chain]]

        mol = PDBComplex()
        mol.load_pdb(str(pdb_path))
        for lig in mol.ligands:
            mol.characterize_complex(lig)

        if not mol.interaction_sets:
            return {"interactions": [], "summary": _empty_summary(), "error": "PLIP: no interaction set"}

        iset = list(mol.interaction_sets.values())[0]
        report = BindingSiteReport(iset)
        interactions: list[dict] = []

        for row in report.hbond_info:
            _, restype, reschain, resnr_l, restype_l, reschain_l, sidechain, dist_ha, dist_da, angle, protisdon, _, dtype, _, atype, ligcoords, protcoords = row
            resnr = row[0]
            interactions.append(
                _mk_ix(
                    "hbond",
                    reschain,
                    resnr,
                    restype,
                    f"{'Don' if protisdon else 'Acc'}:{dtype or '?'}",
                    protcoords,
                    reschain_l,
                    resnr_l,
                    restype_l,
                    f"{'Acc' if protisdon else 'Don'}:{atype or '?'}",
                    ligcoords,
                    float(dist_da),
                    f"D-A {dist_da}Å · H-A {dist_ha}Å · ∠{angle}° · {'侧链' if sidechain else '主链'}",
                )
            )

        for row in report.saltbridge_info:
            _, restype, reschain, _, resnr_l, restype_l, reschain_l, dist, protispos, group, _, ligcoords, protcoords = row
            resnr = row[0]
            interactions.append(
                _mk_ix(
                    "salt_bridge",
                    reschain,
                    resnr,
                    restype,
                    "Salt+",
                    protcoords,
                    reschain_l,
                    resnr_l,
                    restype_l,
                    group or "Salt-",
                    ligcoords,
                    float(dist),
                    f"盐桥 {dist}Å",
                )
            )

        for row in report.hydrophobic_info:
            _, restype, reschain, resnr_l, restype_l, reschain_l, dist, _, _, ligcoords, protcoords = row
            resnr = row[0]
            interactions.append(
                _mk_ix(
                    "hydrophobic",
                    reschain,
                    resnr,
                    restype,
                    "CB",
                    protcoords,
                    reschain_l,
                    resnr_l,
                    restype_l,
                    "CB",
                    ligcoords,
                    float(dist),
                    f"疏水 {dist}Å",
                )
            )

        for row in report.pistacking_info:
            _, restype, reschain, resnr_l, restype_l, reschain_l, _, centdist, angle, offset, pitype, _, ligcoords, protcoords = row
            resnr = row[0]
            interactions.append(
                _mk_ix(
                    "pi_stacking",
                    reschain,
                    resnr,
                    restype,
                    "Ring",
                    protcoords,
                    reschain_l,
                    resnr_l,
                    restype_l,
                    "Ring",
                    ligcoords,
                    float(centdist),
                    f"π-π {centdist}Å · {pitype} · ∠{angle}°",
                )
            )

        for row in report.pication_info:
            _, restype, reschain, _, resnr_l, restype_l, reschain_l, dist, offset, protcharged, group, _, ligcoords, protcoords = row
            resnr = row[0]
            interactions.append(
                _mk_ix(
                    "pi_cation",
                    reschain,
                    resnr,
                    restype,
                    "Charge",
                    protcoords,
                    reschain_l,
                    resnr_l,
                    restype_l,
                    group or "Ring",
                    ligcoords,
                    float(dist),
                    f"π-阳离子 {dist}Å",
                )
            )

        for row in report.waterbridge_info:
            _, restype, reschain, resnr_l, restype_l, reschain_l, dist_aw, dist_dw, d_angle, w_angle, protisdon, _, dtype, _, atype, _, ligcoords, protcoords, _ = row
            resnr = row[0]
            interactions.append(
                _mk_ix(
                    "water_bridge",
                    reschain,
                    resnr,
                    restype,
                    dtype or "W",
                    protcoords,
                    reschain_l,
                    resnr_l,
                    restype_l,
                    atype or "W",
                    ligcoords,
                    float(dist_dw),
                    f"水桥 D-W {dist_dw}Å",
                )
            )

        iface_a = {(ix["chain_a"], ix["resnum_a"]) for ix in interactions}
        iface_b = {(ix["chain_b"], ix["resnum_b"]) for ix in interactions}
        summary = _summarize(interactions, len(iface_a), len(iface_b))
        interactions.sort(key=lambda x: (x["type"], x["distance_angstrom"]))
        return {"interactions": interactions, "summary": summary, "receptor_chain": receptor_chain, "ligand_chain": ligand_chain}
    finally:
        try:
            pdb_path.unlink(missing_ok=True)
        except OSError:
            pass


def find_model_cif(job_dir: Path) -> Path | None:
    cif_files = sorted(job_dir.rglob("*_model_0.cif"))
    if cif_files:
        return cif_files[0]
    pred = job_dir / "pred.cif"
    return pred if pred.is_file() else None


def analyze_interactions_from_cif(
    cif_path: Path,
    chain_a: str,
    chain_b: str,
    *,
    receptor_chain: str | None = None,
    ligand_chain: str | None = None,
) -> dict:
    """Analyze PPI with PLIP; default receptor=chain_b if H/A pair else first chain."""
    rec = receptor_chain or chain_b
    lig = ligand_chain or chain_a
    if rec == lig:
        rec, lig = chain_a, chain_b
    return analyze_plip_ppi(cif_path, rec, lig)
