"""疏水改造：Boltz2 折抗体 → 疏水斑 → 单点枚举 → 同斑组合复折筛选。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from boltzfold_shared.antibody.cdr import annotate_antibody_chain, region_for_index
from boltzfold_shared.antibody.folding import fold_antibody
from boltzfold_shared.io import (
    copy_structure_input,
    export_structure_files,
    write_csv,
    write_fasta,
)
from hydro_redesign.constants import (
    HYDROPHOBICITY_SCALE,
    PATCH_LINK_RADIUS,
    SAP_PATCH_CUTOFF,
    SAP_RADIUS,
    SURFACE_RSA,
)
from hydro_redesign.enumerate import enumerate_mutations
from hydro_redesign.patches import cluster_patches
from hydro_redesign.sap import discover_ensemble_structures
from hydro_redesign.screen import (
    SCREENED_FASTA,
    accept_verified,
    apply_combo,
    build_patch_combos,
    chain_plddt_mean,
    combo_job_id,
    combo_label,
    fold_gate,
    introduces_sequon,
    novel_patches,
    patch_member_positions,
    patch_sap,
    plddt_drop,
    render_screened_fasta,
    residue_plddt,
    sap_gate,
    select_screened_sites,
)
from hydro_redesign.sequences import (
    ALL_MUTANT_FASTA,
    TOP20_MUTANT_FASTA,
    build_mutant_sequences_fasta,
    parse_fasta,
    select_top20_rows,
)

def _annotate_chains(
    sequences: dict[str, str],
) -> tuple[dict[tuple[str, int], str], dict[tuple[str, int], str]]:
    regions: dict[tuple[str, int], str] = {}
    kabats: dict[tuple[str, int], str] = {}
    for cid, seq in sequences.items():
        ab = annotate_antibody_chain(seq)
        labels = list((ab or {}).get("kabat_labels") or []) or [str(i + 1) for i in range(len(seq))]
        for i in range(len(seq)):
            regions[(cid, i + 1)] = region_for_index(ab, i) if ab else "FR"
            kabats[(cid, i + 1)] = labels[i] if i < len(labels) else str(i + 1)
    return regions, kabats


def _relabel_patches(patches: list[dict[str, Any]], kabats: dict[tuple[str, int], str]) -> None:
    import re

    pattern = re.compile(r"^([^:]+):([A-Z])(\d+)$")
    for patch in patches:
        raw = patch.get("residues") or []
        if not isinstance(raw, list):
            continue
        labels = []
        for item in raw:
            text = str(item)
            match = pattern.match(text)
            if not match:
                labels.append(text)
                continue
            chain, aa, pos_s = match.group(1), match.group(2), match.group(3)
            kabat = kabats.get((chain, int(pos_s)), pos_s)
            labels.append(f"{chain}:{aa}{kabat}")
        patch["residues"] = labels

def _verify_patch_combos(
    seqs: dict[str, str],
    mutations: list[dict[str, Any]],
    wildtype_residues: list[dict[str, Any]],
    wildtype_structure: Path,
    fold_root: Path,
) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    """同一斑的 Q 组合复折后，只留下折叠、疏水斑和结合面都通过的序列。"""
    wildtype_positions = {
        (str(row["chain"]), int(row["position"]))
        for row in wildtype_residues
        if row.get("patch_id")
    }
    wildtype_plddt = residue_plddt(wildtype_structure) if wildtype_structure.is_file() else {}
    reports: list[dict[str, Any]] = []
    passed: list[tuple[str, str, float]] = []

    for sites in build_patch_combos(select_screened_sites(mutations)):
        label = combo_label(sites)
        patch_id = str(sites[0].get("patch_id") or "")
        try:
            mutated = apply_combo(seqs, sites)
        except (KeyError, ValueError) as exc:
            reports.append({"label": label, "patch_id": patch_id, "error": str(exc)})
            continue
        if any(introduces_sequon(seqs.get(chain, ""), mutated.get(chain, "")) for chain in mutated):
            reports.append({"label": label, "patch_id": patch_id, "skip": "nglycosylation"})
            continue

        fasta_path = fold_root / f"{combo_job_id(label)}.fasta"
        fasta_path.parent.mkdir(parents=True, exist_ok=True)
        write_fasta(mutated, fasta_path)
        try:
            prediction = fold_antibody(fasta_path, fold_root, combo_job_id(label))
        except Exception as exc:
            reports.append({"label": label, "patch_id": patch_id, "error": str(exc)})
            continue

        mutant_residues, mutant_patches = cluster_patches(
            prediction,
            rsa_cut=SURFACE_RSA,
            patch_cut=PATCH_LINK_RADIUS,
            sap_cut=SAP_PATCH_CUTOFF,
            sap_radius=SAP_RADIUS,
        )
        mutant_plddt = residue_plddt(prediction)
        positions = patch_member_positions(wildtype_residues, patch_id)
        wildtype_sum = patch_sap(wildtype_residues, positions)
        mutant_sum = patch_sap(mutant_residues, positions)
        fresh_patches = novel_patches(mutant_patches, wildtype_positions)
        site_scores = []
        for site in sites:
            key = (str(site["chain"]), int(site["position"]))
            value = mutant_plddt.get(key)
            site_scores.append(
                {
                    "plddt": value,
                    "drop": plddt_drop(wildtype_plddt.get(key), value),
                }
            )
        report = {
            "label": label,
            "patch_id": patch_id,
            "n_sites": len(sites),
            "p1_sap_sum": round(mutant_sum, 3),
            "wt_patch_sap_sum": round(wildtype_sum, 3),
            "plddt_mean": round(chain_plddt_mean(mutant_plddt), 2),
            "fold_ok": fold_gate(site_scores, chain_plddt_mean(mutant_plddt)),
            "sap_ok": sap_gate(wildtype_sum, mutant_sum, fresh_patches),
            "binding_ok": not any(bool(site.get("cdr_risk")) for site in sites),
            "structure": str(prediction),
        }
        report["pass"] = accept_verified(report)
        reports.append(report)
        if not report["pass"]:
            continue
        changed = [chain for chain in ("H", "L") if chain in mutated and mutated[chain] != seqs.get(chain)]
        if not changed:
            changed = [str(sites[0]["chain"])]
        drop = wildtype_sum - mutant_sum
        for chain in changed:
            passed.append((label, mutated[chain], drop))

    passed.sort(key=lambda item: (-item[2], item[0]))
    return [(label, sequence) for label, sequence, _drop in passed], reports


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
    ensemble = discover_ensemble_structures(fold_root, src_struct)
    residues, patches = cluster_patches(
        src_struct,
        rsa_cut=SURFACE_RSA,
        patch_cut=PATCH_LINK_RADIUS,
        sap_cut=SAP_PATCH_CUTOFF,
        sap_radius=SAP_RADIUS,
        ensemble=ensemble,
    )
    regions, kabats = _annotate_chains(seqs)
    for row in residues:
        pos = int(row["position"])
        row["region"] = regions.get((row["chain"], pos), "FR")
        row["kabat"] = kabats.get((row["chain"], pos), str(pos))
    _relabel_patches(patches, kabats)

    write_csv(
        patches_dir / "residue_sasa.csv",
        residues,
        ["chain", "position", "kabat", "aa", "region", "sasa", "rsa", "sc_sasa", "sc_rsa", "phi", "sap", "sap_std", "hydrophobic", "surface", "hydro_sasa", "patch_id"],
    )
    (patches_dir / "patches.json").write_text(
        json.dumps(
            {
                "patches": patches,
                "rsa_cut": SURFACE_RSA,
                "sap_radius": SAP_RADIUS,
                "sap_cut": SAP_PATCH_CUTOFF,
                "patch_link_radius": PATCH_LINK_RADIUS,
                "patch_rule": "surface + phi>0 + SAP>=cut, sidechain link",
                "hydrophobicity_scale": HYDROPHOBICITY_SCALE,
                "n_structures": len(ensemble),
            },
            ensure_ascii=False,
            indent=2,
        ),
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
        ["patch_id", "n_residues", "score", "mean_sap", "residues"],
    )

    stage("enumerate")
    mutations, skipped = enumerate_mutations(
        residues,
        seqs,
        regions,
        kabats=kabats,
        allow_cdr=allow_cdr,
        allow_charged=allow_charged,
    )
    mut_cols = [
        "rank",
        "label",
        "chain",
        "position",
        "kabat",
        "wt",
        "mut",
        "sequence",
        "region",
        "patch_id",
        "rsa",
        "sasa",
        "sap",
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
    stage("verify")
    screened_entries, verify_rows = _verify_patch_combos(
        seqs,
        mutations,
        residues,
        pdb_path,
        fold_root / "combos",
    )
    (exports / SCREENED_FASTA).write_text(
        render_screened_fasta(screened_entries),
        encoding="utf-8",
    )
    (exports / "combo_screen.json").write_text(
        json.dumps(verify_rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    mutable_sites = {(r["chain"], int(r["position"])) for r in mutations}
    skipped_cdr = sum(1 for r in skipped if r.get("skip_reason") == "cdr_frozen")
    summary = {
        "n_residues": len(residues),
        "n_patches": len(patches),
        "n_surface_hydro": sum(1 for r in residues if r.get("patch_id")),
        "n_high_sap": sum(1 for r in residues if float(r.get("sap") or 0.0) >= SAP_PATCH_CUTOFF),
        "n_mutable_sites": len(mutable_sites),
        "n_mutations": len(mutations),
        "n_wetlab": len(wetlab),
        "n_screened": len({label for label, _sequence in screened_entries}),
        "n_combo_checked": len(verify_rows),
        "n_skipped_cdr": skipped_cdr,
        "allow_cdr": allow_cdr,
        "allow_charged": allow_charged,
        "hydrophobicity_scale": HYDROPHOBICITY_SCALE,
        "sap_radius": SAP_RADIUS,
        "sap_cut": SAP_PATCH_CUTOFF,
        "patch_link_radius": PATCH_LINK_RADIUS,
        "n_structures": len(ensemble),
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
        "combos": verify_rows,
        "n_skipped": len(skipped),
        "pred_cif": str(cif_path) if cif_path.is_file() else None,
    }
