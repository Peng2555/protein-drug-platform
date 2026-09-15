"""CIC 第一版：折抗体或上传结构 → 正电/负电/疏水斑。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from boltzfold_shared.antibody.cdr import annotate_antibody_chain, region_for_index
from boltzfold_shared.antibody.folding import fold_antibody
from boltzfold_shared.io import (
    copy_structure_input,
    export_structure_files,
    parse_fasta,
    write_csv,
    write_fasta,
)
from cic_profile.constants import DEFAULT_PH, PATCH_CUTOFF, SURFACE_RSA_CHARGE, SURFACE_RSA_HYDRO
from cic_profile.patches import cluster_cic_patches


def _annotate_regions(sequences: dict[str, str]) -> dict[tuple[str, int], str]:
    out: dict[tuple[str, int], str] = {}
    for cid, seq in sequences.items():
        ab = annotate_antibody_chain(seq)
        for i in range(len(seq)):
            out[(cid, i + 1)] = region_for_index(ab, i) if ab else "FR"
    return out

def run_workflow(
    work_dir: Path,
    *,
    fasta_text: str,
    structure_path: Path | None = None,
    ph: float = DEFAULT_PH,
    on_stage: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    work_dir = work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    inp = work_dir / "input"
    fold_root = work_dir / "fold"
    patches_dir = work_dir / "patches"
    exports = work_dir / "exports"
    for d in (inp, fold_root, patches_dir, exports):
        d.mkdir(parents=True, exist_ok=True)

    def stage(name: str) -> None:
        (work_dir / "workflow_status.json").write_text(
            json.dumps({"stage": name, "status": "running"}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if on_stage:
            on_stage(name)

    seqs = parse_fasta(fasta_text)
    if not seqs:
        raise ValueError("FASTA 无效")
    if "H" not in seqs and len(seqs) == 1:
        cid, seq = next(iter(seqs.items()))
        seqs = {"H": seq}
    unknown = [k for k in seqs if k not in {"H", "L"}]
    if unknown:
        raise ValueError(f"第一版只接受抗体链 H / L，收到: {', '.join(unknown)}")
    write_fasta(seqs, inp / "sequences.fasta")

    stage("fold")
    src_struct: Path
    if structure_path and structure_path.is_file():
        src_struct = copy_structure_input(structure_path, fold_root)
    else:
        src_struct = fold_antibody(inp / "sequences.fasta", fold_root, "WT")

    cif_path = exports / "pred.cif"
    pdb_path = exports / "pred.pdb"
    export_structure_files(src_struct, cif_path, pdb_path)

    stage("patches")
    residues, patches = cluster_cic_patches(src_struct, ph=ph, patch_cut=PATCH_CUTOFF)
    regions = _annotate_regions(seqs)
    for row in residues:
        row["region"] = regions.get((row["chain"], int(row["position"])), "FR")
        row["cdr"] = str(row["region"]).startswith("CDR")

    residue_cols = [
        "chain",
        "position",
        "aa",
        "region",
        "sasa",
        "rsa",
        "charge",
        "charge_sasa",
        "hydro_sasa",
        "hydrophobic",
        "surface_charge",
        "surface_hydro",
        "patch_id",
        "patch_kind",
        "hydro_patch_id",
        "charge_patch_id",
        "cdr",
    ]
    write_csv(patches_dir / "residue_features.csv", residues, residue_cols)
    write_csv(exports / "residue_features.csv", residues, residue_cols)
    patch_rows = [
        {
            **p,
            "residues": ";".join(p["residues"]) if isinstance(p.get("residues"), list) else p.get("residues", ""),
        }
        for p in patches
    ]
    write_csv(exports / "patches.csv", patch_rows, ["patch_id", "kind", "n_residues", "score", "residues"])
    (patches_dir / "patches.json").write_text(
        json.dumps(
            {
                "patches": patches,
                "ph": ph,
                "rsa_charge": SURFACE_RSA_CHARGE,
                "rsa_hydro": SURFACE_RSA_HYDRO,
                "patch_cut": PATCH_CUTOFF,
                "method": "formal_HH_charge_x_sasa + hydro_sasa, Cβ 8Å; v1 no APBS",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    n_pos = sum(1 for p in patches if p["kind"] == "positive")
    n_neg = sum(1 for p in patches if p["kind"] == "negative")
    n_hyd = sum(1 for p in patches if p["kind"] == "hydrophobic")
    summary = {
        "ph": ph,
        "n_residues": len(residues),
        "n_patches": len(patches),
        "n_positive_patches": n_pos,
        "n_negative_patches": n_neg,
        "n_hydrophobic_patches": n_hyd,
        "structure": str(src_struct),
        "pred_cif": str(cif_path) if cif_path.is_file() else None,
        "method": "HH protonation + SASA patches (no APBS)",
    }
    (exports / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (work_dir / "workflow_status.json").write_text(
        json.dumps({"stage": "done", "status": "ok", "summary": summary}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if on_stage:
        on_stage("done")
    return {
        "summary": summary,
        "patches": patches,
        "pred_cif": str(cif_path) if cif_path.is_file() else None,
    }
