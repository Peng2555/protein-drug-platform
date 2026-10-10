#!/usr/bin/env python3
"""用用户提供的 43 条阳性药 VHH 重切 Kabat 阈值。

L/L3：全部 43 条序列。
C/PSH/PPC/PNC：仅当序列能精确对上 TNP 论文 NBB2 模型时打分（与上一版结构口径一致）。
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from algorithm_paths import bootstrap_algorithm_paths

bootstrap_algorithm_paths()

from tnp_profile.calibrate import write_thresholds
from tnp_profile.compactness import compactness_rho, compactness_score
from tnp_profile.constants import DISCLAIMER, THRESHOLDS_PATH
from tnp_profile.flags import INTEGER_METRICS, ONE_SIDED_HIGH, TWO_SIDED, cut_from_values
from tnp_profile.numbering import annotate_kabat, parse_fasta
from tnp_profile.patches import patch_scores
from tnp_profile.structure import THREE_TO_ONE, load_residues, pick_chain

NEW_FASTA = ROOT / "workflows/tnp_profile/src/tnp_profile/data/clinical_vhh_positive43.fasta"
OLD_FASTA = ROOT / "external/TNP/paper/paper_data/sequences/vhh_tsd.fasta"
MODELS = ROOT / "external/TNP/paper/paper_data/vhh_clinical_set_models"
OUT = ROOT / "tnp_profile_outputs/_positive43_recalibrate"


def rewrite_sequential(src: Path, dest: Path) -> None:
    import gemmi

    st = gemmi.read_structure(str(src))
    model = st[0]
    n = 1
    for chain in model:
        for res in chain:
            if res.name not in THREE_TO_ONE and res.name != "MSE":
                continue
            res.seqid = gemmi.SeqId(str(n))
            n += 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(st, "write_pdb"):
        st.write_pdb(str(dest))
    else:
        dest.write_text(st.make_pdb_string(), encoding="utf-8")


def flag_table(spec: dict) -> str:
    p05, p95 = spec["p05"], spec["p95"]
    lo, hi = spec["red_lt"], spec["red_gt"]
    if not spec.get("two_sided"):
        return f"绿 <{p95}；黄 {p95}–{hi}；红 >{hi}"
    return f"绿 {p05 + (0 if spec.get('integer') else 0.01):g}–{p95 - (0 if spec.get('integer') else 0.01):g}；黄 {lo}–{p05} 或 {p95}–{hi}；红 <{lo} 或 >{hi}"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    new_seqs = parse_fasta(NEW_FASTA.read_text(encoding="utf-8"))
    old_seqs = parse_fasta(OLD_FASTA.read_text(encoding="utf-8")) if OLD_FASTA.is_file() else {}
    old_by_seq = {seq.upper(): sid for sid, seq in old_seqs.items()}

    rows = []
    L_vals, L3_vals = [], []
    struct_vals = {"C": [], "PSH": [], "PPC": [], "PNC": []}
    failed = []

    for header, seq in new_seqs.items():
        rec = {"id": header, "seq_len": len(seq), "nbb2": "", "struct_scored": False}
        uid = header.split("|")[2] if "|" in header else header
        rec["uid"] = uid
        rec["name"] = "|".join(header.split("|")[:2])
        try:
            ann = annotate_kabat(seq)
        except Exception as exc:
            failed.append(f"{uid} numbering: {exc}")
            rows.append(rec)
            continue
        rec["L"] = int(ann["L"])
        rec["L3"] = int(ann["L3"])
        rec["tetrad"] = ann["tetrad_motif"]
        L_vals.append(float(ann["L"]))
        L3_vals.append(float(ann["L3"]))

        sid = old_by_seq.get(seq.upper())
        pdb = MODELS / f"{sid}_NanoBodyBuilder2_Model.pdb" if sid else None
        rec["nbb2"] = sid or ""
        if not pdb or not pdb.is_file():
            rec["struct_note"] = "no_nbb2_exact_match"
            rows.append(rec)
            print(uid, rec["name"], "L", rec["L"], "L3", rec["L3"], "no NBB2", flush=True)
            continue
        seq_pdb = OUT / "renumbered" / f"{uid}.pdb"
        try:
            rewrite_sequential(pdb, seq_pdb)
            struct_res = load_residues(seq_pdb)
            chain_id = pick_chain(struct_res, seq, preferred="H")
            chain_res = [r for r in struct_res if r["chain"] == chain_id]
            n_ca = sum(1 for r in chain_res)
            if n_ca != len(seq):
                rec["struct_note"] = f"length_mismatch pdb={n_ca} seq={len(seq)}"
                rows.append(rec)
                print(uid, "length mismatch", n_ca, len(seq), flush=True)
                continue
            rho = compactness_rho(chain_res, ann["residues"])
            rec["C"] = compactness_score(int(ann["L3"]), rho)
            patches = patch_scores(seq_pdb, struct_res, ann, seq)
            rec["PSH"] = patches["PSH"]
            rec["PPC"] = patches["PPC"]
            rec["PNC"] = patches["PNC"]
            rec["n_vicinity"] = patches["n_vicinity"]
            rec["struct_scored"] = True
            if rec["C"] is not None:
                struct_vals["C"].append(float(rec["C"]))
            for k in ("PSH", "PPC", "PNC"):
                struct_vals[k].append(float(rec[k]))
        except Exception as exc:
            failed.append(f"{uid} structure: {exc}")
            rec["struct_note"] = str(exc)
        rows.append(rec)
        print(uid, rec["name"], "L", rec["L"], "C", rec.get("C"), "PSH", rec.get("PSH"), "PPC", rec.get("PPC"), flush=True)

    metrics = {
        "L": cut_from_values(L_vals, two_sided=True, integer=True),
        "L3": cut_from_values(L3_vals, two_sided=True, integer=True),
    }
    for key in ("C", "PSH", "PPC", "PNC"):
        vals = struct_vals[key]
        if len(vals) >= 5:
            metrics[key] = cut_from_values(
                vals,
                two_sided=key in TWO_SIDED and key not in ONE_SIDED_HIGH,
                integer=key in INTEGER_METRICS,
            )
        else:
            metrics[key] = {"calibrated": False, "two_sided": key not in ONE_SIDED_HIGH}

    payload = {
        "scheme": "kabat",
        "structure_engine": "nanobodybuilder2_paper_models",
        "task_fold_engine": "boltz2",
        "reference": "user_positive43_vhh_clinical_check",
        "method": "TNP/TAP: red outside clinical min/max; amber ~5%/95%; integer L/L3 high bound = max+1; PPC/PNC high-side only",
        "n_sequence": len(L_vals),
        "n_structure": len(struct_vals["PSH"]),
        "note": DISCLAIMER + " 参考集换成用户 43 条阳性药 VHH；结构项仅对能精确对上论文 NBB2 模型的序列标定。",
        "metrics": metrics,
        "numbering_failures": failed,
    }

    csv_path = OUT / "positive43_kabat_scores.csv"
    cols = [
        "uid",
        "name",
        "seq_len",
        "nbb2",
        "struct_scored",
        "L",
        "L3",
        "C",
        "PSH",
        "PPC",
        "PNC",
        "tetrad",
        "n_vicinity",
        "struct_note",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    old_path = THRESHOLDS_PATH
    backup = old_path.with_name("thresholds_tnp36_backup.json")
    if old_path.is_file() and not backup.is_file():
        shutil.copy2(old_path, backup)
    dest = write_thresholds(payload, old_path)
    alt = OUT / "thresholds_positive43.json"
    write_thresholds(payload, alt)
    (OUT / "payload.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("wrote", dest)
    print("backup", backup if backup.is_file() else "skipped")
    print("csv", csv_path)
    print("n_sequence", payload["n_sequence"], "n_structure", payload["n_structure"])
    print("failed", failed)
    for key, spec in metrics.items():
        print(key, spec)


if __name__ == "__main__":
    main()
