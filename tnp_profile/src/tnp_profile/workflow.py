"""Boltz2 折 VHH（或上传结构）→ Kabat 六项指标。"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Any, Callable

from tnp_profile.compactness import compactness_rho, compactness_score
from tnp_profile.constants import DISCLAIMER
from tnp_profile.flags import flag_metrics, load_thresholds
from tnp_profile.numbering import annotate_kabat, parse_fasta
from tnp_profile.patches import patch_scores
from tnp_profile.structure import load_residues, pick_chain


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
    on_stage: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    work_dir = work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    inp = work_dir / "input"
    fold_root = work_dir / "fold"
    score_dir = work_dir / "score"
    exports = work_dir / "exports"
    for d in (inp, fold_root, score_dir, exports):
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
    unknown = [k for k in seqs if k != "H"]
    if unknown:
        raise ValueError(f"第一版只接受 VHH 重链 H，收到: {', '.join(unknown)}")
    if "H" not in seqs:
        raise ValueError("缺少重链 H")
    _write_fasta(seqs, inp / "sequences.fasta")
    sequence = seqs["H"]

    stage("fold")
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
        shutil.copy2(src_struct, cif_path)
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

    stage("score")
    annotation = annotate_kabat(sequence)
    struct_res = load_residues(src_struct)
    chain_id = pick_chain(struct_res, sequence, preferred="H")
    chain_res = [r for r in struct_res if r["chain"] == chain_id]
    rho = compactness_rho(chain_res, annotation["residues"])
    c_score = compactness_score(int(annotation["L3"]), rho)
    patches = patch_scores(src_struct, struct_res, annotation, sequence)

    raw = {
        "L": float(annotation["L"]),
        "L3": float(annotation["L3"]),
        "C": c_score,
        "PSH": patches["PSH"],
        "PPC": patches["PPC"],
        "PNC": patches["PNC"],
    }
    thresholds = load_thresholds()
    flagged = flag_metrics(raw, thresholds)
    metrics = []
    for key, meta in flagged.items():
        metrics.append(
            {
                "id": key,
                "value": meta["value"],
                "flag": meta["flag"],
                "calibrated": meta["calibrated"],
                "thresholds": meta["thresholds"],
            }
        )

    residue_cols = [
        "chain",
        "position",
        "aa",
        "kabat",
        "region",
        "sasa",
        "surface",
        "in_vicinity",
        "hydrophobic",
        "charge",
        "salt_bridged",
        "patch_id",
        "hydro_sasa",
        "rsa",
    ]
    residue_rows = []
    for row in patches["residues"]:
        residue_rows.append(
            {
                **row,
                "patch_id": "Vicinity" if row.get("in_vicinity") else "",
                "hydro_sasa": row.get("sasa") or 0,
                "rsa": 0,
            }
        )
    _write_csv(score_dir / "residue_features.csv", residue_rows, residue_cols)
    _write_csv(exports / "residue_features.csv", residue_rows, residue_cols)

    patch_rows = [
        {
            "patch_id": "Vicinity",
            "kind": "cdr_vicinity",
            "n_residues": patches["n_vicinity"],
            "score": patches["PSH"],
            "residues": ";".join(
                f"{r['chain']}:{r['aa']}{r['position']}" for r in residue_rows if r.get("in_vicinity")
            ),
        }
    ]
    _write_csv(
        exports / "patches.csv",
        patch_rows,
        ["patch_id", "kind", "n_residues", "score", "residues"],
    )

    summary = {
        "disclaimer": DISCLAIMER,
        "scheme": "kabat",
        "structure_engine": "upload" if structure_path else "boltz2",
        "L": annotation["L"],
        "L3": annotation["L3"],
        "C": None if c_score is None else round(c_score, 4),
        "rho": None if rho is None else round(rho, 4),
        "PSH": patches["PSH"],
        "PPC": patches["PPC"],
        "PNC": patches["PNC"],
        "tetrad_motif": annotation["tetrad_motif"],
        "tetrad": annotation["tetrad"],
        "cdr_h1": annotation["cdr_h1"],
        "cdr_h2": annotation["cdr_h2"],
        "cdr_h3": annotation["cdr_h3"],
        "n_vicinity": patches["n_vicinity"],
        "n_surface": patches["n_surface"],
        "metrics": metrics,
        "pred_cif": str(cif_path) if cif_path.is_file() else None,
        "structure": str(src_struct),
        "thresholds_note": thresholds.get("note") or DISCLAIMER,
    }
    (exports / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (score_dir / "metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (work_dir / "workflow_status.json").write_text(
        json.dumps({"stage": "done", "status": "ok", "summary": summary}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if on_stage:
        on_stage("done")
    return {
        "summary": summary,
        "metrics": metrics,
        "residues": residue_rows,
        "patches": patch_rows,
        "pred_cif": str(cif_path) if cif_path.is_file() else None,
    }
