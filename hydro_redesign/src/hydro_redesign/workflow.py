"""疏水改造第一版：Boltz2 折抗体 → 斑 → 枚举打分。"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Any, Callable

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


def _write_fasta(seqs: dict[str, str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for cid, seq in seqs.items():
        lines.append(f">{cid}")
        lines.append(seq)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in columns})


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


def _fold_antibody(fasta: Path, fold_root: Path, job_id: str = "WT") -> Path:
    from affinity_redesign.tracks.boltz2 import fold_complex

    data = fold_complex(
        fasta,
        fold_root,
        job_id,
        use_msa_server=True,
        recycling_steps=3,
        sampling_steps=200,
        diffusion_samples=3,
    )
    if data.get("status") != "ok":
        raise RuntimeError(data.get("error") or "Boltz2 折抗体失败")
    pred = data.get("pred_pdb") or data.get("pred_cif")
    if not pred or not Path(pred).is_file():
        raise RuntimeError("Boltz2 未产出 pred.pdb/cif")
    return Path(pred)


def _to_cif(src: Path, dest: Path) -> Path:
    import gemmi

    dest.parent.mkdir(parents=True, exist_ok=True)
    st = gemmi.read_structure(str(src))
    st.make_mmcif_document().write_file(str(dest))
    return dest


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
    _write_fasta(seqs, inp / "sequences.fasta")

    stage("fold")
    src_struct: Path
    if structure_path and structure_path.is_file():
        dest = fold_root / f"input{structure_path.suffix.lower() or '.pdb'}"
        shutil.copy2(structure_path, dest)
        src_struct = dest
    else:
        src_struct = _fold_antibody(inp / "sequences.fasta", fold_root, "WT")

    cif_path = exports / "pred.cif"
    pdb_path = exports / "pred.pdb"
    try:
        _to_cif(src_struct, cif_path)
    except Exception:
        shutil.copy2(src_struct, cif_path if src_struct.suffix.lower() in {".cif", ".mmcif"} else cif_path)
    if src_struct.suffix.lower() == ".pdb":
        shutil.copy2(src_struct, pdb_path)
    else:
        try:
            import gemmi

            st = gemmi.read_structure(str(src_struct))
            if hasattr(st, "write_pdb"):
                st.write_pdb(str(pdb_path))
            else:
                pdb_path.write_text(st.make_pdb_string(), encoding="utf-8")
        except Exception:
            pass

    stage("patches")
    residues, patches = cluster_patches(src_struct, rsa_cut=SURFACE_RSA)
    regions = _annotate_regions(seqs)
    for row in residues:
        row["region"] = regions.get((row["chain"], int(row["position"])), "FR")

    _write_csv(
        patches_dir / "residue_sasa.csv",
        residues,
        ["chain", "position", "aa", "region", "sasa", "rsa", "hydrophobic", "surface", "hydro_sasa", "patch_id"],
    )
    (patches_dir / "patches.json").write_text(
        json.dumps({"patches": patches, "rsa_cut": SURFACE_RSA}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_csv(
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
    _write_csv(exports / "mutations.csv", mutations, mut_cols)
    wetlab = [r for r in mutations if r.get("wetlab")]
    _write_csv(exports / "wetlab.csv", wetlab, mut_cols)
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
