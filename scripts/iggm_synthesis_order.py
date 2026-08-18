#!/usr/bin/env python3
"""从 IgGM↔SHM 匹配结果整理 A/B 档送合成清单。"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SynthesisOrderParams:
    min_extra_count: int = 100


ORDER_FIELDS = [
    "synthesis_id", "priority", "recommend",
    "iggm_variant_id", "iggm_cdr3", "seq_count", "shm_row",
    "cdr3_mutation_sites", "extra_mutation_sites",
    "all_mutation_sites_for_synthesis", "n_total_mutations",
    "synthesis_sequence", "nucleotide_sequence",
    "v_gene", "j_gene", "PI", "note",
]


def read_csv(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: str | Path, rows: list[dict], fields: list[str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def parse_labels(text: str) -> list[str]:
    if not text or text in {"none", "无"}:
        return []
    return [x.strip() for x in re.split(r"[;|]", text) if x.strip()]


def format_mutation_site(label: str) -> str:
    label = label.strip()
    if "→" in label:
        return label
    m = re.match(r"(\d+)([A-Z\*])([A-Z\*])", label)
    if not m:
        return label
    return f"{m.group(1)}{m.group(2)}→{m.group(3)}"


def all_sites(cdr3_labels: list[str], extra_labels: list[str]) -> str:
    parts = [format_mutation_site(x) for x in cdr3_labels + extra_labels]
    return "; ".join(parts) if parts else "无（与母本骨架相同）"


def build_synthesis_order(
    matched_csv: str | Path,
    out_dir: str | Path,
    *,
    params: SynthesisOrderParams | None = None,
    parent_cdr3: str | None = None,
    parent_v_gene: str | None = None,
) -> dict:
    params = params or SynthesisOrderParams()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    match_rows = read_csv(matched_csv)
    if not match_rows:
        raise ValueError("匹配结果为空，无法生成送合成清单")

    if parent_cdr3 is None:
        parent_cdr3 = match_rows[0].get("shm_kabat_CDR3", "")
    if parent_v_gene is None:
        parent_v_gene = match_rows[0].get("parent_v_gene", "")

    by_variant: dict[str, list[dict]] = {}
    for row in match_rows:
        by_variant.setdefault(row["iggm_variant_id"], []).append(row)

    synthesis: list[dict] = []
    syn_id = 1

    for vid, rows in sorted(
        by_variant.items(),
        key=lambda x: -max(float(r.get("iggm_frequency") or 0) for r in x[1]),
    ):
        clean = [r for r in rows if r.get("has_extra_shm") == "NO"]
        if not clean:
            continue
        best = max(clean, key=lambda x: int(float(x["seq_count"])))
        cdr3 = parse_labels(best.get("cdr3_mutation_sites_in_shm_row", ""))
        extra = parse_labels(best.get("extra_mutation_sites_in_shm_row", ""))
        synthesis.append({
            "synthesis_id": f"SYN-{syn_id:03d}",
            "priority": "A-核心推荐",
            "recommend": "YES",
            "iggm_variant_id": vid,
            "iggm_cdr3": best["iggm_cdr3"],
            "seq_count": best["seq_count"],
            "shm_row": best["shm_file_line"],
            "cdr3_mutation_sites": "; ".join(format_mutation_site(x) for x in cdr3) or "无",
            "extra_mutation_sites": "无",
            "all_mutation_sites_for_synthesis": all_sites(cdr3, extra),
            "n_total_mutations": len(cdr3) + len(extra),
            "synthesis_sequence": best["aa_sequence"],
            "nucleotide_sequence": best.get("nucleotide_sequence", ""),
            "v_gene": best["v_gene"],
            "j_gene": best["j_gene"],
            "PI": best.get("PI", ""),
            "note": "IgGM+SHM CDR3精确匹配，无额外SHM，优先送合成",
        })
        syn_id += 1

    seen_sig: set[tuple] = set()
    for r in sorted(match_rows, key=lambda x: -int(float(x["seq_count"]))):
        if r.get("has_extra_shm") != "YES":
            continue
        cnt = int(float(r["seq_count"]))
        if cnt < params.min_extra_count:
            continue
        cdr3 = parse_labels(r.get("cdr3_mutation_sites_in_shm_row", ""))
        extra = parse_labels(r.get("extra_mutation_sites_in_shm_row", ""))
        sig = (r["iggm_variant_id"], tuple(sorted(cdr3)), tuple(sorted(extra)))
        if sig in seen_sig:
            continue
        seen_sig.add(sig)
        synthesis.append({
            "synthesis_id": f"SYN-{syn_id:03d}",
            "priority": "B-含额外SHM",
            "recommend": "OPTIONAL",
            "iggm_variant_id": r["iggm_variant_id"],
            "iggm_cdr3": r["iggm_cdr3"],
            "seq_count": cnt,
            "shm_row": r["shm_file_line"],
            "cdr3_mutation_sites": "; ".join(format_mutation_site(x) for x in cdr3) or "无",
            "extra_mutation_sites": "; ".join(format_mutation_site(x) for x in extra) or "无",
            "all_mutation_sites_for_synthesis": all_sites(cdr3, extra),
            "n_total_mutations": len(cdr3) + len(extra),
            "synthesis_sequence": r["aa_sequence"],
            "nucleotide_sequence": r.get("nucleotide_sequence", ""),
            "v_gene": r["v_gene"],
            "j_gene": r["j_gene"],
            "PI": r.get("PI", ""),
            "note": f"IgGM CDR3匹配 + {len(extra)}个额外SHM位点",
        })
        syn_id += 1

    csv_path = out_dir / "synthesis_order.csv"
    write_csv(csv_path, synthesis, ORDER_FIELDS)

    txt_path = out_dir / "synthesis_order.txt"
    with txt_path.open("w", encoding="utf-8") as f:
        f.write("送合成清单\n")
        f.write("=" * 60 + "\n")
        if parent_v_gene:
            f.write(f"参考骨架: 母本 {parent_v_gene}")
        if parent_cdr3:
            f.write(f", CDR3={parent_cdr3}")
        f.write("\n突变位点均相对母本骨架\n\n")

        for tier in ["A-核心推荐", "B-含额外SHM"]:
            tier_rows = [s for s in synthesis if s["priority"] == tier]
            if not tier_rows:
                continue
            f.write(f"\n【{tier}】共 {len(tier_rows)} 条\n")
            f.write("-" * 60 + "\n")
            for s in tier_rows:
                f.write(f"\n{s['synthesis_id']}  {s['iggm_variant_id']}  count={s['seq_count']}\n")
                f.write(f"  CDR3: {s['iggm_cdr3']}\n")
                f.write(f"  CDR3突变位点: {s['cdr3_mutation_sites']}\n")
                f.write(f"  额外突变位点: {s['extra_mutation_sites']}\n")
                f.write(f"  ★ 合成需引入的全部突变: {s['all_mutation_sites_for_synthesis']}\n")
                f.write(f"  氨基酸序列: {s['synthesis_sequence']}\n")
                if s.get("nucleotide_sequence"):
                    f.write(f"  核苷酸序列: {s['nucleotide_sequence']}\n")
                f.write(f"  {s['note']}\n")

    a_count = sum(1 for s in synthesis if s["priority"] == "A-核心推荐")
    b_count = sum(1 for s in synthesis if s["priority"] == "B-含额外SHM")

    return {
        "order_count": len(synthesis),
        "a_count": a_count,
        "b_count": b_count,
        "order_csv": str(csv_path),
        "order_txt": str(txt_path),
        "out_dir": str(out_dir),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--matched_csv", required=True)
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--min_extra_count", type=int, default=100)
    parser.add_argument("--parent_cdr3", default=None)
    parser.add_argument("--parent_v_gene", default=None)
    args = parser.parse_args()

    result = build_synthesis_order(
        args.matched_csv,
        args.out_dir,
        params=SynthesisOrderParams(min_extra_count=args.min_extra_count),
        parent_cdr3=args.parent_cdr3,
        parent_v_gene=args.parent_v_gene,
    )
    print("=== 送合成清单已整理 ===")
    for k, v in result.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
