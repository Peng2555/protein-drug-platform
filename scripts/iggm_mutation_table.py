#!/usr/bin/env python3
"""整理亲和力成熟突变表：支持 0~3 个突变（含单点组合设计）"""

from __future__ import annotations

import argparse
import csv
import itertools
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Mutation:
    pos: int
    wt: str
    mut: str

    def label(self) -> str:
        return f"{self.pos}{self.wt}{self.mut}"

    def detail(self) -> str:
        return f"Pos: {self.pos}, {self.wt} -> {self.mut}"


def parse_fasta(path: str | Path) -> tuple[list[str], list[str]]:
    seqs, ids = [], []
    cur_id, cur_seq = None, []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if cur_id is not None:
                    seqs.append("".join(cur_seq))
                    ids.append(cur_id)
                cur_id, cur_seq = line[1:].split()[0], []
            else:
                cur_seq.append(line)
    if cur_id is not None:
        seqs.append("".join(cur_seq))
        ids.append(cur_id)
    return seqs, ids


def load_parent_sequence(origin_fasta: str | Path, chain_id: str = "H") -> str:
    seqs, ids = parse_fasta(origin_fasta)
    if chain_id in ids:
        return seqs[ids.index(chain_id)]
    return seqs[0]


def detect_cdr3_region(mask_fasta: str | Path, chain_id: str = "H") -> tuple[int, int, str]:
    seqs, ids = parse_fasta(mask_fasta)
    mask_seq = seqs[ids.index(chain_id)] if chain_id in ids else seqs[0]
    x_idx = [i for i, aa in enumerate(mask_seq) if aa == "X"]
    if not x_idx:
        raise ValueError(f"{mask_fasta} 中未找到 X 标记的 CDR3 区域")
    start = x_idx[0] + 1
    end = x_idx[-1] + 1
    return start, end, mask_seq[x_idx[0] : x_idx[-1] + 1].replace("X", "?")


def extract_cdr3(seq: str, cdr3_start: int, cdr3_end: int) -> str:
    return seq[cdr3_start - 1 : cdr3_end]


def cdr3_mutation_fields(
    parent: str,
    mutant: str,
    muts: list[Mutation],
    cdr3_start: int,
    cdr3_end: int,
) -> dict:
    parent_cdr3 = extract_cdr3(parent, cdr3_start, cdr3_end)
    mutant_cdr3 = extract_cdr3(mutant, cdr3_start, cdr3_end)
    cdr3_muts = [m for m in muts if cdr3_start <= m.pos <= cdr3_end]
    return {
        "cdr3_parent": parent_cdr3,
        "cdr3_seq": mutant_cdr3,
        "cdr3_mutation_count": len(cdr3_muts),
        "cdr3_mutations": "; ".join(m.detail() for m in cdr3_muts),
        "cdr3_mutation_labels": "|".join(m.label() for m in cdr3_muts),
        "cdr3_positions": f"{cdr3_start}-{cdr3_end}",
    }


def diff_mutations(parent: str, mutant: str) -> list[Mutation]:
    n = min(len(parent), len(mutant))
    muts = []
    for i in range(n):
        if parent[i] != mutant[i]:
            muts.append(Mutation(pos=i + 1, wt=parent[i], mut=mutant[i]))
    if len(parent) != len(mutant):
        raise ValueError("parent 与 mutant 序列长度不一致")
    return muts


def apply_mutations(parent: str, muts: Iterable[Mutation]) -> str:
    seq = list(parent)
    used = set()
    for m in muts:
        if m.pos in used:
            raise ValueError(f"重复位点: {m.pos}")
        used.add(m.pos)
        idx = m.pos - 1
        if seq[idx] != m.wt:
            raise ValueError(f"位点 {m.pos} 当前为 {seq[idx]}，与预期野生型 {m.wt} 不一致")
        seq[idx] = m.mut
    return "".join(seq)


def parse_fasta_dir(fasta_dir: str | Path) -> Counter[str]:
    counter: Counter[str] = Counter()
    for fname in os.listdir(fasta_dir):
        if not fname.endswith(".fasta"):
            continue
        seqs, _ = parse_fasta(Path(fasta_dir) / fname)
        if seqs:
            counter[seqs[0]] += 1
    return counter


def build_single_mutation_pool(parent: str, seq_counter: Counter[str], min_freq: int) -> list[dict]:
    pool = []
    seen = set()
    for seq, freq in seq_counter.most_common():
        muts = diff_mutations(parent, seq)
        if len(muts) != 1:
            continue
        key = (muts[0].pos, muts[0].wt, muts[0].mut)
        if key in seen:
            continue
        seen.add(key)
        if freq < min_freq:
            continue
        pool.append({
            "mutation": muts[0],
            "frequency": freq,
            "sequence": seq,
            "source": "observed",
        })
    pool.sort(key=lambda x: (-x["frequency"], x["mutation"].pos))
    return pool


def make_variant_row(
    variant_id: str,
    parent: str,
    muts: list[Mutation],
    frequency: int,
    source: str,
    cdr3_start: int,
    cdr3_end: int,
    note: str = "",
) -> dict:
    seq = apply_mutations(parent, muts) if muts else parent
    row = {
        "variant_id": variant_id,
        "mutation_count": len(muts),
        "frequency": frequency,
        "source": source,
        "mutation_labels": "|".join(m.label() for m in muts),
        "mutation_details": "; ".join(m.detail() for m in muts),
        "mutation_positions": "|".join(str(m.pos) for m in muts),
        "antibody_seq_h": seq,
        "note": note,
    }
    row.update(cdr3_mutation_fields(parent, seq, muts, cdr3_start, cdr3_end))
    return row


def build_combination_variants(
    parent: str,
    single_pool: list[dict],
    mutation_count: int,
    max_variants: int,
    cdr3_start: int,
    cdr3_end: int,
) -> list[dict]:
    mut_list = [item["mutation"] for item in single_pool]
    rows = []
    for combo in itertools.combinations(mut_list, mutation_count):
        positions = [m.pos for m in combo]
        if len(set(positions)) != len(positions):
            continue
        variant_id = f"combo{mutation_count}_{'_'.join(m.label() for m in combo)}"
        avg_freq = round(
            sum(next(x["frequency"] for x in single_pool if x["mutation"] == m) for m in combo)
            / len(combo),
            1,
        )
        rows.append(
            make_variant_row(
                variant_id=variant_id,
                parent=parent,
                muts=list(combo),
                frequency=avg_freq,
                source="combined",
                cdr3_start=cdr3_start,
                cdr3_end=cdr3_end,
                note=f"由 {mutation_count} 个单点突变组合生成",
            )
        )
        if len(rows) >= max_variants:
            break
    return rows


CSV_FIELDS = [
    "variant_id", "mutation_count", "frequency", "source",
    "mutation_labels", "mutation_details", "mutation_positions",
    "cdr3_positions", "cdr3_parent", "cdr3_seq",
    "cdr3_mutation_count", "cdr3_mutation_labels", "cdr3_mutations",
    "antibody_seq_h", "note",
]

CDR3_FIELDS = [
    "variant_id", "mutation_count", "frequency", "source",
    "cdr3_positions", "cdr3_parent", "cdr3_seq",
    "cdr3_mutation_count", "cdr3_mutation_labels", "cdr3_mutations",
    "antibody_seq_h",
]


def write_csv(path: str | Path, rows: list[dict], fields: list[str] | None = None) -> None:
    fields = fields or CSV_FIELDS
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_cdr3_fasta(path: str | Path, rows: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(f">{row['variant_id']} freq={row['frequency']} mut={row['cdr3_mutation_count']}\n")
            f.write(f"{row['cdr3_seq']}\n")


def build_mutation_table(
    *,
    fasta_dir: str | Path,
    origin_fasta: str | Path,
    mask_fasta: str | Path,
    out_dir: str | Path,
    chain_id: str = "H",
    min_freq: int = 1,
    max_combo2: int = 200,
    max_combo3: int = 200,
    include_parent: bool = False,
) -> dict:
    """从 IgGM 成熟 FASTA 构建 1~3 点突变表，返回输出路径与统计。"""
    fasta_dir = Path(fasta_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    parent = load_parent_sequence(origin_fasta, chain_id=chain_id)
    cdr3_start, cdr3_end, _ = detect_cdr3_region(mask_fasta, chain_id=chain_id)
    seq_counter = parse_fasta_dir(fasta_dir)
    single_pool = build_single_mutation_pool(parent, seq_counter, min_freq)

    all_rows: list[dict] = []
    if include_parent:
        all_rows.append(
            make_variant_row(
                variant_id="parent",
                parent=parent,
                muts=[],
                frequency=seq_counter.get(parent, 0),
                source="observed",
                cdr3_start=cdr3_start,
                cdr3_end=cdr3_end,
                note="母本序列",
            )
        )

    rows_1 = []
    for i, item in enumerate(single_pool, 1):
        m = item["mutation"]
        row = make_variant_row(
            variant_id=f"mut1_{i:03d}_{m.label()}",
            parent=parent,
            muts=[m],
            frequency=item["frequency"],
            source="observed",
            cdr3_start=cdr3_start,
            cdr3_end=cdr3_end,
        )
        rows_1.append(row)
        all_rows.append(row)

    rows_2 = build_combination_variants(
        parent, single_pool, mutation_count=2, max_variants=max_combo2,
        cdr3_start=cdr3_start, cdr3_end=cdr3_end,
    )
    rows_3 = build_combination_variants(
        parent, single_pool, mutation_count=3, max_variants=max_combo3,
        cdr3_start=cdr3_start, cdr3_end=cdr3_end,
    )
    all_rows.extend(rows_2)
    all_rows.extend(rows_3)

    cdr3_csv = out_dir / "cdr3_all_1to3.csv"
    write_csv(out_dir / "mutations_all_1to3.csv", all_rows)
    write_csv(out_dir / "mutations_1pt.csv", rows_1)
    write_csv(out_dir / "mutations_2pt.csv", rows_2)
    write_csv(out_dir / "mutations_3pt.csv", rows_3)
    write_csv(cdr3_csv, all_rows, fields=CDR3_FIELDS)
    write_csv(out_dir / "cdr3_1pt.csv", rows_1, fields=CDR3_FIELDS)
    write_csv(out_dir / "cdr3_2pt.csv", rows_2, fields=CDR3_FIELDS)
    write_csv(out_dir / "cdr3_3pt.csv", rows_3, fields=CDR3_FIELDS)
    write_cdr3_fasta(out_dir / "cdr3_all_1to3.fasta", all_rows)

    return {
        "cdr3_csv": str(cdr3_csv),
        "out_dir": str(out_dir),
        "variant_count": len(all_rows),
        "single_count": len(rows_1),
        "combo2_count": len(rows_2),
        "combo3_count": len(rows_3),
        "cdr3_region": f"{cdr3_start}-{cdr3_end}",
    }


def main():
    parser = argparse.ArgumentParser(description="整理 1~3 点突变表")
    parser.add_argument("--fasta_dir", required=True)
    parser.add_argument("--origin_fasta", required=True)
    parser.add_argument("--mask_fasta", required=True)
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--chain_id", default="H")
    parser.add_argument("--min_freq", type=int, default=1)
    parser.add_argument("--max_combo2", type=int, default=200)
    parser.add_argument("--max_combo3", type=int, default=200)
    parser.add_argument("--include_parent", action="store_true")
    args = parser.parse_args()

    result = build_mutation_table(
        fasta_dir=args.fasta_dir,
        origin_fasta=args.origin_fasta,
        mask_fasta=args.mask_fasta,
        out_dir=args.out_dir,
        chain_id=args.chain_id,
        min_freq=args.min_freq,
        max_combo2=args.max_combo2,
        max_combo3=args.max_combo3,
        include_parent=args.include_parent,
    )
    print("=== 突变表已生成 ===")
    for k, v in result.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
