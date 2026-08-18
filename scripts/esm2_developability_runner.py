#!/usr/bin/env python3
"""ESM-2 3B wild-type-marginal scoring for antibody developability redesign.

This is the first funnel: sequence-acceptable substitutions. It does not predict
affinity. Hydrophilicity deltas are annotated for the next stage; Tm is left pending.
"""

from __future__ import annotations

import csv
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

STANDARD_AA = list("ACDEFGHIKLMNPQRSTVWY")

# Kyte–Doolittle: higher = more hydrophobic.
KYTE_DOOLITTLE = {
    "A": 1.8, "R": -4.5, "N": -3.5, "D": -3.5, "C": 2.5,
    "Q": -3.5, "E": -3.5, "G": -0.4, "H": -3.2, "I": 4.5,
    "L": 3.8, "K": -3.9, "M": 1.9, "F": 2.8, "P": -1.6,
    "S": -0.8, "T": -0.7, "W": -0.9, "Y": -1.3, "V": 4.2,
}

DEFAULT_MODEL_PATH = Path(
    os.environ.get(
        "ESM2_3B_PATH",
        "/home/pengpai/data/cache/torch/hub/checkpoints/esm2_t36_3B_UR50D.pt",
    )
)


@dataclass
class DevelopabilityResult:
    status: str
    stage: str
    seconds: float
    results: dict
    error: str | None = None


def _region_for_index(index: int, cdr_spans: list[dict], domain: str | None) -> str:
    for span in cdr_spans:
        if span["start"] <= index <= span["end"]:
            return span["name"]
    prefix = "H" if (domain or "H") == "H" else "L"
    named = {s["name"]: s for s in cdr_spans}
    cdr1 = named.get(f"CDR-{prefix}1")
    cdr2 = named.get(f"CDR-{prefix}2")
    cdr3 = named.get(f"CDR-{prefix}3")
    if cdr1 and index < cdr1["start"]:
        return "FR1"
    if cdr1 and cdr2 and cdr1["end"] < index < cdr2["start"]:
        return "FR2"
    if cdr2 and cdr3 and cdr2["end"] < index < cdr3["start"]:
        return "FR3"
    if cdr3 and index > cdr3["end"]:
        return "FR4"
    return "FR"


def _freeze_reason(
    aa: str,
    region: str,
    *,
    freeze_cysteine: bool,
    freeze_cdr3: bool,
    freeze_all_cdrs: bool,
) -> str | None:
    if freeze_cysteine and aa == "C":
        return "cysteine"
    if freeze_all_cdrs and region.startswith("CDR-"):
        return "cdr"
    if freeze_cdr3 and region in {"CDR-H3", "CDR-L3"}:
        return "cdr3"
    return None


def _creates_nglycosylation(sequence: str, index: int, new_aa: str) -> bool:
    chars = list(sequence)
    chars[index] = new_aa
    n = len(chars)

    def is_sequon(start: int, seq: list[str] | str) -> bool:
        if start < 0 or start + 2 >= (len(seq) if not isinstance(seq, str) else len(seq)):
            return False
        return seq[start] == "N" and seq[start + 1] != "P" and seq[start + 2] in {"S", "T"}

    for start in range(max(0, index - 2), min(index, n - 3) + 1):
        if is_sequon(start, chars) and not is_sequon(start, sequence):
            return True
    return False


def _load_esm2(model_path: Path):
    import argparse
    import torch
    import esm

    if not model_path.is_file():
        raise FileNotFoundError(f"未找到本地 ESM-2 3B 权重: {model_path}")

    # fair-esm checkpoints pickle argparse.Namespace. PyTorch 2.6 defaults
    # torch.load(weights_only=True), which rejects that type.
    try:
        torch.serialization.add_safe_globals([argparse.Namespace])
    except Exception:
        pass
    original_load = torch.load

    def _trusted_local_load(*args, **kwargs):
        kwargs["map_location"] = kwargs.get("map_location", "cpu")
        kwargs["weights_only"] = False
        return original_load(*args, **kwargs)

    torch.load = _trusted_local_load
    try:
        model, alphabet = esm.pretrained.load_model_and_alphabet_local(str(model_path))
    finally:
        torch.load = original_load

    model.eval()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    if device.type == "cuda":
        model = model.half()
    return model, alphabet, device


def _log_probs_for_sequence(model, alphabet, device, sequence: str):
    import torch

    batch_converter = alphabet.get_batch_converter()
    _labels, _strs, tokens = batch_converter([("chain", sequence)])
    tokens = tokens.to(device)
    with torch.no_grad():
        if device.type == "cuda":
            with torch.cuda.amp.autocast(dtype=torch.float16):
                out = model(tokens, repr_layers=[], return_contacts=False)
        else:
            out = model(tokens, repr_layers=[], return_contacts=False)
    logits = out["logits"][0, 1 : 1 + len(sequence)].float()
    return torch.log_softmax(logits, dim=-1).cpu()


def score_sequences(
    fasta_text: str,
    *,
    model_path: Path = DEFAULT_MODEL_PATH,
    freeze_cysteine: bool = True,
    freeze_cdr3: bool = True,
    freeze_all_cdrs: bool = False,
    dll_threshold: float = 0.0,
    max_mutants_per_site: int = 19,
    goal: str = "both",
    parent_id: str = "parent",
    on_stage: Callable[[str], None] | None = None,
) -> dict:
    import sys
    from pathlib import Path as _P

    root = _P(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if str(root / "scripts") not in sys.path:
        sys.path.insert(0, str(root / "scripts"))

    from boltz_runner import parse_fasta_text
    from app.cdr_annotation import annotate_antibody_chain

    seqs = parse_fasta_text(fasta_text)
    if on_stage:
        on_stage("load_model")
    model, alphabet, device = _load_esm2(model_path)
    aa_index = {aa: alphabet.get_idx(aa) for aa in STANDARD_AA}

    if on_stage:
        on_stage("score")

    chains_out: list[dict] = []
    candidates: list[dict] = []

    for chain_id, sequence in seqs.items():
        ab = annotate_antibody_chain(sequence)
        cdr_spans = ab["cdr_spans"] if ab else []
        domain = ab["domain"] if ab else None
        kabat_labels = ab["kabat_labels"] if ab else [str(i + 1) for i in range(len(sequence))]
        log_probs = _log_probs_for_sequence(model, alphabet, device, sequence)

        residues: list[dict] = []
        for i, wt in enumerate(sequence):
            region = _region_for_index(i, cdr_spans, domain)
            freeze = _freeze_reason(
                wt, region,
                freeze_cysteine=freeze_cysteine,
                freeze_cdr3=freeze_cdr3,
                freeze_all_cdrs=freeze_all_cdrs,
            )
            wt_idx = aa_index.get(wt)
            aa_ll = []
            for aa in STANDARD_AA:
                idx = aa_index[aa]
                ll = float(log_probs[i, idx])
                dll = float(log_probs[i, idx] - log_probs[i, wt_idx]) if wt_idx is not None else 0.0
                aa_ll.append({"aa": aa, "ll": round(ll, 4), "dll": round(dll, 4), "is_wt": aa == wt})
            best = max((row for row in aa_ll if not row["is_wt"]), key=lambda r: r["dll"], default=None)
            if freeze:
                tier = "freeze"
            elif best and best["dll"] >= dll_threshold:
                tier = "candidate"
            else:
                tier = "avoid"

            residues.append({
                "index": i + 1,
                "aa": wt,
                "kabat": kabat_labels[i] if i < len(kabat_labels) else str(i + 1),
                "region": region,
                "tier": tier,
                "freeze_reason": freeze,
                "wt_ll": round(float(log_probs[i, wt_idx]), 4) if wt_idx is not None else None,
                "best_aa": None if freeze else (best["aa"] if best else None),
                "best_dll": None if freeze else (best["dll"] if best else None),
                "aa_scores": aa_ll,
            })

            if freeze or not best:
                continue
            ranked = sorted(
                (row for row in aa_ll if not row["is_wt"] and row["dll"] >= dll_threshold),
                key=lambda r: r["dll"],
                reverse=True,
            )
            allowed: list[dict] = []
            kept = 0
            for row in ranked:
                mut = row["aa"]
                if mut == "C":
                    continue
                if _creates_nglycosylation(sequence, i, mut):
                    continue
                hydro_delta = round(KYTE_DOOLITTLE[wt] - KYTE_DOOLITTLE[mut], 3)
                allowed.append({"aa": mut, "dll": row["dll"]})
                candidates.append({
                    "parent_id": parent_id,
                    "chain": chain_id,
                    "seq_pos": i + 1,
                    "kabat": residues[-1]["kabat"],
                    "wt": wt,
                    "mut": mut,
                    "mutation": f"{chain_id}:{wt}{residues[-1]['kabat']}{mut}",
                    "region": region,
                    "buried": None,
                    "interface": False,
                    "esm_dll": row["dll"],
                    "hydro_delta": hydro_delta,
                    "pass_esm": True,
                    "pass_hydro": hydro_delta > 0,
                    "pass_tm": None,
                    "status": "allowed",
                    "freeze_reason": None,
                })
                kept += 1
                if kept >= max_mutants_per_site:
                    break
            residues[-1]["allowed_aas"] = [x["aa"] for x in allowed]
            residues[-1]["allowed_count"] = len(allowed)

        n_freeze = sum(1 for r in residues if r["tier"] == "freeze")
        n_cand = sum(1 for r in residues if r["tier"] == "candidate")
        n_avoid = sum(1 for r in residues if r["tier"] == "avoid")
        chains_out.append({
            "chain_id": chain_id,
            "length": len(sequence),
            "sequence": sequence,
            "is_antibody": ab is not None,
            "domain": domain,
            "scheme": ab["scheme"] if ab else None,
            "cdr_spans": cdr_spans,
            "n_freeze": n_freeze,
            "n_candidate": n_cand,
            "n_avoid": n_avoid,
            "residues": residues,
        })

    def _rank_key(item: dict):
        return (str(item["chain"]), int(item["seq_pos"]), -float(item["esm_dll"]))

    candidates.sort(key=_rank_key)
    for rank, item in enumerate(candidates, start=1):
        item["rank"] = rank

    return {
        "protocol": "esm2_wt_marginal_developability",
        "model": "esm2_t36_3B_UR50D",
        "model_path": str(model_path),
        "scoring": "wild-type marginal (single forward pass per chain)",
        "goal": goal,
        "dll_threshold": dll_threshold,
        "freeze_cysteine": freeze_cysteine,
        "freeze_cdr3": freeze_cdr3,
        "freeze_all_cdrs": freeze_all_cdrs,
        "max_mutants_per_site": max_mutants_per_site,
        "note": (
            "ESM-2 给出可突变位点及可替换氨基酸（ΔLL≥阈值）。"
            "这不是亲和力或亲水性处方，亲水/Tm 列仅作后续参考。"
        ),
        "parent_id": parent_id,
        "chains": chains_out,
        "candidates": candidates,
        "n_candidates": len(candidates),
        "n_hydro_passed": sum(1 for c in candidates if c["pass_hydro"]),
        "standard_aa": STANDARD_AA,
    }


def write_candidates_csv(path: Path, candidates: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "rank", "parent_id", "chain", "seq_pos", "kabat", "wt", "mut", "mutation",
        "region", "buried", "interface", "esm_dll", "hydro_delta",
        "pass_esm", "pass_hydro", "pass_tm", "status",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in candidates:
            writer.writerow(row)


def run_developability_job(
    *,
    work_dir: Path,
    fasta_text: str,
    params: dict,
    on_stage: Callable[[str], None] | None = None,
) -> DevelopabilityResult:
    started = time.time()
    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        (work_dir / "input.fasta").write_text(fasta_text, encoding="utf-8")
        model_path = Path(params.get("model_path") or DEFAULT_MODEL_PATH)
        payload = score_sequences(
            fasta_text,
            model_path=model_path,
            freeze_cysteine=bool(params.get("freeze_cysteine", True)),
            freeze_cdr3=bool(params.get("freeze_cdr3", True)),
            freeze_all_cdrs=bool(params.get("freeze_all_cdrs", False)),
            dll_threshold=float(params.get("dll_threshold", 0.0)),
            max_mutants_per_site=int(params.get("max_mutants_per_site", 19)),
            goal=str(params.get("goal", "both")),
            parent_id=str(params.get("parent_id") or "parent"),
            on_stage=on_stage,
        )
        if on_stage:
            on_stage("write")
        summary_path = work_dir / "summary.json"
        csv_path = work_dir / "candidates.csv"
        json_path = work_dir / "candidates.json"
        summary_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        json_path.write_text(json.dumps(payload["candidates"], indent=2, ensure_ascii=False), encoding="utf-8")
        write_candidates_csv(csv_path, payload["candidates"])
        payload["output_files"] = sorted(p.name for p in work_dir.iterdir() if p.is_file())
        payload["candidates_csv"] = str(csv_path)
        payload["candidates_json"] = str(json_path)
        summary_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return DevelopabilityResult("ok", "done", time.time() - started, payload)
    except Exception as exc:
        return DevelopabilityResult("failed", "failed", time.time() - started, {}, str(exc))
