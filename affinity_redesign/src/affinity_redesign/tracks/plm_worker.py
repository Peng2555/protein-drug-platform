#!/usr/bin/env python3
"""PLM 打分 worker：在含 fair-esm 的解释器中运行（如 boltz2 env）。

用法:
  ESM_PYTHON -m affinity_redesign.tracks.plm_worker \\
    --sequences seq.fasta --candidates candidates.csv --out-dir round1/plm \\
    --models esm1b,esm1v_ensemble --consensus-k 3 --top-per-chain 10
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import defaultdict
from pathlib import Path

STANDARD_AA = list("ACDEFGHIKLMNPQRSTVWY")

MODEL_LOADERS = {
    "esm1b": "esm1b_t33_650M_UR50S",
    "esm1v_1": "esm1v_t33_650M_UR90S_1",
    "esm1v_2": "esm1v_t33_650M_UR90S_2",
    "esm1v_3": "esm1v_t33_650M_UR90S_3",
    "esm1v_4": "esm1v_t33_650M_UR90S_4",
    "esm1v_5": "esm1v_t33_650M_UR90S_5",
}


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


def expand_models(names: list[str]) -> list[str]:
    out: list[str] = []
    for n in names:
        n = n.strip()
        if n in ("esm1v_ensemble", "esm1v"):
            out.extend([f"esm1v_{i}" for i in range(1, 6)])
        elif n in MODEL_LOADERS:
            out.append(n)
        else:
            raise ValueError(f"未知 PLM 模型: {n}")
    seen: set[str] = set()
    uniq: list[str] = []
    for m in out:
        if m not in seen:
            seen.add(m)
            uniq.append(m)
    return uniq


def load_model(name: str, device: str):
    import torch
    import esm

    loader_name = MODEL_LOADERS[name]
    fn = getattr(esm.pretrained, loader_name)
    model, alphabet = fn()
    model.eval()
    model = model.to(device)
    if device.startswith("cuda"):
        model = model.half()
    return model, alphabet


def wildtype_marginal_dll(model, alphabet, device, sequence: str) -> dict[tuple[int, str], float]:
    """返回 {(1-based pos, mut_aa): dll}，dll = logP(mut)-logP(wt)。"""
    import torch

    batch_converter = alphabet.get_batch_converter()
    _labels, _strs, tokens = batch_converter([("wt", sequence)])
    tokens = tokens.to(device)
    with torch.no_grad():
        if str(device).startswith("cuda"):
            with torch.cuda.amp.autocast(dtype=torch.float16):
                out = model(tokens, repr_layers=[], return_contacts=False)
        else:
            out = model(tokens, repr_layers=[], return_contacts=False)
    logits = out["logits"][0, 1 : 1 + len(sequence)].float()
    log_probs = torch.log_softmax(logits, dim=-1).cpu()

    aa_idx = {aa: alphabet.get_idx(aa) for aa in STANDARD_AA}
    table: dict[tuple[int, str], float] = {}
    for i, wt in enumerate(sequence):
        wt_i = aa_idx.get(wt)
        if wt_i is None:
            continue
        wt_lp = float(log_probs[i, wt_i])
        for mut in STANDARD_AA:
            if mut == wt:
                continue
            table[(i + 1, mut)] = float(log_probs[i, aa_idx[mut]]) - wt_lp
    return table


def select_top_per_chain(
    rows: list[dict],
    *,
    top_n: int,
    maxrep: int = 0,
) -> list[dict]:
    """按 mean_dll 降序保留共识通过项；top_n<=0 表示不截断；maxrep<=0 不限制同位点。"""
    by_chain: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_chain[r["chain"]].append(r)

    selected: list[dict] = []
    for _chain, items in by_chain.items():
        items = sorted(items, key=lambda x: (-float(x["mean_dll"]), x["position"], x["mut"]))
        pos_count: dict[int, int] = defaultdict(int)
        kept = 0
        for item in items:
            if not item.get("consensus_pass"):
                continue
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


def run(
    *,
    sequences_path: Path,
    candidates_path: Path,
    out_dir: Path,
    models: list[str],
    consensus_k: int,
    dll_threshold: float,
    top_per_chain: int,
    maxrep: int,
    device: str,
) -> dict:
    import torch

    seqs = parse_fasta(sequences_path.read_text(encoding="utf-8"))
    candidates: list[dict] = []
    with candidates_path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            candidates.append(row)

    model_names = expand_models(models)
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"

    per_model: dict[str, dict[str, dict[tuple[int, str], float]]] = {}
    binder_chains = sorted({c["chain"] for c in candidates})

    for mname in model_names:
        print(f"[plm] scoring with {mname} on {device}", flush=True)
        model, alphabet = load_model(mname, device)
        per_model[mname] = {}
        for cid in binder_chains:
            if cid not in seqs:
                raise ValueError(f"候选链 {cid} 不在序列 FASTA 中")
            per_model[mname][cid] = wildtype_marginal_dll(
                model, alphabet, device, seqs[cid]
            )
        del model
        if device.startswith("cuda"):
            torch.cuda.empty_cache()

    scored_rows: list[dict] = []
    for cand in candidates:
        chain = cand["chain"]
        pos = int(cand["position"])
        mut = cand["mut"]
        wt = cand["wt"]
        key = (pos, mut)
        dlls: dict[str, float] = {}
        for mname in model_names:
            dlls[mname] = float(per_model[mname][chain].get(key, float("-inf")))
        valid = [v for v in dlls.values() if v != float("-inf")]
        mean_dll = sum(valid) / len(valid) if valid else float("-inf")
        n_pass = sum(1 for v in valid if v > dll_threshold)
        consensus_pass = n_pass >= consensus_k
        row = {
            "chain": chain,
            "position": pos,
            "wt": wt,
            "mut": mut,
            "region": cand.get("region", ""),
            "label": cand.get("label") or f"{wt}{pos}{mut}",
            "domain": cand.get("domain", ""),
            "mean_dll": round(mean_dll, 6) if mean_dll != float("-inf") else "",
            "n_models_pass": n_pass,
            "n_models": len(model_names),
            "consensus_k": consensus_k,
            "dll_threshold": dll_threshold,
            "consensus_pass": consensus_pass,
        }
        for mname, v in dlls.items():
            row[f"dll_{mname}"] = round(v, 6) if v != float("-inf") else ""
        scored_rows.append(row)

    out_dir.mkdir(parents=True, exist_ok=True)
    score_fields = [
        "chain", "position", "wt", "mut", "region", "label", "domain",
        "mean_dll", "n_models_pass", "n_models", "consensus_k", "dll_threshold",
        "consensus_pass",
    ] + [f"dll_{m}" for m in model_names]

    scores_path = out_dir / "scores.csv"
    with scores_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=score_fields, extrasaction="ignore")
        w.writeheader()
        for row in scored_rows:
            w.writerow(row)

    top_rows = select_top_per_chain(scored_rows, top_n=top_per_chain, maxrep=maxrep)
    top_path = out_dir / "top_per_chain.csv"
    with top_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=score_fields, extrasaction="ignore")
        w.writeheader()
        for row in top_rows:
            w.writerow(row)

    summary = {
        "status": "ok",
        "models": model_names,
        "device": device,
        "n_candidates": len(candidates),
        "n_consensus_pass": sum(1 for r in scored_rows if r["consensus_pass"]),
        "n_top": len(top_rows),
        "top_per_chain": top_per_chain,
        "consensus_k": consensus_k,
        "dll_threshold": dll_threshold,
        "scores_csv": str(scores_path),
        "top_csv": str(top_path),
        "top_labels": [r["label"] for r in top_rows],
    }
    (out_dir / "result.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "summary": summary}, ensure_ascii=False))
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description="ESM-1b/1v PLM scoring worker")
    p.add_argument("--sequences", type=Path, required=True)
    p.add_argument("--candidates", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--models", type=str, default="esm1b,esm1v_ensemble")
    p.add_argument("--consensus-k", type=int, default=3)
    p.add_argument("--dll-threshold", type=float, default=0.0)
    p.add_argument("--top-per-chain", type=int, default=0, help="每链最多保留条数，0=保留全部通过项")
    p.add_argument("--maxrep", type=int, default=0, help="同位点最多保留条数，0=不限制")
    p.add_argument("--device", type=str, default="auto")
    p.add_argument("--torch-home", type=str, default="")
    args = p.parse_args()

    if args.torch_home:
        os.environ["TORCH_HOME"] = args.torch_home

    run(
        sequences_path=args.sequences,
        candidates_path=args.candidates,
        out_dir=args.out_dir,
        models=[x.strip() for x in args.models.split(",") if x.strip()],
        consensus_k=args.consensus_k,
        dll_threshold=args.dll_threshold,
        top_per_chain=args.top_per_chain,
        maxrep=args.maxrep,
        device=args.device,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
