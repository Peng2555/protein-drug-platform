"""Protein–protein interface analysis for job detail visualization."""

from __future__ import annotations

import sys
from pathlib import Path

from app.cdr_annotation import annotate_fasta
from app.config import settings
from app.models import Batch, Job

ROOT = Path(__file__).resolve().parents[1]
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


def _receptor_ligand_chains(primary: dict, roles: dict[str, dict]) -> tuple[str, str]:
    """Pick PLIP receptor (target) and ligand (binder) chains."""
    ca, cb = primary["chain_a"], primary["chain_b"]
    ra, rb = roles.get(ca, {}), roles.get(cb, {})

    def _is_binder(r: dict) -> bool:
        return r.get("role") in {"heavy", "antibody"}

    def _is_target(r: dict) -> bool:
        return r.get("role") in {"target", "chain"} and not r.get("is_antibody")

    if _is_target(ra) and _is_binder(rb):
        return ca, cb
    if _is_target(rb) and _is_binder(ra):
        return cb, ca
    # VHH default: A=target receptor, H=binder ligand
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

    primary = raw.get("primary_interface")
    if primary:
        primary = {
            **primary,
            "label_a": roles.get(primary["chain_a"], {}).get("label", primary["chain_a"]),
            "label_b": roles.get(primary["chain_b"], {}).get("label", primary["chain_b"]),
        }
        cif = find_model_cif(job_dir)
        if cif:
            rec, lig = _receptor_ligand_chains(primary, roles)
            ix_data = analyze_interactions_from_cif(
                cif, primary["chain_a"], primary["chain_b"],
                receptor_chain=rec, ligand_chain=lig,
            )
            primary["interactions"] = ix_data.get("interactions", [])
            primary["interaction_summary"] = ix_data.get("summary")

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
