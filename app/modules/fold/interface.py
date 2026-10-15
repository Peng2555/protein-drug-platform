"""Protein–protein interface analysis for job detail visualization."""

from __future__ import annotations

import sys
from pathlib import Path

from app.common.cdr_annotation import annotate_fasta
from app.common.kabat_results import annotate_job_chains
from app.core.config import settings
from app.core.models import Batch, Job

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from pdockq_runner import analyze_interfaces_from_dir  # noqa: E402
from interface_interactions import analyze_interactions_from_cif, find_model_cif  # noqa: E402


def _resolve_job_dir(job: Job) -> Path:
    if job.work_dir:
        p = Path(job.work_dir)
        if p.is_dir():
            return p
    legacy = settings.boltz2_out_root / job.id
    if legacy.is_dir():
        return legacy
    raise FileNotFoundError(f"Job output directory not found for {job.id}")


def _chain_color(chain_id: str, index: int) -> str:
    defaults = {
        "H": "#00ac9f",
        "L": "#2e5aa5",
        "A": "#ff7a00",
    }
    if chain_id in defaults:
        return defaults[chain_id]
    palette = ["#00ac9f", "#ff7a00", "#2e5aa5", "#c45a00", "#7c3aed", "#059669"]
    return palette[index % len(palette)]


def _infer_chain_roles(job: Job, chain_ids: list[str], batch: Batch | None = None) -> dict[str, dict]:
    roles: dict[str, dict] = {}
    annotated = {c["chain_id"]: c for c in annotate_fasta(job.fasta_text)}

    heavy_id = batch.heavy_chain_id if batch else None
    target_id = batch.target_chain_id if batch else None

    for i, cid in enumerate(chain_ids):
        ann = annotated.get(cid)
        label = cid
        role = "chain"
        if heavy_id and cid == heavy_id:
            label = f"重链 ({cid})"
            role = "heavy"
        elif target_id and cid == target_id:
            label = f"靶点/抗原 ({cid})"
            role = "target"
        elif ann and ann.get("is_antibody"):
            dom = ann.get("domain") or "Ab"
            label = f"抗体 {dom} 链 ({cid})"
            role = "antibody"
        elif ann:
            label = f"抗原/靶点 ({cid})"
            role = "target"
        roles[cid] = {
            "chain_id": cid,
            "label": label,
            "role": role,
            "color": _chain_color(cid, i),
            "is_antibody": bool(ann and ann.get("is_antibody")),
        }
    return roles


def _is_binder(role: dict) -> bool:
    return role.get("role") in {"heavy", "antibody"} or bool(role.get("is_antibody"))


def _binder_and_target_ids(chain_ids: list[str], roles: dict[str, dict]) -> tuple[list[str], list[str]]:
    binders = [cid for cid in chain_ids if _is_binder(roles.get(cid, {}))]
    targets = [cid for cid in chain_ids if cid not in binders]
    return binders, targets


def _is_antibody_target_pair(iface: dict, roles: dict[str, dict]) -> bool:
    a_binder = _is_binder(roles.get(iface["chain_a"], {}))
    b_binder = _is_binder(roles.get(iface["chain_b"], {}))
    return a_binder != b_binder


def _merge_antibody_target_interface(
    interfaces: list[dict],
    roles: dict[str, dict],
    binders: list[str],
    targets: list[str],
) -> dict | None:
    """Prefer antibody–antigen contacts over the heavy–light interface."""
    cross = [
        iface for iface in interfaces
        if iface.get("contact_pairs", 0) > 0 and _is_antibody_target_pair(iface, roles)
    ]
    if not cross or not binders or not targets:
        return None
    best = max(cross, key=lambda iface: (iface.get("pdockq") or 0, iface.get("contact_pairs") or 0))
    target_residues: list[dict] = []
    antibody_residues: list[dict] = []
    seen_target: set[tuple[str, int]] = set()
    seen_antibody: set[tuple[str, int]] = set()
    contacts = 0
    for iface in cross:
        contacts += int(iface.get("contact_pairs") or 0)
        for chain_key, residue_key in (("chain_a", "residues_a"), ("chain_b", "residues_b")):
            cid = iface[chain_key]
            bucket = antibody_residues if _is_binder(roles.get(cid, {})) else target_residues
            seen = seen_antibody if bucket is antibody_residues else seen_target
            for residue in iface.get(residue_key) or []:
                key = (residue.get("chain_id") or cid, int(residue.get("seq_num") or 0))
                if key in seen:
                    continue
                seen.add(key)
                bucket.append(residue)
    return {
        **best,
        "chain_a": targets[0],
        "chain_b": binders[0],
        "label_a": "靶点 " + "+".join(targets),
        "label_b": "抗体 " + "+".join(binders),
        "residues_a": target_residues,
        "residues_b": antibody_residues,
        "contact_pairs": contacts,
    }


def _kabat_lookup(job: Job) -> dict[tuple[str, int], str]:
    """抗体链的 1-based 顺序位 → Kabat 编号。靶点没有 Kabat。"""
    lookup: dict[tuple[str, int], str] = {}
    for chain in annotate_job_chains(job):
        if not chain.get("is_antibody"):
            continue
        chain_id = str(chain.get("chain_id") or "")
        for residue in chain.get("residues") or []:
            kabat = str(residue.get("kabat") or "").strip()
            try:
                index = int(residue.get("index"))
            except (TypeError, ValueError):
                continue
            if chain_id and kabat:
                lookup[(chain_id, index)] = kabat
    return lookup


def _apply_kabat_numbers(primary: dict, lookup: dict[tuple[str, int], str]) -> None:
    if not lookup:
        return
    for residue in list(primary.get("residues_a") or []) + list(primary.get("residues_b") or []):
        try:
            index = int(residue.get("seq_num"))
        except (TypeError, ValueError):
            continue
        kabat = lookup.get((str(residue.get("chain_id") or ""), index))
        if kabat:
            residue["kabat"] = kabat
    for interaction in primary.get("interactions") or []:
        for chain_key, num_key, out_key in (
            ("chain_a", "resnum_a", "kabat_a"),
            ("chain_b", "resnum_b", "kabat_b"),
        ):
            try:
                index = int(interaction.get(num_key))
            except (TypeError, ValueError):
                continue
            kabat = lookup.get((str(interaction.get(chain_key) or ""), index))
            if kabat:
                interaction[out_key] = kabat


def _receptor_ligand_chains(primary: dict, roles: dict[str, dict]) -> tuple[str, str]:
    """Pick PLIP receptor (target) and ligand (binder) chains."""
    ca, cb = primary["chain_a"], primary["chain_b"]
    ra, rb = roles.get(ca, {}), roles.get(cb, {})
    if not _is_binder(ra) and _is_binder(rb):
        return ca, cb
    if not _is_binder(rb) and _is_binder(ra):
        return cb, ca
    if ca == "A":
        return ca, cb
    if cb == "A":
        return cb, ca
    return cb, ca


def build_job_interface_analysis(job: Job, db=None) -> dict:
    job_dir = _resolve_job_dir(job)
    raw = analyze_interfaces_from_dir(job_dir)
    chain_ids = [c["chain_id"] for c in raw.get("chains", [])]

    batch = None
    if job.batch_id and db is not None:
        batch = db.get(Batch, job.batch_id)
    elif job.batch_id:
        batch = getattr(job, "batch", None)

    roles = _infer_chain_roles(job, chain_ids, batch)

    chains = []
    for c in raw.get("chains", []):
        cid = c["chain_id"]
        meta = roles.get(cid, {"label": cid, "role": "chain", "color": _chain_color(cid, 0), "is_antibody": False})
        chains.append({**c, **meta})

    interfaces = []
    for iface in raw.get("interfaces", []):
        interfaces.append(
            {
                **iface,
                "label_a": roles.get(iface["chain_a"], {}).get("label", iface["chain_a"]),
                "label_b": roles.get(iface["chain_b"], {}).get("label", iface["chain_b"]),
            }
        )

    binders, targets = _binder_and_target_ids(chain_ids, roles)
    merged = _merge_antibody_target_interface(interfaces, roles, binders, targets)
    primary = merged or raw.get("primary_interface")
    if primary and not merged:
        primary = {
            **primary,
            "label_a": roles.get(primary["chain_a"], {}).get("label", primary["chain_a"]),
            "label_b": roles.get(primary["chain_b"], {}).get("label", primary["chain_b"]),
        }
    if primary:
        cif = find_model_cif(job_dir)
        if cif:
            if binders and targets:
                rec, lig = targets, binders
            else:
                rec, lig = _receptor_ligand_chains(primary, roles)
            ix_data = analyze_interactions_from_cif(
                cif, primary["chain_a"], primary["chain_b"],
                receptor_chain=rec, ligand_chain=lig,
            )
            primary["interactions"] = ix_data.get("interactions", [])
            primary["interaction_summary"] = ix_data.get("summary")
        _apply_kabat_numbers(primary, _kabat_lookup(job))

    return {
        "job_id": job.id,
        "error": raw.get("error"),
        "contact_cutoff_angstrom": raw.get("contact_cutoff_angstrom", 8.0),
        "method": "PLIP 3.0 非共价相互作用（氢键/盐桥/疏水/π-堆积等）· pDockQ 8Å 界面",
        "reference_tools": raw.get("reference_tools", []),
        "chains": chains,
        "interfaces": interfaces,
        "primary_interface": primary,
    }
