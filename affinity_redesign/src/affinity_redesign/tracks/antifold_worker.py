#!/usr/bin/env python3
"""结构轨 worker：AntiFold（或 ESM-IF1）复合物 inverse folding 打分。

在含 antifold 的解释器中运行（默认 maxwell env）。

用法:
  ANTIFOLD_PYTHON -m affinity_redesign.tracks.antifold_worker \\
    --pdb complex.pdb --sequences seq.fasta --candidates candidates.csv \\
    --out-dir round1/structure --heavy H --light L --antigen A
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

STANDARD_AA = list("ACDEFGHIKLMNPQRSTVWY")

# AntiFold/biotite 只认标准 20 氨基酸；结构文件常见非标残基映射
_NONSTD_TO_STD = {
    "PCA": "GLN",  # pyroglutamate（N 端 Gln 环化）
    "MSE": "MET",
    "HSD": "HIS",
    "HSE": "HIS",
    "HSP": "HIS",
    "HID": "HIS",
    "HIE": "HIS",
    "HIP": "HIS",
    "SEP": "SER",
    "TPO": "THR",
    "PTR": "TYR",
    "CSO": "CYS",
    "CSD": "CYS",
    "MLY": "LYS",
    "MLE": "LEU",
    "DAL": "ALA",
}


def sanitize_pdb_for_antifold(src: Path, dest: Path) -> dict:
    """将非标残基改为标准三字母；蛋白 HETATM 改为 ATOM。返回替换统计。"""
    stats: dict[str, int] = defaultdict(int)
    lines_out: list[str] = []
    for line in src.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith(("ATOM", "HETATM")) and len(line) >= 20:
            res = line[17:20].strip()
            mapped = _NONSTD_TO_STD.get(res)
            if mapped and mapped != res:
                stats[f"{res}->{mapped}"] += 1
                line = line[:17] + f"{mapped:>3}" + line[20:]
                res = mapped
            # 标准残基的 HETATM（如 PCA→GLN）改为 ATOM，便于 AntiFold 读取
            if line.startswith("HETATM") and res in {
                "ALA",
                "CYS",
                "ASP",
                "GLU",
                "PHE",
                "GLY",
                "HIS",
                "ILE",
                "LYS",
                "LEU",
                "MET",
                "ASN",
                "PRO",
                "GLN",
                "ARG",
                "SER",
                "THR",
                "VAL",
                "TRP",
                "TYR",
            }:
                line = "ATOM  " + line[6:]
                stats["HETATM->ATOM"] += 1
        lines_out.append(line)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines_out) + "\n", encoding="utf-8")
    return dict(stats)


def parse_fasta(text: str) -> dict[str, str]:
    seqs: dict[str, str] = {}
    cur: str | None = None
    chunks: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if cur is not None:
                seqs[cur] = "".join(chunks).upper().replace(" ", "")
            cur = line[1:].split()[0]
            chunks = []
        else:
            chunks.append(line)
    if cur is not None:
        seqs[cur] = "".join(chunks).upper().replace(" ", "")
    return seqs


def select_top_per_chain(
    rows: list[dict],
    *,
    top_n: int,
    maxrep: int = 0,
    score_key: str = "dll",
) -> list[dict]:
    by_chain: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_chain[r["chain"]].append(r)

    selected: list[dict] = []
    for _chain, items in by_chain.items():
        passed = [x for x in items if x.get("pass") and x.get(score_key) != ""]
        passed = sorted(
            passed,
            key=lambda x: (-float(x[score_key]), int(x["position"]), x["mut"]),
        )
        pos_count: dict[int, int] = defaultdict(int)
        kept = 0
        for item in passed:
            pos = int(item["position"])
            if maxrep > 0 and pos_count[pos] >= maxrep:
                continue
            if maxrep > 0:
                pos_count[pos] += 1
            kept += 1
            selected.append(item)
            if top_n > 0 and kept >= top_n:
                break
    return selected


def _align_pdb_seq_to_fasta(pdb_seq: str, fasta_seq: str) -> list[int | None]:
    """返回 pdb 每个残基对应的 1-based FASTA 位点；无法对齐则为 None。"""
    if not pdb_seq:
        return []
    idx = fasta_seq.find(pdb_seq)
    if idx >= 0:
        return [idx + i + 1 for i in range(len(pdb_seq))]

    # 宽松：允许 PDB 是 FASTA 的子串缺失两端
    mapping: list[int | None] = [None] * len(pdb_seq)
    fi = 0
    for pi, aa in enumerate(pdb_seq):
        while fi < len(fasta_seq) and fasta_seq[fi] != aa:
            fi += 1
        if fi >= len(fasta_seq):
            break
        mapping[pi] = fi + 1
        fi += 1
    return mapping


def logits_df_to_score_table(
    df,
    fasta_seqs: dict[str, str],
    binder_chains: set[str],
) -> dict[str, dict[tuple[int, str], float]]:
    """{(chain): {(1-based_pos, mut_aa): dll}}，dll = logit(mut)-logit(wt)。

    AntiFold 返回列名为 pdb_res（原始残基）；导出 CSV 有时写作 aa_orig。
    """
    res_col = "pdb_res" if "pdb_res" in df.columns else "aa_orig"
    if res_col not in df.columns:
        raise KeyError(f"logits 表缺少残基列，列={list(df.columns)}")

    table: dict[str, dict[tuple[int, str], float]] = {c: {} for c in binder_chains}
    for chain in binder_chains:
        sub = df[df["pdb_chain"].astype(str) == str(chain)].copy()
        if sub.empty:
            continue
        # 保持 AntiFold 输出顺序（沿链的残基顺序）
        sub = sub.reset_index(drop=True)
        pdb_seq = "".join(sub[res_col].astype(str).tolist())
        fasta = fasta_seqs.get(chain)
        if not fasta:
            raise ValueError(f"FASTA 缺少 binder 链 {chain}")
        pos_map = _align_pdb_seq_to_fasta(pdb_seq, fasta)
        matched = sum(1 for p in pos_map if p is not None)
        if matched < max(1, int(0.8 * len(pdb_seq))):
            raise ValueError(
                f"链 {chain} PDB 序列与 FASTA 对齐失败 "
                f"(matched={matched}/{len(pdb_seq)}; pdb={pdb_seq[:20]}... fasta={fasta[:20]}...)"
            )

        for i, row in sub.iterrows():
            seq_pos = pos_map[i]
            if seq_pos is None:
                continue
            wt = str(row[res_col])
            if seq_pos < 1 or seq_pos > len(fasta):
                continue
            if fasta[seq_pos - 1] != wt:
                continue
            if wt not in STANDARD_AA:
                continue
            wt_logit = float(row[wt])
            for mut in STANDARD_AA:
                if mut == wt:
                    continue
                table[chain][(seq_pos, mut)] = float(row[mut]) - wt_logit
    return table


def run_antifold_logits(
    *,
    pdb_path: Path,
    heavy: str,
    light: str | None,
    antigen: str | None,
    antifold_root: Path,
    esm_if1_mode: bool,
    out_dir: Path,
):
    """调用 AntiFold API，返回 logits DataFrame，并写出 raw CSV。"""
    antifold_root = antifold_root.resolve()
    if str(antifold_root) not in sys.path:
        sys.path.insert(0, str(antifold_root))

    import pandas as pd
    import antifold.main as af_main

    checkpoint = "ESM-IF1" if esm_if1_mode else ""
    model = af_main.load_model(checkpoint)

    pdb_path = pdb_path.resolve()
    work = Path(tempfile.mkdtemp(prefix="antifold_pdb_"))
    try:
        local_pdb = work / pdb_path.name
        sanit_stats = sanitize_pdb_for_antifold(pdb_path, local_pdb)
        if sanit_stats:
            print(f"[structure] sanitized PDB: {sanit_stats}", flush=True)
        stem = local_pdb.stem

        # VHH / nanobody: Lchain 必须是 NaN，不能传 ""——否则 AntiFold 会去读空链名并报
        # ValueError: Chain  not found in input file
        row: dict = {"pdb": stem, "Hchain": heavy, "Lchain": light if light else None}
        if antigen:
            row["Agchain"] = antigen
        pdbs_csv = pd.DataFrame([row])

        custom = bool(antigen) or (light is None) or esm_if1_mode
        df_list = af_main.get_pdbs_logits(
            model=model,
            pdbs_csv_or_dataframe=pdbs_csv,
            pdb_dir=str(work),
            out_dir=str(out_dir / "antifold_raw"),
            custom_chain_mode=custom,
            save_flag=True,
        )
        if not df_list:
            raise RuntimeError("AntiFold 未返回 logits")
        return df_list[0]
    finally:
        shutil.rmtree(work, ignore_errors=True)
        del model


def run(
    *,
    pdb_path: Path,
    sequences_path: Path,
    candidates_path: Path,
    out_dir: Path,
    heavy: str,
    light: str | None,
    antigen: str | None,
    antifold_root: Path,
    esm_if1_mode: bool,
    dll_threshold: float,
    top_per_chain: int,
    maxrep: int,
) -> dict:
    seqs = parse_fasta(sequences_path.read_text(encoding="utf-8"))
    candidates: list[dict] = []
    with candidates_path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            candidates.append(row)

    binder_chains = sorted({c["chain"] for c in candidates})
    print(
        f"[structure] engine={'esm_if1' if esm_if1_mode else 'antifold'} "
        f"pdb={pdb_path} chains H={heavy} L={light} Ag={antigen}",
        flush=True,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    df = run_antifold_logits(
        pdb_path=pdb_path,
        heavy=heavy,
        light=light,
        antigen=antigen,
        antifold_root=antifold_root,
        esm_if1_mode=esm_if1_mode,
        out_dir=out_dir,
    )

    raw_csv = out_dir / "logits_raw.csv"
    df.to_csv(raw_csv, index=False, float_format="%.6f")

    score_table = logits_df_to_score_table(df, seqs, set(binder_chains))

    scored_rows: list[dict] = []
    n_scored = 0
    for cand in candidates:
        chain = cand["chain"]
        pos = int(cand["position"])
        mut = cand["mut"]
        wt = cand["wt"]
        dll = score_table.get(chain, {}).get((pos, mut))
        if dll is None:
            row = {
                "chain": chain,
                "position": pos,
                "wt": wt,
                "mut": mut,
                "region": cand.get("region", ""),
                "label": cand.get("label") or f"{wt}{pos}{mut}",
                "domain": cand.get("domain", ""),
                "dll": "",
                "dll_threshold": dll_threshold,
                "pass": False,
                "in_structure": False,
            }
        else:
            n_scored += 1
            row = {
                "chain": chain,
                "position": pos,
                "wt": wt,
                "mut": mut,
                "region": cand.get("region", ""),
                "label": cand.get("label") or f"{wt}{pos}{mut}",
                "domain": cand.get("domain", ""),
                "dll": round(float(dll), 6),
                "dll_threshold": dll_threshold,
                "pass": float(dll) > dll_threshold,
                "in_structure": True,
            }
        scored_rows.append(row)

    score_fields = [
        "chain",
        "position",
        "wt",
        "mut",
        "region",
        "label",
        "domain",
        "dll",
        "dll_threshold",
        "pass",
        "in_structure",
    ]
    scores_path = out_dir / "scores.csv"
    with scores_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=score_fields)
        w.writeheader()
        for row in scored_rows:
            w.writerow(row)

    top_rows = select_top_per_chain(
        scored_rows, top_n=top_per_chain, maxrep=maxrep, score_key="dll"
    )
    top_path = out_dir / "top_per_chain.csv"
    with top_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=score_fields)
        w.writeheader()
        for row in top_rows:
            w.writerow(row)

    summary = {
        "status": "ok",
        "engine": "esm_if1" if esm_if1_mode else "antifold",
        "pdb": str(pdb_path),
        "heavy": heavy,
        "light": light,
        "antigen": antigen,
        "n_candidates": len(candidates),
        "n_scored": n_scored,
        "n_pass": sum(1 for r in scored_rows if r["pass"]),
        "n_top": len(top_rows),
        "top_per_chain": top_per_chain,
        "dll_threshold": dll_threshold,
        "scores_csv": str(scores_path),
        "top_csv": str(top_path),
        "logits_csv": str(raw_csv),
        "top_labels": [r["label"] for r in top_rows],
    }
    (out_dir / "result.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "summary": summary}, ensure_ascii=False))
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description="AntiFold / ESM-IF1 structure scoring worker")
    p.add_argument("--pdb", type=Path, required=True)
    p.add_argument("--sequences", type=Path, required=True)
    p.add_argument("--candidates", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--heavy", type=str, required=True)
    p.add_argument("--light", type=str, default="")
    p.add_argument("--antigen", type=str, default="")
    p.add_argument("--antifold-root", type=Path, required=True)
    p.add_argument("--esm-if1-mode", action="store_true")
    p.add_argument("--dll-threshold", type=float, default=0.0)
    p.add_argument("--top-per-chain", type=int, default=0, help="每链最多保留条数，0=保留全部 dll>0")
    p.add_argument("--maxrep", type=int, default=0, help="同位点最多保留条数，0=不限制")
    p.add_argument("--torch-home", type=str, default="")
    args = p.parse_args()

    if args.torch_home:
        os.environ["TORCH_HOME"] = args.torch_home

    run(
        pdb_path=args.pdb,
        sequences_path=args.sequences,
        candidates_path=args.candidates,
        out_dir=args.out_dir,
        heavy=args.heavy,
        light=args.light or None,
        antigen=args.antigen or None,
        antifold_root=args.antifold_root,
        esm_if1_mode=args.esm_if1_mode,
        dll_threshold=args.dll_threshold,
        top_per_chain=args.top_per_chain,
        maxrep=args.maxrep,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
