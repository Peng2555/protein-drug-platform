#!/usr/bin/env python3
"""在 TNP 临床 36 条上对比：官网 IMGT 分数 vs 本平台 Kabat 公式（结构用论文 NBB2 PDB）。"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tnp_profile" / "src"))
sys.path.insert(0, str(ROOT / "hydro_redesign" / "src"))
sys.path.insert(0, str(ROOT / "affinity_redesign" / "src"))

from tnp_profile.compactness import compactness_rho, compactness_score
from tnp_profile.flags import TWO_SIDED, cut_from_values
from tnp_profile.numbering import annotate_kabat, parse_fasta
from tnp_profile.patches import patch_scores
from tnp_profile.structure import THREE_TO_ONE, load_residues, pick_chain

FASTA = ROOT / "tnp_profile" / "src" / "tnp_profile" / "data" / "clinical_vhh.fasta"
MODELS = ROOT / "external" / "TNP" / "paper" / "paper_data" / "vhh_clinical_set_models"
OFFICIAL = ROOT / "external" / "TNP" / "paper" / "paper_data" / "insilico_descriptors" / "VHH_TSD_all_properties_FINAL.csv"
OUT = ROOT / "tnp_profile_outputs" / "_clinical_ref_score"


def _hmmer() -> str:
    from pathlib import Path as P
    from affinity_redesign.config import settings

    c = P(settings.hmmer_path)
    return str(c) if (c / "hmmscan").exists() else ""


def annotate_imgt(sequence: str) -> dict:
    from anarci import anarci

    kwargs = {"scheme": "imgt"}
    hmmer = _hmmer()
    if hmmer:
        kwargs["hmmerpath"] = hmmer
    numbering_result, _detail, _hit = anarci([("query", sequence)], **kwargs)
    if not numbering_result or not numbering_result[0]:
        raise ValueError("IMGT 编号失败")
    numbering = numbering_result[0][0][0]
    # IMGT CDR-H1 27-38, H2 56-65, H3 105-117
    spans = {"H1": [], "H2": [], "H3": []}
    for (pos, _ins), aa in numbering:
        if aa == "-":
            continue
        if 27 <= pos <= 38:
            spans["H1"].append(aa)
        elif 56 <= pos <= 65:
            spans["H2"].append(aa)
        elif 105 <= pos <= 117:
            spans["H3"].append(aa)
    L3 = len(spans["H3"])
    L = len(spans["H1"]) + len(spans["H2"]) + L3
    return {"L": L, "L3": L3}


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


def load_official() -> dict[str, dict]:
    by_seq: dict[str, dict] = {}
    with OFFICIAL.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            seq = (row.get("Sequence") or "").strip().upper()
            by_seq[seq] = {
                "name": row.get("SeqID") or "",
                "L": float(row["Total CDR length"]),
                "L3": float(row["CDR3 length"]),
                "C": float(row["CDR3 compactness"]),
                "PSH": float(row["Patches CDR Surface Hydrophobicity"]),
                "PPC": float(row["Patches CDR Positive Charge"]),
                "PNC": float(row["Patches CDR Negative Charge"]),
            }
    return by_seq


def summarize(vals: list[float], two_sided: bool) -> dict:
    cut = cut_from_values(vals, two_sided=two_sided)
    nums = sorted(vals)
    return {
        **cut,
        "mean": sum(vals) / len(vals),
        "sorted": nums,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    seqs = parse_fasta(FASTA.read_text(encoding="utf-8"))
    official = load_official()
    rows = []
    failed = []
    for sid, seq in seqs.items():
        rec = {"id": sid, "seq_len": len(seq), "official_name": "", "match_official": False}
        off = official.get(seq.upper())
        if off is None:
            # try strip C-term extras
            for oseq, o in official.items():
                if seq.upper() in oseq or oseq in seq.upper():
                    off = o
                    break
        if off:
            rec["official_name"] = off["name"]
            rec["match_official"] = True
            rec["off_L"] = off["L"]
            rec["off_L3"] = off["L3"]
            rec["off_C"] = round(off["C"], 4)
            rec["off_PSH"] = off["PSH"]
            rec["off_PPC"] = off["PPC"]
            rec["off_PNC"] = off["PNC"]
        try:
            imgt = annotate_imgt(seq)
            rec["imgt_L"] = imgt["L"]
            rec["imgt_L3"] = imgt["L3"]
            kab = annotate_kabat(seq)
            rec["kabat_L"] = kab["L"]
            rec["kabat_L3"] = kab["L3"]
            rec["tetrad"] = kab["tetrad_motif"]
        except Exception as exc:
            failed.append(f"{sid} numbering: {exc}")
            rows.append(rec)
            continue
        pdb = MODELS / f"{sid}_NanoBodyBuilder2_Model.pdb"
        if not pdb.is_file():
            failed.append(f"{sid} missing pdb")
            rows.append(rec)
            continue
        seq_pdb = OUT / "renumbered" / f"{sid}.pdb"
        try:
            rewrite_sequential(pdb, seq_pdb)
            struct_res = load_residues(seq_pdb)
            chain_id = pick_chain(struct_res, seq, preferred="H")
            chain_res = [r for r in struct_res if r["chain"] == chain_id]
            rho = compactness_rho(chain_res, kab["residues"])
            rec["kabat_rho"] = None if rho is None else round(rho, 4)
            rec["kabat_C"] = None if compactness_score(int(kab["L3"]), rho) is None else round(
                compactness_score(int(kab["L3"]), rho), 4
            )
            patches = patch_scores(seq_pdb, struct_res, kab, seq)
            rec["kabat_PSH"] = patches["PSH"]
            rec["kabat_PPC"] = patches["PPC"]
            rec["kabat_PNC"] = patches["PNC"]
            rec["n_vicinity"] = patches["n_vicinity"]
            rec["n_surface"] = patches["n_surface"]
        except Exception as exc:
            failed.append(f"{sid} structure: {exc}")
        rows.append(rec)
        print(sid, rec.get("kabat_L"), rec.get("kabat_C"), rec.get("kabat_PSH"), flush=True)

    cols = [
        "id",
        "official_name",
        "match_official",
        "seq_len",
        "tetrad",
        "off_L",
        "imgt_L",
        "kabat_L",
        "off_L3",
        "imgt_L3",
        "kabat_L3",
        "off_C",
        "kabat_C",
        "kabat_rho",
        "off_PSH",
        "kabat_PSH",
        "off_PPC",
        "kabat_PPC",
        "off_PNC",
        "kabat_PNC",
        "n_vicinity",
        "n_surface",
    ]
    csv_path = OUT / "clinical36_official_vs_kabat_nbb2.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)

    def col(key: str) -> list[float]:
        return [float(r[key]) for r in rows if r.get(key) is not None]

    cuts = {
        "official": {
            "L": summarize(col("off_L"), True),
            "L3": summarize(col("off_L3"), True),
            "C": summarize(col("off_C"), True),
            "PSH": summarize(col("off_PSH"), True),
            "PPC": summarize(col("off_PPC"), False),
            "PNC": summarize(col("off_PNC"), False),
        },
        "kabat_nbb2": {
            "L": summarize(col("kabat_L"), True),
            "L3": summarize(col("kabat_L3"), True),
            "C": summarize(col("kabat_C"), True) if col("kabat_C") else {},
            "PSH": summarize(col("kabat_PSH"), True) if col("kabat_PSH") else {},
            "PPC": summarize(col("kabat_PPC"), False) if col("kabat_PPC") else {},
            "PNC": summarize(col("kabat_PNC"), False) if col("kabat_PNC") else {},
        },
    }
    # drop sorted from json dump size? keep it, 36 numbers is fine
    payload = {"n": len(rows), "failed": failed, "cuts": cuts, "csv": str(csv_path)}
    (OUT / "clinical36_cuts.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", csv_path)
    print(json.dumps({k: {m: {x: v[x] for x in ("min", "max", "p05", "p95", "mean", "n") if x in v} for m, v in d.items()} for k, d in cuts.items()}, indent=2))
    if failed:
        print("FAILED", len(failed))
        print("\n".join(failed[:20]))


if __name__ == "__main__":
    main()
