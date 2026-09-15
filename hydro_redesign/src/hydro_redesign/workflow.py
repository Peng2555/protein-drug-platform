"""疏水改造第一版：Boltz2 折抗体 → 斑 → 枚举打分。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from antibody_workflows import (
    copy_structure_input,
    export_structure_files,
    fold_antibody,
    write_csv,
    write_fasta,
)
from hydro_redesign.constants import SURFACE_RSA
from hydro_redesign.enumerate import enumerate_mutations
from hydro_redesign.patches import cluster_patches
from hydro_redesign.sequences import (
    ALL_MUTANT_FASTA,
    TOP20_MUTANT_FASTA,
    build_mutant_sequences_fasta,
    parse_fasta,
    select_top20_rows,
)

def _annotate_regions(sequences: dict[str, str]) -> dict[tuple[str, int], str]:
    try:
        from affinity_redesign.common.cdr import annotate_antibody_chain, region_for_index
    except ImportError:
        return {(cid, i + 1): "FR" for cid, seq in sequences.items() for i in range(len(seq))}

    out: dict[tuple[str, int], str] = {}
    for cid, seq in sequences.items():
        ab = annotate_antibody_chain(seq)
        for i in range(len(seq)):
            if ab:
                out[(cid, i + 1)] = region_for_index(ab, i)
            else:
                out[(cid, i + 1)] = "FR"
    return out

def run_workflow(
    work_dir: Path,
    *,
    fasta_text: str,
    structure_path: Path | None = None,
    allow_cdr: bool = False,
    allow_charged: bool = False,
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
        status = {
            "stage": name,
            "status": "running",
        }
        (work_dir / "workflow_status.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
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
    residues, patches = cluster_patches(src_struct, rsa_cut=SURFACE_RSA)
    regions = _annotate_regions(seqs)
    for row in residues:
        row["region"] = regions.get((row["chain"], int(row["position"])), "FR")

    write_csv(
        patches_dir / "residue_sasa.csv",
        residues,
        ["chain", "position", "aa", "region", "sasa", "rsa", "hydrophobic", "surface", "hydro_sasa", "patch_id"],
    )
    (patches_dir / "patches.json").write_text(
        json.dumps({"patches": patches, "rsa_cut": SURFACE_RSA}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_csv(
        exports / "patches.csv",
        [
            {
                **p,
                "residues": ";".join(p["residues"]) if isinstance(p.get("residues"), list) else p.get("residues", ""),
            }
            for p in patches
        ],
        ["patch_id", "n_residues", "score", "residues"],
    )

    stage("enumerate")
    mutations, skipped = enumerate_mutations(
        residues,
        seqs,
        regions,
        allow_cdr=allow_cdr,
        allow_charged=allow_charged,
    )
    mut_cols = [
        "rank",
        "label",
        "chain",
        "position",
        "wt",
        "mut",
        "region",
        "patch_id",
        "rsa",
        "sasa",
        "hydro_sasa",
        "hydro_delta",
        "delta_patch",
        "cdr_risk",
        "wetlab",
    ]
    write_csv(exports / "mutations.csv", mutations, mut_cols)
    wetlab = [r for r in mutations if r.get("wetlab")]
    write_csv(exports / "wetlab.csv", wetlab, mut_cols)
    (exports / ALL_MUTANT_FASTA).write_text(
        build_mutant_sequences_fasta(seqs, mutations),
        encoding="utf-8",
    )
    (exports / TOP20_MUTANT_FASTA).write_text(
        build_mutant_sequences_fasta(seqs, select_top20_rows(mutations, wetlab)),
        encoding="utf-8",
    )

    mutable_sites = {(r["chain"], int(r["position"])) for r in mutations}
    skipped_cdr = sum(1 for r in skipped if r.get("skip_reason") == "cdr_frozen")
    summary = {
        "n_residues": len(residues),
        "n_patches": len(patches),
        "n_surface_hydro": sum(1 for r in residues if r.get("hydrophobic") and r.get("surface") and r.get("patch_id")),
        "n_mutable_sites": len(mutable_sites),
        "n_mutations": len(mutations),
        "n_wetlab": len(wetlab),
        "n_skipped_cdr": skipped_cdr,
        "allow_cdr": allow_cdr,
        "allow_charged": allow_charged,
        "structure": str(src_struct),
        "pred_cif": str(cif_path) if cif_path.is_file() else None,
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
        "mutations": mutations[:200],
        "wetlab": wetlab,
        "n_skipped": len(skipped),
        "pred_cif": str(cif_path) if cif_path.is_file() else None,
    }
