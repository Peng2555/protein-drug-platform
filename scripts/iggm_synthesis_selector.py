#!/usr/bin/env python3
"""从测序表 + IgGM 突变结果中筛选「可送合成」候选（体细胞高频突变 SHM 感知版）。"""

from __future__ import annotations

import argparse
import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Mutation:
    pos: int
    wt: str
    mut: str

    def key(self) -> tuple[int, str, str]:
        return (self.pos, self.wt, self.mut)

    def label(self) -> str:
        return f"{self.pos}{self.wt}{self.mut}"

    def detail(self) -> str:
        return f"Pos: {self.pos}, {self.wt} -> {self.mut}"


@dataclass
class SynthesisSelectParams:
    min_seq_count: float = 10.0
    top_n: int = 30
    mutation_min: int = 1
    mutation_max: int = 3
    seq_col: str | None = None
    cdr3_col: str | None = None
    count_col: str | None = None
    v_gene: str | None = None
    max_extra_cdr3_muts: int = 3
    chain_id: str = "H"


KABAT_REGIONS = [
    "kabat_FR1", "kabat_CDR1", "kabat_FR2", "kabat_CDR2",
    "kabat_FR3", "kabat_CDR3", "kabat_FR4",
]

SYNTHESIS_FIELDS = [
    "final_rank", "rank_score", "recommend_for_synthesis", "match_mode", "cdr3_exact_iggm",
    "iggm_variant_id", "mutation_count", "iggm_frequency", "iggm_source",
    "iggm_design_mutations", "iggm_cdr3",
    "seq_count", "seq_row",
    "synthesis_sequence", "sequencing_cdr3",
    "extra_cdr3_shm", "extra_outside_cdr3_shm", "shm_regions_detail",
    "v_gene", "j_gene", "PI", "free_Cys", "errorAb", "match_hits",
]


def read_table(path: str | Path) -> tuple[list[str], list[dict]]:
    path = Path(path)
    ext = path.suffix.lower()
    if ext in {".xlsx", ".xls"}:
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError("读取 Excel 需要安装 pandas 与 openpyxl") from exc
        df = pd.read_excel(path)
        df = df.fillna("")
        return list(df.columns), df.to_dict(orient="records")

    delimiter = "\t" if ext == ".tsv" else ","
    with path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        rows = []
        for row in reader:
            clean = {}
            for k, v in row.items():
                key = (k or "").strip()
                clean[key] = v.strip() if isinstance(v, str) else v
            rows.append(clean)
        return reader.fieldnames or [], rows


def norm_seq(s) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", "", str(s)).upper()


def to_float(v, default=0.0):
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def parse_mutation_text(text: str) -> list[Mutation]:
    if not text:
        return []
    muts = []
    for block in re.split(r"[;|]", str(text)):
        block = block.strip()
        if not block:
            continue
        m = re.search(r"Pos:\s*(\d+)\s*,\s*([A-Z\*])\s*->\s*([A-Z\*])", block, re.I)
        if m:
            muts.append(Mutation(int(m.group(1)), m.group(2).upper(), m.group(3).upper()))
            continue
        m = re.search(r"(\d+)\s*([A-Z\*])\s*[->→]\s*([A-Z\*])", block, re.I)
        if m:
            muts.append(Mutation(int(m.group(1)), m.group(2).upper(), m.group(3).upper()))
    return muts


def diff_sequence(parent: str, seq: str) -> list[Mutation]:
    if not parent or not seq:
        return []
    n = min(len(parent), len(seq))
    return [Mutation(i + 1, parent[i], seq[i]) for i in range(n) if parent[i] != seq[i]]


def diff_cdr3_window(parent_cdr3: str, seq_cdr3: str, cdr3_start: int) -> list[Mutation]:
    if not parent_cdr3 or not seq_cdr3 or len(parent_cdr3) != len(seq_cdr3):
        return []
    muts = []
    for i, (a, b) in enumerate(zip(parent_cdr3, seq_cdr3)):
        if a != b:
            muts.append(Mutation(cdr3_start + i, a, b))
    return muts


def load_parent(origin_fasta: str | Path, chain_id: str = "H") -> str:
    seqs, ids = [], []
    cur, buf = None, []
    with open(origin_fasta, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith(">"):
                if cur is not None:
                    seqs.append("".join(buf))
                    ids.append(cur)
                cur, buf = line[1:].split()[0], []
            elif line:
                buf.append(line)
    if cur is not None:
        seqs.append("".join(buf))
        ids.append(cur)
    return seqs[ids.index(chain_id)] if chain_id in ids else seqs[0]


def load_cdr3_window(mask_fasta: str | Path, parent: str, chain_id: str = "H") -> tuple[int, int, str]:
    seqs, ids = [], []
    cur, buf = None, []
    with open(mask_fasta, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith(">"):
                if cur is not None:
                    seqs.append("".join(buf))
                    ids.append(cur)
                cur, buf = line[1:].split()[0], []
            elif line:
                buf.append(line)
    if cur is not None:
        seqs.append("".join(buf))
        ids.append(cur)
    mask = seqs[ids.index(chain_id)] if chain_id in ids else seqs[0]
    xs = [i for i, ch in enumerate(mask) if ch == "X"]
    if not xs:
        raise ValueError(f"{mask_fasta} 中未找到 X 标记的 CDR3 区域")
    start = xs[0] + 1
    end = xs[-1] + 1
    return start, end, parent[start - 1 : end]


def pick_col(cols: list[str], *candidates, default=None):
    lower = {c.lower(): c for c in cols}
    if default and default in cols:
        return default
    for name in candidates:
        if name.lower() in lower:
            return lower[name.lower()]
    return None


def load_iggm(path: str | Path, parent: str, cdr3_start: int, cdr3_end: int) -> list[dict]:
    _, rows = read_table(path)
    out = []
    for row in rows:
        design_muts = parse_mutation_text(row.get("cdr3_mutations", "") or row.get("mutation_details", ""))
        if not design_muts and row.get("antibody_seq_h"):
            design_muts = [
                m for m in diff_sequence(parent, norm_seq(row["antibody_seq_h"]))
                if cdr3_start <= m.pos <= cdr3_end
            ]
        out.append({
            "variant_id": row.get("variant_id", ""),
            "mutation_count": int(to_float(row.get("mutation_count", 0))),
            "iggm_frequency": to_float(row.get("frequency", 0)),
            "source": row.get("source", ""),
            "iggm_cdr3": norm_seq(row.get("cdr3_seq", "")),
            "iggm_mutations": row.get("cdr3_mutations", "") or row.get("mutation_details", ""),
            "iggm_seq": norm_seq(row.get("antibody_seq_h", "")),
            "design_keys": frozenset(m.key() for m in design_muts),
            "design_muts": design_muts,
        })
    return out


def infer_parent_kabat_regions(parent: str, ref_row: dict, cols: list[str]) -> dict[str, str]:
    region_cols = [pick_col(cols, r, default=r) for r in KABAT_REGIONS]
    region_cols = [c for c in region_cols if c and norm_seq(ref_row.get(c, ""))]
    if not region_cols:
        return {}

    cursor = 0
    regions = {}
    for col in region_cols:
        seg = norm_seq(ref_row.get(col, ""))
        length = len(seg)
        if cursor + length > len(parent):
            return {}
        regions[col] = parent[cursor : cursor + length]
        cursor += length
    return regions


def summarize_extra_shm_regions(seq_row: dict, cols: list[str], parent_regions: dict[str, str]) -> str:
    notes = []
    for col in KABAT_REGIONS:
        rc = pick_col(cols, col, default=col)
        if not rc or rc not in parent_regions:
            continue
        parent_seg = parent_regions[rc]
        seq_seg = norm_seq(seq_row.get(rc, ""))
        if not seq_seg or len(seq_seg) != len(parent_seg):
            continue
        muts = []
        for i, (a, b) in enumerate(zip(parent_seg, seq_seg)):
            if a != b:
                muts.append(f"{col}[{i+1}]{a}{b}")
        if muts:
            notes.append(f"{col.replace('kabat_', '')}:{'|'.join(muts)}")
    return "; ".join(notes)


def prepare_sequencing_rows(
    rows: list[dict],
    cols: list[str],
    params: SynthesisSelectParams,
    parent: str,
    parent_cdr3: str,
    cdr3_start: int,
    cdr3_end: int,
    parent_regions: dict[str, str],
) -> list[dict]:
    seq_col = params.seq_col or pick_col(
        cols, "sequence_v_aa_germline", "sequence_", "sequence", "seq", "antibody_seq_h"
    )
    cdr3_col = params.cdr3_col or pick_col(cols, "kabat_CDR3", "cdr3", "cdr3_seq", "junction_aa")
    count_col = params.count_col or pick_col(cols, "seq_count", "count", "reads", "frequency")
    err_col = pick_col(cols, "errorAb", "error_ab")
    cys_col = pick_col(cols, "free_Cys", "free_cys")

    if not cdr3_col and not seq_col:
        raise ValueError(f"未找到序列列，现有列: {cols}")

    kept = []
    for i, row in enumerate(rows):
        count = to_float(row.get(count_col, 0)) if count_col else 0
        if count < params.min_seq_count:
            continue
        if err_col and str(row.get(err_col, "0")).strip() not in {"0", "0.0", "", "No", "False"}:
            continue
        if cys_col and str(row.get(cys_col, "")).strip().lower() in {"yes", "true", "1"}:
            continue
        if params.v_gene and str(row.get("v_gene", "")).strip() != params.v_gene:
            continue

        full_seq = norm_seq(row.get(seq_col, "")) if seq_col else ""
        seq_cdr3 = norm_seq(row.get(cdr3_col, "")) if cdr3_col else ""
        cdr3_muts = diff_cdr3_window(parent_cdr3, seq_cdr3, cdr3_start)
        full_muts = diff_sequence(parent, full_seq) if full_seq and len(full_seq) == len(parent) else []
        shm_regions = summarize_extra_shm_regions(row, cols, parent_regions) if parent_regions else ""

        kept.append({
            "row_index": i + 2,
            "seq_count": count,
            "sequence": full_seq,
            "cdr3": seq_cdr3,
            "cdr3_mut_keys": frozenset(m.key() for m in cdr3_muts),
            "cdr3_muts": cdr3_muts,
            "full_mut_keys": frozenset(m.key() for m in full_muts),
            "full_muts": full_muts,
            "shm_regions": shm_regions,
            "raw": row,
        })
    return kept


def find_shm_aware_hits(ig, seq_rows, parent_cdr3, cdr3_start, cdr3_end, max_extra_cdr3_muts):
    hits = []
    for s in seq_rows:
        if not s["cdr3"] or len(s["cdr3"]) != len(parent_cdr3):
            continue
        extra_cdr3 = [m for m in s["cdr3_muts"] if m.key() not in ig["design_keys"]]
        if len(extra_cdr3) > max_extra_cdr3_muts:
            continue

        match_mode = None
        if ig["design_keys"] and ig["design_keys"].issubset(s["cdr3_mut_keys"]):
            match_mode = "design_subset_cdr3"
        elif ig["design_keys"] and s["full_mut_keys"] and ig["design_keys"].issubset(s["full_mut_keys"]):
            match_mode = "design_subset_full"

        if not match_mode:
            continue

        extra_full = [m for m in s["full_muts"] if m.key() not in ig["design_keys"]]
        extra_outside_cdr3 = [m for m in extra_full if not (cdr3_start <= m.pos <= cdr3_end)]

        hits.append({
            **s,
            "match_mode": match_mode,
            "cdr3_exact_iggm": s["cdr3"] == ig["iggm_cdr3"],
            "extra_cdr3_shm": "; ".join(m.label() for m in extra_cdr3),
            "extra_outside_cdr3_shm": "; ".join(m.label() for m in extra_outside_cdr3),
            "extra_shm_count_cdr3": len(extra_cdr3),
            "extra_shm_count_outside": len(extra_outside_cdr3),
        })
    return hits


def score_candidate(iggm_freq, seq_count, mutation_count, extra_outside):
    return (
        iggm_freq
        + math.log10(max(seq_count, 1) + 1) * 20
        - max(0, mutation_count - 1) * 3
        - extra_outside * 0.5
    )


def write_csv(path: str | Path, rows: list[dict], fields: list[str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def run_synthesis_selection(
    *,
    sequencing_table: str | Path,
    iggm_table: str | Path,
    origin_fasta: str | Path,
    mask_fasta: str | Path,
    out_dir: str | Path,
    params: SynthesisSelectParams | None = None,
) -> dict:
    params = params or SynthesisSelectParams()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    parent = load_parent(origin_fasta, params.chain_id)
    cdr3_start, cdr3_end, parent_cdr3 = load_cdr3_window(mask_fasta, parent, params.chain_id)

    cols, seq_rows_raw = read_table(sequencing_table)
    cdr3_col_name = params.cdr3_col or pick_col(cols, "kabat_CDR3", "cdr3", "cdr3_seq")
    count_col_name = params.count_col or pick_col(cols, "seq_count", "count", "reads", "frequency")

    ref_row = None
    if cdr3_col_name:
        candidates = [r for r in seq_rows_raw if norm_seq(r.get(cdr3_col_name, "")) == parent_cdr3]
        if candidates and count_col_name:
            ref_row = max(candidates, key=lambda r: to_float(r.get(count_col_name, 0)))
        elif seq_rows_raw:
            ref_row = seq_rows_raw[0]
    parent_regions = infer_parent_kabat_regions(parent, ref_row, cols) if ref_row else {}

    seq_rows = prepare_sequencing_rows(
        seq_rows_raw, cols, params, parent, parent_cdr3, cdr3_start, cdr3_end, parent_regions
    )
    iggm_rows = load_iggm(iggm_table, parent, cdr3_start, cdr3_end)

    synthesis = []
    unmatched_iggm = []

    for ig in iggm_rows:
        if not (params.mutation_min <= ig["mutation_count"] <= params.mutation_max):
            continue
        if not ig["design_keys"]:
            continue

        hits = find_shm_aware_hits(
            ig, seq_rows, parent_cdr3, cdr3_start, cdr3_end, params.max_extra_cdr3_muts
        )
        if not hits:
            unmatched_iggm.append(ig)
            continue

        best = max(
            hits,
            key=lambda x: (
                x["cdr3_exact_iggm"],
                x["seq_count"],
                -x["extra_shm_count_cdr3"],
                -x["extra_shm_count_outside"],
            ),
        )
        raw = best["raw"]
        sc = score_candidate(
            ig["iggm_frequency"],
            best["seq_count"],
            ig["mutation_count"],
            best["extra_shm_count_outside"],
        )
        synthesis.append({
            "rank_score": round(sc, 2),
            "recommend_for_synthesis": "YES",
            "match_mode": best["match_mode"],
            "cdr3_exact_iggm": "YES" if best["cdr3_exact_iggm"] else "NO",
            "iggm_variant_id": ig["variant_id"],
            "mutation_count": ig["mutation_count"],
            "iggm_frequency": ig["iggm_frequency"],
            "iggm_source": ig["source"],
            "iggm_design_mutations": ig["iggm_mutations"],
            "iggm_cdr3": ig["iggm_cdr3"],
            "seq_count": best["seq_count"],
            "seq_row": best["row_index"],
            "synthesis_sequence": best["sequence"],
            "sequencing_cdr3": best["cdr3"],
            "extra_cdr3_shm": best["extra_cdr3_shm"],
            "extra_outside_cdr3_shm": best["extra_outside_cdr3_shm"],
            "shm_regions_detail": best["shm_regions"],
            "v_gene": raw.get("v_gene", ""),
            "j_gene": raw.get("j_gene", ""),
            "PI": raw.get("PI", ""),
            "free_Cys": raw.get("free_Cys", ""),
            "errorAb": raw.get("errorAb", ""),
            "match_hits": len(hits),
        })

    synthesis.sort(key=lambda x: (-x["rank_score"], -x["seq_count"], -x["iggm_frequency"]))

    dedup = []
    seen = set()
    for row in synthesis:
        key = (row["sequencing_cdr3"], row["synthesis_sequence"])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(row)

    top = dedup[: params.top_n]
    for i, row in enumerate(top, 1):
        row["final_rank"] = i

    top_csv = out_dir / "synthesis_candidates_top.csv"
    all_csv = out_dir / "synthesis_candidates_all.csv"
    unmatched_csv = out_dir / "iggm_not_in_sequencing_filtered.csv"

    write_csv(all_csv, dedup, SYNTHESIS_FIELDS)
    write_csv(top_csv, top, SYNTHESIS_FIELDS)
    write_csv(
        unmatched_csv,
        unmatched_iggm,
        ["variant_id", "mutation_count", "iggm_frequency", "source", "iggm_cdr3", "iggm_mutations", "iggm_seq"],
    )

    iggm_in_range = sum(
        1 for x in iggm_rows if params.mutation_min <= x["mutation_count"] <= params.mutation_max
    )

    return {
        "sequencing_total": len(seq_rows_raw),
        "sequencing_filtered": len(seq_rows),
        "iggm_in_range": iggm_in_range,
        "matched_count": len(dedup),
        "top_count": len(top),
        "unmatched_iggm_count": len(unmatched_iggm),
        "parent_cdr3": parent_cdr3,
        "cdr3_region": f"{cdr3_start}-{cdr3_end}",
        "top_csv": str(top_csv),
        "all_csv": str(all_csv),
        "unmatched_csv": str(unmatched_csv),
        "out_dir": str(out_dir),
    }


def main():
    parser = argparse.ArgumentParser(description="SHM 感知：筛选可送合成的 IgGM×测序候选")
    parser.add_argument("--sequencing_table", required=True)
    parser.add_argument("--iggm_table", required=True)
    parser.add_argument("--origin_fasta", required=True)
    parser.add_argument("--mask_fasta", required=True)
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--chain_id", default="H")
    parser.add_argument("--min_seq_count", type=float, default=10)
    parser.add_argument("--top_n", type=int, default=30)
    parser.add_argument("--mutation_min", type=int, default=1)
    parser.add_argument("--mutation_max", type=int, default=3)
    parser.add_argument("--seq_col", default=None)
    parser.add_argument("--cdr3_col", default=None)
    parser.add_argument("--count_col", default=None)
    parser.add_argument("--v_gene", default=None)
    parser.add_argument("--max_extra_cdr3_muts", type=int, default=3)
    args = parser.parse_args()

    params = SynthesisSelectParams(
        min_seq_count=args.min_seq_count,
        top_n=args.top_n,
        mutation_min=args.mutation_min,
        mutation_max=args.mutation_max,
        seq_col=args.seq_col,
        cdr3_col=args.cdr3_col,
        count_col=args.count_col,
        v_gene=args.v_gene,
        max_extra_cdr3_muts=args.max_extra_cdr3_muts,
        chain_id=args.chain_id,
    )
    result = run_synthesis_selection(
        sequencing_table=args.sequencing_table,
        iggm_table=args.iggm_table,
        origin_fasta=args.origin_fasta,
        mask_fasta=args.mask_fasta,
        out_dir=args.out_dir,
        params=params,
    )
    print("=== SHM 感知合成候选筛选完成 ===")
    for k, v in result.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
