#!/usr/bin/env python3
"""Model-only interface quality scores (pDockQ / pDockQ2) from Boltz2 outputs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import gemmi
import numpy as np

# Bryant et al., Nature Communications 2022 (author correction)
_PDOCKQ = (0.724, 152.611, 0.052, 0.018)
# Zhu et al., Bioinformatics 2023
_PDOCKQ2 = (1.31, 84.733, 0.075, 0.005)
_D0 = 10.0
_CONTACT_A = 8.0


def _sigmoid(x: float, params: tuple[float, float, float, float]) -> float:
    l_val, x0, k, b = params
    return l_val / (1.0 + math.exp(-k * (x - x0))) + b


def _plddt_scale(values: np.ndarray) -> np.ndarray:
    """AlphaFold-style pLDDT is 0–100; Boltz stores 0–1 in npz."""
    arr = np.asarray(values, dtype=float).ravel()
    if arr.size and np.nanmax(arr) <= 1.5:
        arr = arr * 100.0
    return arr


def _representative_coords(residue: gemmi.Residue) -> tuple[float, float, float] | None:
    for atom_name in ("CB", "CA"):
        atom = residue.find_atom(atom_name, "\0")
        if atom:
            p = atom.pos
            return (p.x, p.y, p.z)
    return None


@dataclass
class InterfaceScore:
    chain_a: str
    chain_b: str
    contact_pairs: int
    avg_interface_plddt: float
    avg_interface_pae: float | None
    pdockq: float
    pdockq2: float


@dataclass
class PDockQResult:
    pdockq: float | None
    pdockq2: float | None
    mpdockq: float | None
    num_chains: int
    interfaces: list[InterfaceScore]
    error: str | None = None


def _chain_residue_indices(structure: gemmi.Structure) -> tuple[list[str], dict[str, list[int]]]:
    chain_ids: list[str] = []
    residue_index: dict[str, list[int]] = {}
    offset = 0
    model = structure[0]
    for chain in model:
        cid = chain.name
        chain_ids.append(cid)
        n = 0
        for res in chain:
            if res.find_atom("CA", "\0"):
                n += 1
        residue_index[cid] = list(range(offset, offset + n))
        offset += n
    return chain_ids, residue_index


def _interface_contacts(
    structure: gemmi.Structure,
    chain_a: str,
    chain_b: str,
    plddt: np.ndarray,
    residue_index: dict[str, list[int]],
    contact_a: float = _CONTACT_A,
) -> tuple[int, float, list[tuple[int, int]]]:
    model = structure[0]
    chain_map = {ch.name: ch for ch in model}

    def _coords_and_global_idx(chain_id: str) -> tuple[np.ndarray, list[int]]:
        coords: list[tuple[float, float, float]] = []
        gidx: list[int] = []
        idxs = residue_index.get(chain_id, [])
        chain = chain_map[chain_id]
        for local_i, res in enumerate(chain):
            if local_i >= len(idxs):
                break
            pt = _representative_coords(res)
            if pt is None:
                continue
            coords.append(pt)
            gidx.append(idxs[local_i])
        return np.array(coords, dtype=float), gidx

    c1, idx1 = _coords_and_global_idx(chain_a)
    c2, idx2 = _coords_and_global_idx(chain_b)
    if c1.size == 0 or c2.size == 0:
        return 0, float("nan"), []

    diff = c1[:, None, :] - c2[None, :, :]
    dist2 = np.sum(diff * diff, axis=2)
    pairs_ij = np.argwhere(dist2 <= contact_a * contact_a)
    if pairs_ij.size == 0:
        return 0, float("nan"), []

    contact_res: set[int] = set()
    pair_global: list[tuple[int, int]] = []
    for i, j in pairs_ij:
        gi, gj = idx1[int(i)], idx2[int(j)]
        contact_res.add(gi)
        contact_res.add(gj)
        pair_global.append((gi, gj))

    avg_if_plddt = float(np.mean(plddt[list(contact_res)]))
    return int(pairs_ij.shape[0]), avg_if_plddt, pair_global


def _mean_ptm(pae: np.ndarray, pairs: list[tuple[int, int]], reverse: bool) -> float:
    vals: list[float] = []
    for i, j in pairs:
        a, b = (j, i) if reverse else (i, j)
        if a >= pae.shape[0] or b >= pae.shape[1]:
            continue
        pae_val = float(pae[a, b])
        vals.append(1.0 / (1.0 + (pae_val / _D0) ** 2))
    return float(np.mean(vals)) if vals else float("nan")


def _interface_pdockq2(avg_if_plddt: float, pae: np.ndarray | None, pairs: list[tuple[int, int]]) -> float:
    if not pairs or pae is None or math.isnan(avg_if_plddt):
        return 0.0
    m_ab = _mean_ptm(pae, pairs, reverse=False)
    m_ba = _mean_ptm(pae, pairs, reverse=True)
    s_ab = _sigmoid(avg_if_plddt * m_ab, _PDOCKQ2) if not math.isnan(m_ab) else float("nan")
    s_ba = _sigmoid(avg_if_plddt * m_ba, _PDOCKQ2) if not math.isnan(m_ba) else float("nan")
    if math.isnan(s_ab) and math.isnan(s_ba):
        return 0.0
    if math.isnan(s_ba) or (not math.isnan(s_ab) and s_ab >= s_ba):
        return s_ab
    return s_ba


def _element_for_atom(atom_name: str, comp_id: str) -> gemmi.Element:
    name = atom_name.strip()
    if len(name) == 1:
        return gemmi.Element(name)
    if name.startswith(("C", "N", "O", "S", "H", "P")):
        return gemmi.Element(name[0])
    return gemmi.Element(comp_id[0] if comp_id else "C")


def _sanitize_mmcif_path(cif_path: Path) -> Path:
    """Rewrite non-ASCII ``data_`` block names so gemmi can parse ESMFold exports.

    ESMFold may embed the job directory name (often Chinese) into ``data_<name>``,
    which gemmi rejects with ``expected block header (data_)``.
    """
    import re

    text = cif_path.read_text(encoding="utf-8", errors="replace")
    sanitized, n = re.subn(r"^data_[^\s#]+", "data_pred", text, count=1, flags=re.M)
    if n == 0 or sanitized == text:
        return cif_path
    out = cif_path.with_name(f"{cif_path.stem}__gemmi_safe.cif")
    if not out.is_file() or out.read_text(encoding="utf-8", errors="replace") != sanitized:
        out.write_text(sanitized, encoding="utf-8")
    return out


def _structure_from_atom_site_cif(cif_path: Path) -> gemmi.Structure:
    """Build a gemmi Structure from mmCIF atom_site (ESMFold2 exports)."""
    path = _sanitize_mmcif_path(cif_path)
    doc = gemmi.cif.read(str(path))
    if not doc:
        raise ValueError(f"empty mmCIF: {cif_path}")
    block = doc[0]
    st = gemmi.Structure()
    st.name = block.name
    st.add_model(gemmi.Model("1"))
    model = st[0]
    chains: dict[str, gemmi.Chain] = {}
    cat = block.find(
        "_atom_site.",
        [
            "group_PDB",
            "label_atom_id",
            "label_comp_id",
            "label_asym_id",
            "label_seq_id",
            "Cartn_x",
            "Cartn_y",
            "Cartn_z",
            "auth_asym_id",
        ],
    )
    for row in cat:
        if row[0] != "ATOM":
            continue
        atom_name, comp_id, label_asym, seq_id = row[1], row[2], row[3], row[4]
        x, y, z = float(row[5]), float(row[6]), float(row[7])
        chain_id = (row[8] or label_asym or "A").strip() or "A"
        chain = chains.get(chain_id)
        if chain is None:
            model.add_chain(gemmi.Chain(chain_id))
            chain = model[chain_id]
            chains[chain_id] = chain
        seq = int(seq_id)
        residue = None
        for res in chain:
            if res.seqid.num == seq and res.name == comp_id:
                residue = res
                break
        if residue is None:
            residue = gemmi.Residue()
            residue.name = comp_id
            residue.seqid = gemmi.SeqId(str(seq))
            residue.label_seq = seq
            residue.subchain = chain_id
            chain.add_residue(residue)
        atom = gemmi.Atom()
        atom.name = atom_name
        atom.element = _element_for_atom(atom_name, comp_id)
        atom.pos = gemmi.Position(x, y, z)
        residue.add_atom(atom)
    if not chains:
        raise ValueError(f"no ATOM records in {cif_path}")
    return st


def _load_structure(cif_path: Path) -> gemmi.Structure:
    path = _sanitize_mmcif_path(cif_path)
    try:
        st = gemmi.read_structure(str(path))
        if len(st) > 0 and len(st[0]) > 0:
            st.remove_ligands_and_waters()
            return st
    except Exception:
        pass
    return _structure_from_atom_site_cif(path)


def compute_pdockq_from_boltz_dir(out_dir: Path, *, contact_a: float = _CONTACT_A) -> PDockQResult:
    """Score all chain-pair interfaces under a Boltz2 job output directory."""
    pred_dir = out_dir
    cif_files = sorted(out_dir.rglob("*_model_0.cif"))
    if not cif_files:
        pred = out_dir / "pred.cif"
        if pred.is_file():
            cif_files = [pred]
    if not cif_files:
        return PDockQResult(None, None, None, 0, [], error="no model CIF found")

    cif_path = cif_files[0]
    pred_parent = cif_path.parent
    stem = cif_path.name.replace(".cif", "")
    plddt_path = pred_parent / f"plddt_{stem}.npz"
    if not plddt_path.is_file():
        plddt_path = out_dir / "plddt_model_0.npz"
    pae_path = pred_parent / f"pae_{stem}.npz"

    if not plddt_path.is_file():
        return PDockQResult(None, None, None, 0, [], error=f"missing pLDDT: {plddt_path}")

    structure = _load_structure(cif_path)
    plddt = _plddt_scale(np.load(plddt_path)["plddt"])
    pae = np.load(pae_path)["pae"].astype(float) if pae_path.is_file() else None

    chain_ids, residue_index = _chain_residue_indices(structure)
    if len(chain_ids) < 2:
        return PDockQResult(None, None, None, len(chain_ids), [], error="single chain; pDockQ needs ≥2 chains")

    interfaces: list[InterfaceScore] = []
    total_contacts = 0
    weighted_plddt_sum = 0.0

    for i, chain_a in enumerate(chain_ids):
        for chain_b in chain_ids[i + 1 :]:
            n_contacts, avg_if_plddt, pairs = _interface_contacts(
                structure, chain_a, chain_b, plddt, residue_index, contact_a=contact_a
            )
            if n_contacts <= 0 or math.isnan(avg_if_plddt):
                pdockq = 0.0
                pdockq2 = 0.0
                avg_pae = None
            else:
                pdockq = _sigmoid(avg_if_plddt * math.log10(n_contacts), _PDOCKQ)
                pdockq2 = _interface_pdockq2(avg_if_plddt, pae, pairs)
                avg_pae = None
                if pae is not None and pairs:
                    pae_vals = []
                    for gi, gj in pairs:
                        if gi < pae.shape[0] and gj < pae.shape[1]:
                            pae_vals.append(float(pae[gi, gj]))
                            pae_vals.append(float(pae[gj, gi]))
                    avg_pae = float(np.mean(pae_vals)) if pae_vals else None

            interfaces.append(
                InterfaceScore(
                    chain_a=chain_a,
                    chain_b=chain_b,
                    contact_pairs=n_contacts,
                    avg_interface_plddt=avg_if_plddt,
                    avg_interface_pae=avg_pae,
                    pdockq=pdockq,
                    pdockq2=pdockq2,
                )
            )
            total_contacts += n_contacts
            if n_contacts > 0 and not math.isnan(avg_if_plddt):
                weighted_plddt_sum += avg_if_plddt

    if not interfaces:
        return PDockQResult(None, None, None, len(chain_ids), [], error="no interfaces evaluated")

    active = [i for i in interfaces if i.contact_pairs > 0]
    if not active:
        return PDockQResult(None, None, None, len(chain_ids), interfaces, error="no inter-chain contacts")

    best_pdockq = max(i.pdockq for i in active)
    best_pdockq2 = max(i.pdockq2 for i in active)
    mpdockq = None
    if len(chain_ids) > 2 and total_contacts > 0:
        avg_global = weighted_plddt_sum / max(1, sum(1 for i in interfaces if i.contact_pairs > 0))
        mpdockq = _sigmoid(avg_global * math.log10(total_contacts + 1), (0.728, 309.375, 0.098, 0.262))

    global_pdockq = mpdockq if mpdockq is not None else best_pdockq
    global_pdockq2 = best_pdockq2

    return PDockQResult(
        pdockq=global_pdockq,
        pdockq2=global_pdockq2,
        mpdockq=mpdockq,
        num_chains=len(chain_ids),
        interfaces=interfaces,
    )


def find_boltz_prediction_dir(out_dir: Path) -> Path:
    """Return directory containing confidence/plddt npz (for callers/tests)."""
    for conf in sorted(out_dir.rglob("confidence_*_model_0.json")):
        return conf.parent
    raise FileNotFoundError(f"No Boltz prediction dir under {out_dir}")


def _plddt_from_structure(structure: gemmi.Structure) -> np.ndarray:
    vals: list[float] = []
    for chain in structure[0]:
        for res in chain:
            atom = res.find_atom("CA", "\0")
            if atom:
                vals.append(float(atom.b_iso))
    if not vals:
        return np.array([], dtype=float)
    return _plddt_scale(np.array(vals, dtype=float))


def _resolve_cif_and_plddt(out_dir: Path) -> tuple[Path, np.ndarray, np.ndarray | None]:
    cif_files = sorted(out_dir.rglob("*_model_0.cif"))
    if not cif_files:
        pred = out_dir / "pred.cif"
        if pred.is_file():
            cif_files = [pred]
    if not cif_files:
        raise FileNotFoundError("no model CIF found")
    cif_path = cif_files[0]
    pred_parent = cif_path.parent
    stem = cif_path.name.replace(".cif", "")
    plddt_path = pred_parent / f"plddt_{stem}.npz"
    if not plddt_path.is_file():
        plddt_path = out_dir / "plddt_model_0.npz"
    pae_path = pred_parent / f"pae_{stem}.npz"

    structure = _load_structure(cif_path)
    if plddt_path.is_file():
        plddt = _plddt_scale(np.load(plddt_path)["plddt"])
    else:
        plddt = _plddt_from_structure(structure)
    pae = np.load(pae_path)["pae"].astype(float) if pae_path.is_file() else None
    return cif_path, plddt, pae


def _interface_contacts_detailed(
    structure: gemmi.Structure,
    chain_a: str,
    chain_b: str,
    plddt: np.ndarray,
    residue_index: dict[str, list[int]],
    contact_a: float = _CONTACT_A,
) -> tuple[int, float, list[tuple[int, int]], list[tuple[str, int, str]], list[tuple[str, int, str]]]:
    """Return contacts, avg pLDDT, global pairs, unique interface residues on each chain."""
    model = structure[0]
    chain_map = {ch.name: ch for ch in model}

    def _coords_resinfo(chain_id: str) -> tuple[np.ndarray, list[int], list[tuple[int, str]]]:
        coords: list[tuple[float, float, float]] = []
        gidx: list[int] = []
        resinfo: list[tuple[int, str]] = []
        idxs = residue_index.get(chain_id, [])
        chain = chain_map[chain_id]
        for local_i, res in enumerate(chain):
            if local_i >= len(idxs):
                break
            pt = _representative_coords(res)
            if pt is None:
                continue
            coords.append(pt)
            gidx.append(idxs[local_i])
            resinfo.append((res.seqid.num, res.name))
        return np.array(coords, dtype=float), gidx, resinfo

    c1, idx1, info1 = _coords_resinfo(chain_a)
    c2, idx2, info2 = _coords_resinfo(chain_b)
    if c1.size == 0 or c2.size == 0:
        return 0, float("nan"), [], [], []

    diff = c1[:, None, :] - c2[None, :, :]
    dist2 = np.sum(diff * diff, axis=2)
    pairs_ij = np.argwhere(dist2 <= contact_a * contact_a)
    if pairs_ij.size == 0:
        return 0, float("nan"), [], [], []

    contact_res: set[int] = set()
    pair_global: list[tuple[int, int]] = []
    res_a: dict[tuple[str, int], str] = {}
    res_b: dict[tuple[str, int], str] = {}
    for i, j in pairs_ij:
        gi, gj = idx1[int(i)], idx2[int(j)]
        contact_res.add(gi)
        contact_res.add(gj)
        pair_global.append((gi, gj))
        seq_a, name_a = info1[int(i)]
        seq_b, name_b = info2[int(j)]
        res_a[(chain_a, seq_a)] = name_a
        res_b[(chain_b, seq_b)] = name_b

    avg_if_plddt = float(np.mean(plddt[list(contact_res)]))
    residues_a = [(chain_a, seq, name) for (_, seq), name in sorted(res_a.items())]
    residues_b = [(chain_b, seq, name) for (_, seq), name in sorted(res_b.items())]
    return int(pairs_ij.shape[0]), avg_if_plddt, pair_global, residues_a, residues_b


def analyze_interfaces_from_dir(out_dir: Path, *, contact_a: float = _CONTACT_A) -> dict:
    """Full interface analysis for web visualization (pDockQ 8Å contact definition)."""
    try:
        cif_path, plddt, pae = _resolve_cif_and_plddt(out_dir)
    except FileNotFoundError as exc:
        return {"error": str(exc), "chains": [], "interfaces": [], "primary_interface": None}

    structure = _load_structure(cif_path)
    chain_ids, residue_index = _chain_residue_indices(structure)
    if len(chain_ids) < 2:
        return {
            "error": "single chain; interface analysis needs ≥2 chains",
            "chains": [{"chain_id": c, "length": len(residue_index.get(c, []))} for c in chain_ids],
            "interfaces": [],
            "primary_interface": None,
            "method": _method_note(),
        }

    interfaces: list[dict] = []
    for i, chain_a in enumerate(chain_ids):
        for chain_b in chain_ids[i + 1 :]:
            n_contacts, avg_if_plddt, pairs, residues_a, residues_b = _interface_contacts_detailed(
                structure, chain_a, chain_b, plddt, residue_index, contact_a=contact_a
            )
            if n_contacts <= 0 or math.isnan(avg_if_plddt):
                pdockq = 0.0
                pdockq2 = 0.0
                avg_pae = None
            else:
                pdockq = _sigmoid(avg_if_plddt * math.log10(n_contacts), _PDOCKQ)
                pdockq2 = _interface_pdockq2(avg_if_plddt, pae, pairs)
                avg_pae = None
                if pae is not None and pairs:
                    pae_vals = []
                    for gi, gj in pairs:
                        if gi < pae.shape[0] and gj < pae.shape[1]:
                            pae_vals.append(float(pae[gi, gj]))
                            pae_vals.append(float(pae[gj, gi]))
                    avg_pae = float(np.mean(pae_vals)) if pae_vals else None

            interfaces.append(
                {
                    "chain_a": chain_a,
                    "chain_b": chain_b,
                    "contact_pairs": n_contacts,
                    "avg_interface_plddt": None if math.isnan(avg_if_plddt) else avg_if_plddt,
                    "avg_interface_pae": avg_pae,
                    "pdockq": pdockq,
                    "pdockq2": pdockq2,
                    "residues_a": [{"chain_id": c, "seq_num": s, "resname": n} for c, s, n in residues_a],
                    "residues_b": [{"chain_id": c, "seq_num": s, "resname": n} for c, s, n in residues_b],
                }
            )

    primary = None
    active = [iface for iface in interfaces if iface["contact_pairs"] > 0]
    if active:
        primary = max(active, key=lambda x: x["pdockq"])

    chains = [
        {
            "chain_id": cid,
            "length": len(residue_index.get(cid, [])),
        }
        for cid in chain_ids
    ]

    return {
        "error": None,
        "contact_cutoff_angstrom": contact_a,
        "method": _method_note(),
        "reference_tools": _reference_tools(),
        "chains": chains,
        "interfaces": interfaces,
        "primary_interface": primary,
    }


def _method_note() -> str:
    return (
        "Inter-chain contacts at ≤8 Å (CB/CA representative atoms), "
        "pDockQ scoring (Bryant et al., Nat Commun 2022)"
    )


def _reference_tools() -> list[dict[str, str]]:
    return [
        {
            "name": "pDockQ / pDockQ2",
            "role": "Model-quality interface score (no reference structure)",
            "url": "https://github.com/patrickbryant/PDockQ",
        },
        {
            "name": "PRODIGY",
            "role": "Contact-based binding affinity ΔG / Kd prediction",
            "url": "https://wenmr.science.uu.nl/prodigy/",
        },
        {
            "name": "PLIP",
            "role": "Non-covalent interaction profiling (H-bonds, salt bridges, …)",
            "url": "https://plip-tool.biotec.tu-dresden.de/",
        },
    ]
