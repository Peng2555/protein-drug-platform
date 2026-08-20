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
                    "mutation": f"{chain_id}:{wt}{i + 1}{mut}",
                    "region": region,
                    "buried": None,
                    "interface": False,
                    "esm_dll": row["dll"],
                    "hydro_delta": hydro_delta,
                    "maxwell_ddg": None,
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
            "ESM-2 3B 与 Venus-MAXWELL 平行打分：ΔLL=序列可接受度，ΔΔG=相对稳定性。"
            "亲水Δ仍是 Kyte–Doolittle 标注。"
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
        "region", "buried", "interface", "esm_dll", "hydro_delta", "maxwell_ddg",
        "pass_esm", "pass_hydro", "pass_tm", "status",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in candidates:
            writer.writerow(row)


def _polymer_seq(chain) -> str:
    import gemmi

    seq = []
    for res in chain:
        if res.entity_type == gemmi.EntityType.Polymer or res.get_ca():
            one = gemmi.find_tabulated_residue(res.name).one_letter_code
            if one and one not in {"X", " ", "?"}:
                seq.append(one)
    return "".join(seq)


def extract_chain_pdb(structure_path: Path, chain_id: str, dest: Path, expected_seq: str = "") -> str:
    """Write one chain to PDB (protein residues only). Returns one-letter sequence."""
    import gemmi

    st = gemmi.read_structure(str(structure_path))
    st.remove_ligands_and_waters()
    out = gemmi.Structure()
    out.cell = st.cell
    out.spacegroup_hm = st.spacegroup_hm
    model = gemmi.Model("1")
    found = None
    for ch in st[0]:
        if ch.name == chain_id:
            found = ch.clone()
            break
    if found is None and expected_seq:
        for ch in st[0]:
            if _polymer_seq(ch) == expected_seq:
                found = ch.clone()
                break
    if found is None:
        names = [ch.name for ch in st[0]]
        raise ValueError(f"结构中没有链 {chain_id}（现有: {', '.join(names) or '无'}）")
    found.name = chain_id
    seq = _polymer_seq(found)
    model.add_chain(found)
    out.add_model(model)
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.write_pdb(str(dest))
    return seq


def _run_maxwell_cli(
    *,
    python_bin: str,
    script: Path,
    pdb_file: Path,
    chain: str,
    ckpt: Path,
    output_file: Path,
    device: str,
) -> dict:
    import subprocess

    proc = subprocess.run(
        [
            python_bin,
            str(script),
            "--pdb_file", str(pdb_file),
            "--chain", chain,
            "--ckpt_path", str(ckpt),
            "--output_file", str(output_file),
            "--device", device,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "MAXWELL failed")[-4000:]
        raise RuntimeError(err)
    return json.loads(output_file.read_text(encoding="utf-8"))


def attach_maxwell_scores(
    payload: dict,
    *,
    structure_path: Path,
    work_dir: Path,
    python_bin: str,
    ckpt: Path,
    script: Path,
    device: str = "cuda",
    on_stage: Callable[[str], None] | None = None,
) -> dict:
    """Fill parallel MAXWELL ΔΔG onto residues/candidates. Does not change ESM tiers."""
    warnings: list[str] = []
    chain_results: list[dict] = []
    maxwell_dir = work_dir / "maxwell"
    maxwell_dir.mkdir(parents=True, exist_ok=True)

    for chain in payload.get("chains") or []:
        cid = str(chain["chain_id"])
        fasta_seq = chain.get("sequence") or ""
        if on_stage:
            on_stage(f"maxwell:{cid}")
        try:
            pdb_path = maxwell_dir / f"chain_{cid}.pdb"
            pdb_seq = extract_chain_pdb(structure_path, cid, pdb_path, expected_seq=fasta_seq)
            if pdb_seq and fasta_seq and pdb_seq != fasta_seq:
                if len(pdb_seq) != len(fasta_seq):
                    warnings.append(
                        f"链 {cid} 结构序列长度 {len(pdb_seq)} ≠ FASTA {len(fasta_seq)}，已跳过 MAXWELL"
                    )
                    continue
                warnings.append(f"链 {cid} 结构序列与 FASTA 不完全一致，仍按结构坐标打分")
            out_json = maxwell_dir / f"chain_{cid}.json"
            data = _run_maxwell_cli(
                python_bin=python_bin,
                script=script,
                pdb_file=pdb_path,
                chain=cid,
                ckpt=ckpt,
                output_file=out_json,
                device=device,
            )
            seq = data.get("sequence") or pdb_seq
            ddg_map: dict[tuple[int, str], float] = {}
            for row in data.get("rows") or []:
                ddg_map[(int(row["pos"]), str(row["mut"]))] = float(row["ddg"])
            for res in chain.get("residues") or []:
                idx = int(res["index"])
                for score in res.get("aa_scores") or []:
                    score["maxwell_ddg"] = ddg_map.get((idx, score["aa"]))
                mut_scores = [
                    s["maxwell_ddg"]
                    for s in (res.get("aa_scores") or [])
                    if not s.get("is_wt") and s.get("maxwell_ddg") is not None
                ]
                res["best_maxwell_aa"] = None
                res["best_maxwell_ddg"] = None
                if mut_scores:
                    best = min(
                        (s for s in res["aa_scores"] if not s.get("is_wt") and s.get("maxwell_ddg") is not None),
                        key=lambda s: s["maxwell_ddg"],
                    )
                    res["best_maxwell_aa"] = best["aa"]
                    res["best_maxwell_ddg"] = best["maxwell_ddg"]
            chain_results.append({"chain_id": cid, "length": len(seq), "status": "ok"})
        except Exception as exc:
            warnings.append(f"链 {cid} MAXWELL 失败: {exc}")
            chain_results.append({"chain_id": cid, "status": "failed", "error": str(exc)})

    for cand in payload.get("candidates") or []:
        chain = next((c for c in payload["chains"] if c["chain_id"] == cand["chain"]), None)
        ddg = None
        if chain:
            res = next((r for r in chain["residues"] if r["index"] == cand["seq_pos"]), None)
            if res:
                hit = next((s for s in res.get("aa_scores") or [] if s["aa"] == cand["mut"]), None)
                if hit:
                    ddg = hit.get("maxwell_ddg")
        cand["maxwell_ddg"] = ddg
        cand["pass_tm"] = (ddg < 0) if ddg is not None else None

    payload["maxwell"] = {
        "engine": "venus-maxwell-esmif",
        "structure": str(structure_path),
        "chains": chain_results,
        "warnings": warnings,
        "n_stabilizing": sum(1 for c in payload.get("candidates") or [] if c.get("pass_tm")),
    }
    return payload


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
        structure_path = params.get("structure_path")
        run_maxwell = bool(params.get("run_maxwell", True)) and bool(structure_path)
        if run_maxwell:
            ckpt = Path(params.get("maxwell_ckpt") or "")
            py = str(params.get("maxwell_python") or "")
            script = Path(__file__).resolve().parent / "maxwell_landscape.py"
            if not ckpt.is_file():
                payload["maxwell"] = {"engine": "venus-maxwell-esmif", "skipped": "missing checkpoint"}
            elif not Path(py).is_file():
                payload["maxwell"] = {"engine": "venus-maxwell-esmif", "skipped": "missing maxwell python"}
            else:
                if on_stage:
                    on_stage("maxwell")
                device = "cuda" if os.environ.get("CUDA_VISIBLE_DEVICES", "0") != "" else "cpu"
                payload = attach_maxwell_scores(
                    payload,
                    structure_path=Path(structure_path),
                    work_dir=work_dir,
                    python_bin=py,
                    ckpt=ckpt,
                    script=script,
                    device=device,
                    on_stage=on_stage,
                )
        else:
            payload["maxwell"] = {
                "engine": "venus-maxwell-esmif",
                "skipped": "no structure (fold job or PDB/CIF upload required)",
            }
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
