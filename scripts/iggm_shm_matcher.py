#!/usr/bin/env python3
"""IgGM CDR3 ↔ SHM 大表匹配（v_gene 预筛选 + CDR3 精确匹配）。"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict

KABAT_REGIONS_BEFORE_CDR3 = (
    "kabat_FR1", "kabat_CDR1", "kabat_FR2", "kabat_CDR2", "kabat_FR3",
)
KABAT_REGIONS_ALL = (*KABAT_REGIONS_BEFORE_CDR3, "kabat_CDR3", "kabat_FR4")


@dataclass(frozen=True)
class Mut:
    pos: int
    wt: str
    mut: str

    def label(self) -> str:
        return f"{self.pos}{self.wt}{self.mut}"


@dataclass
class ShmMatchParams:
    min_seq_count: int = 30
    v_gene: str | None = None
    chain_id: str = "H"


MATCHED_FIELDS = [
    "iggm_variant_id", "iggm_mutation_count", "iggm_frequency", "iggm_source",
    "iggm_cdr3", "iggm_cdr3_mutations", "iggm_cdr3_mutation_sites",
    "shm_file_line", "shm_sequence_id", "seq_count",
    "v_gene", "j_gene", "d_call", "shm_kabat_CDR3",
    "cdr3_mutation_sites_in_shm_row", "extra_mutation_sites_in_shm_row",
    "all_mutation_sites_vs_parent", "n_cdr3_mutations", "n_extra_mutations", "has_extra_shm",
    "nucleotide_sequence", "aa_sequence", "PI",
    "parent_reference_file_line", "parent_v_gene",
]


def read_table(path: str | Path) -> list[dict]:
    path = Path(path)
    ext = path.suffix.lower()
    if ext in {".xlsx", ".xls"}:
        import pandas as pd
        df = pd.read_excel(path)
        df = df.fillna("")
        return df.to_dict(orient="records")
    delim = "\t" if ext == ".tsv" else ","
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=delim))


def norm(s) -> str:
    return re.sub(r"\s+", "", str(s or "")).upper()


def to_int(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def load_fasta_chain(path: str | Path, chain_id: str = "H") -> str:
    seqs, ids, cur, buf = [], [], None, []
    with open(path, encoding="utf-8") as f:
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


def has_kabat_columns(row: dict) -> bool:
    return all(norm(row.get(col, "")) for col in KABAT_REGIONS_ALL)


def stitch_kabat_sequence(row: dict) -> str:
    return "".join(norm(row.get(col, "")) for col in KABAT_REGIONS_ALL)


def cdr3_bounds_from_kabat_row(row: dict) -> tuple[int, int]:
    offset = sum(len(norm(row.get(col, ""))) for col in KABAT_REGIONS_BEFORE_CDR3)
    cdr3 = norm(row.get("kabat_CDR3", ""))
    if not cdr3:
        raise ValueError("SHM 参考行缺少 kabat_CDR3")
    return offset + 1, offset + len(cdr3)


def row_aa_sequence(row: dict) -> str:
    return norm(
        row.get("sequence_v_aa_germline", "")
        or row.get("sequence_", "")
        or row.get("sequence", "")
    )


def find_modal_parent_cdr3(
    shm_rows: list[dict],
    *,
    v_gene: str | None,
    min_count: int,
) -> str | None:
    totals: dict[str, int] = defaultdict(int)
    for row in shm_rows:
        if not has_kabat_columns(row):
            continue
        cnt = to_int(row.get("seq_count", 0))
        if cnt <= min_count:
            continue
        if v_gene and str(row.get("v_gene", "")).strip() != v_gene:
            continue
        cdr3 = norm(row.get("kabat_CDR3", ""))
        if cdr3:
            totals[cdr3] += cnt
    if not totals:
        return None
    return max(totals, key=totals.get)


def infer_dominant_v_gene(shm_rows: list[dict], min_count: int) -> str | None:
    totals: dict[str, int] = defaultdict(int)
    for row in shm_rows:
        if not has_kabat_columns(row):
            continue
        cnt = to_int(row.get("seq_count", 0))
        if cnt <= min_count:
            continue
        v = str(row.get("v_gene", "")).strip()
        if v:
            totals[v] += cnt
    if not totals:
        return None
    return max(totals, key=totals.get)


def find_parent_reference_row(
    shm_rows: list[dict],
    *,
    origin_aa: str | None,
    v_gene: str | None,
    min_count: int,
) -> tuple[dict, int, str, int]:
    """从 SHM 表 Kabat 注释列识别母本参考行。"""
    candidates: list[tuple[int, int, dict, str]] = []

    if origin_aa:
        for file_line, row in enumerate(shm_rows, start=2):
            if not has_kabat_columns(row):
                continue
            cnt = to_int(row.get("seq_count", 0))
            if cnt <= min_count:
                continue
            if v_gene and str(row.get("v_gene", "")).strip() != v_gene:
                continue

            aa = row_aa_sequence(row)
            stitched = stitch_kabat_sequence(row)
            ref_aa = aa or stitched
            if not ref_aa:
                continue
            if ref_aa != origin_aa and stitched != origin_aa:
                continue

            candidates.append((cnt, file_line, row, ref_aa if ref_aa == origin_aa else stitched))

        if not candidates:
            target_v_gene = v_gene or infer_dominant_v_gene(shm_rows, min_count)
            parent_cdr3 = find_modal_parent_cdr3(
                shm_rows, v_gene=target_v_gene, min_count=min_count
            )
            if parent_cdr3 and parent_cdr3 in origin_aa:
                for file_line, row in enumerate(shm_rows, start=2):
                    if not has_kabat_columns(row):
                        continue
                    cnt = to_int(row.get("seq_count", 0))
                    if cnt <= min_count:
                        continue
                    if target_v_gene and str(row.get("v_gene", "")).strip() != target_v_gene:
                        continue
                    if norm(row.get("kabat_CDR3", "")) != parent_cdr3:
                        continue
                    aa = row_aa_sequence(row) or stitch_kabat_sequence(row)
                    if aa:
                        candidates.append((cnt, file_line, row, aa))
    else:
        target_v_gene = v_gene or infer_dominant_v_gene(shm_rows, min_count)
        parent_cdr3 = find_modal_parent_cdr3(
            shm_rows, v_gene=target_v_gene, min_count=min_count
        )
        if parent_cdr3:
            for file_line, row in enumerate(shm_rows, start=2):
                if not has_kabat_columns(row):
                    continue
                cnt = to_int(row.get("seq_count", 0))
                if cnt <= min_count:
                    continue
                if target_v_gene and str(row.get("v_gene", "")).strip() != target_v_gene:
                    continue
                if norm(row.get("kabat_CDR3", "")) != parent_cdr3:
                    continue
                aa = row_aa_sequence(row) or stitch_kabat_sequence(row)
                if aa:
                    candidates.append((cnt, file_line, row, aa))

    if not candidates:
        hint = "请确认 SHM 表含 kabat_FR1…kabat_FR4 列"
        if origin_aa:
            hint += "，且母本 CDR3 能在 origin.fasta 中找到"
        if v_gene:
            hint += f"，v_gene={v_gene}"
        raise ValueError(f"未找到母本参考行（{hint}）")

    if origin_aa:
        parent_cdr3_hint = norm(candidates[0][2].get("kabat_CDR3", ""))
        if parent_cdr3_hint and parent_cdr3_hint not in origin_aa:
            raise ValueError("origin.fasta 中未包含识别出的母本 CDR3，请检查序列或改由 SHM 表自动识别")

    candidates.sort(key=lambda x: (-x[0], x[1]))
    cnt, file_line, row, ref_aa = candidates[0]
    return row, file_line, ref_aa, cnt


def parse_iggm_muts(text: str) -> list[Mut]:
    muts = []
    for block in re.split(r"[;|]", str(text)):
        m = re.search(r"Pos:\s*(\d+),\s*([A-Z\*])\s*->\s*([A-Z\*])", block, re.I)
        if m:
            muts.append(Mut(int(m.group(1)), m.group(2).upper(), m.group(3).upper()))
    return muts


def diff_muts(ref: str, seq: str) -> list[Mut]:
    if not ref or not seq or len(ref) != len(seq):
        return []
    return [Mut(i + 1, ref[i], seq[i]) for i in range(len(ref)) if ref[i] != seq[i]]


def fmt_muts(muts: list[Mut]) -> str:
    return "; ".join(f"{m.pos}{m.wt}→{m.mut}" for m in muts) if muts else ""


def write_csv(path: str | Path, rows: list[dict], fields: list[str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def run_iggm_shm_match(
    *,
    iggm_table: str | Path,
    shm_table: str | Path,
    out_dir: str | Path,
    params: ShmMatchParams | None = None,
    origin_fasta: str | Path | None = None,
) -> dict:
    params = params or ShmMatchParams()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    origin_aa = None
    if origin_fasta:
        origin_aa = norm(load_fasta_chain(origin_fasta, params.chain_id))

    shm_all = read_table(shm_table)
    ref_row, ref_row_no, ref_aa, ref_count = find_parent_reference_row(
        shm_all,
        origin_aa=origin_aa,
        v_gene=params.v_gene,
        min_count=params.min_seq_count,
    )

    parent_cdr3 = norm(ref_row.get("kabat_CDR3", ""))
    parent_v_gene = str(ref_row.get("v_gene", "")).strip() or (params.v_gene or "")
    cdr3_start, cdr3_end = cdr3_bounds_from_kabat_row(ref_row)

    if origin_aa:
        parent_cdr3_in_origin = parent_cdr3 in origin_aa
        if not parent_cdr3_in_origin:
            raise ValueError("origin.fasta 中未包含识别出的母本 CDR3")

    shm_filtered = []
    shm_by_cdr3: dict[str, list[dict]] = {}

    for file_line, row in enumerate(shm_all, start=2):
        if str(row.get("v_gene", "")).strip() != parent_v_gene:
            continue
        cnt = to_int(row.get("seq_count", 0))
        if cnt <= params.min_seq_count:
            continue
        cdr3 = norm(row.get("kabat_CDR3", ""))
        aa = row_aa_sequence(row)
        nt = norm(row.get("sequence", "") or row.get("nucleotide_sequence", ""))
        if not cdr3 or not aa:
            continue

        item = {
            "file_line": file_line,
            "sequence_id": row.get("sequence_id", ""),
            "seq_count": cnt,
            "v_gene": row.get("v_gene", ""),
            "j_gene": row.get("j_gene", ""),
            "d_call": row.get("d_call", ""),
            "kabat_CDR3": cdr3,
            "aa_sequence": aa,
            "nucleotide_sequence": nt,
            "PI": row.get("PI", ""),
        }
        shm_filtered.append(item)
        shm_by_cdr3.setdefault(cdr3, []).append(item)

    iggm_rows = read_table(iggm_table)
    matched = []

    for ig in iggm_rows:
        iggm_cdr3 = norm(ig.get("cdr3_seq", ""))
        if not iggm_cdr3:
            continue
        hits = shm_by_cdr3.get(iggm_cdr3, [])
        if not hits:
            continue

        iggm_muts = parse_iggm_muts(ig.get("cdr3_mutations", ""))
        iggm_mut_str = fmt_muts(iggm_muts) or ig.get("cdr3_mutation_labels", "")

        for h in sorted(hits, key=lambda x: -x["seq_count"]):
            all_muts = diff_muts(ref_aa, h["aa_sequence"])
            cdr3_muts = [m for m in all_muts if cdr3_start <= m.pos <= cdr3_end]
            extra_muts = [m for m in all_muts if not (cdr3_start <= m.pos <= cdr3_end)]

            matched.append({
                "iggm_variant_id": ig.get("variant_id", ""),
                "iggm_mutation_count": ig.get("mutation_count", ""),
                "iggm_frequency": ig.get("frequency", ""),
                "iggm_source": ig.get("source", ""),
                "iggm_cdr3": iggm_cdr3,
                "iggm_cdr3_mutations": ig.get("cdr3_mutations", ""),
                "iggm_cdr3_mutation_sites": iggm_mut_str,
                "shm_file_line": h["file_line"],
                "shm_sequence_id": h["sequence_id"],
                "seq_count": h["seq_count"],
                "v_gene": h["v_gene"],
                "j_gene": h["j_gene"],
                "d_call": h["d_call"],
                "shm_kabat_CDR3": h["kabat_CDR3"],
                "cdr3_mutation_sites_in_shm_row": fmt_muts(cdr3_muts),
                "extra_mutation_sites_in_shm_row": fmt_muts(extra_muts),
                "all_mutation_sites_vs_parent": fmt_muts(all_muts) or "无",
                "n_cdr3_mutations": len(cdr3_muts),
                "n_extra_mutations": len(extra_muts),
                "has_extra_shm": "YES" if extra_muts else "NO",
                "nucleotide_sequence": h["nucleotide_sequence"],
                "aa_sequence": h["aa_sequence"],
                "PI": h["PI"],
                "parent_reference_file_line": ref_row_no,
                "parent_v_gene": parent_v_gene,
            })

    matched.sort(key=lambda x: (-float(x["iggm_frequency"] or 0), -x["seq_count"], x["iggm_variant_id"]))

    matched_path = out_dir / "iggm_cdr3_shm_matched.csv"
    write_csv(matched_path, matched, MATCHED_FIELDS)

    unmatched = []
    for ig in iggm_rows:
        c = norm(ig.get("cdr3_seq", ""))
        if c and c not in shm_by_cdr3:
            unmatched.append(ig)

    unmatched_path = out_dir / "iggm_cdr3_not_in_shm_filtered.csv"
    write_csv(
        unmatched_path,
        [{
            "variant_id": ig.get("variant_id", ""),
            "mutation_count": ig.get("mutation_count", ""),
            "frequency": ig.get("frequency", ""),
            "source": ig.get("source", ""),
            "cdr3_seq": ig.get("cdr3_seq", ""),
            "cdr3_mutations": ig.get("cdr3_mutations", ""),
            "cdr3_mutation_labels": ig.get("cdr3_mutation_labels", ""),
        } for ig in unmatched],
        ["variant_id", "mutation_count", "frequency", "source", "cdr3_seq", "cdr3_mutations", "cdr3_mutation_labels"],
    )

    summary_path = out_dir / "iggm_cdr3_shm_match_summary.txt"
    summary_path.write_text(
        "\n".join([
            f"母本 CDR3: {parent_cdr3}",
            f"母本 v_gene: {parent_v_gene}",
            f"母本参考行: {ref_row_no} (count={ref_count})",
            f"CDR3 边界 (Kabat 区段): {cdr3_start}-{cdr3_end}",
            f"SHM 预筛选: v_gene={parent_v_gene}, seq_count>{params.min_seq_count}",
            f"SHM 筛选后行数: {len(shm_filtered)}",
            f"IgGM 变体总数: {len(iggm_rows)}",
            f"匹配输出行数: {len(matched)}",
            f"匹配到的 IgGM CDR3 种类: {len({m['iggm_cdr3'] for m in matched})}",
            f"未匹配 IgGM 变体: {len(unmatched)}",
        ]),
        encoding="utf-8",
    )

    return {
        "parent_cdr3": parent_cdr3,
        "parent_v_gene": parent_v_gene,
        "cdr3_region": f"{cdr3_start}-{cdr3_end}",
        "shm_filtered": len(shm_filtered),
        "matched_count": len(matched),
        "matched_cdr3_kinds": len({m["iggm_cdr3"] for m in matched}),
        "unmatched_iggm_count": len(unmatched),
        "matched_csv": str(matched_path),
        "unmatched_csv": str(unmatched_path),
        "summary_txt": str(summary_path),
        "out_dir": str(out_dir),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iggm_table", required=True)
    parser.add_argument("--shm_table", required=True)
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--origin_fasta", default=None, help="可选，用于校验/定位母本参考行")
    parser.add_argument("--min_seq_count", type=int, default=30)
    parser.add_argument("--v_gene", default=None)
    parser.add_argument("--chain_id", default="H")
    args = parser.parse_args()

    result = run_iggm_shm_match(
        iggm_table=args.iggm_table,
        shm_table=args.shm_table,
        out_dir=args.out_dir,
        origin_fasta=args.origin_fasta,
        params=ShmMatchParams(
            min_seq_count=args.min_seq_count,
            v_gene=args.v_gene,
            chain_id=args.chain_id,
        ),
    )
    print("=== IgGM ↔ SHM 匹配完成 ===")
    for k, v in result.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
