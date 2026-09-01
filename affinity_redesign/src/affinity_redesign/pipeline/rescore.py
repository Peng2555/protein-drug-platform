"""Boltz2 全量预测 + Rosetta + 导出排名表。"""

from __future__ import annotations

import csv
import json
import shutil
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from queue import Queue

from affinity_redesign.common.fasta import parse_fasta_file, write_fasta
from affinity_redesign.config import settings
from affinity_redesign.pipeline.merge import load_plm_top_csv, load_structure_top_csv
from affinity_redesign.schemas import CampaignConfig, RescoreConfig, Round1Config
from affinity_redesign.tracks.boltz2 import fold_complex
from affinity_redesign.tracks.gpu_pool import select_idle_gpu_ids, write_pool_status


def _chain_order(campaign: CampaignConfig) -> list[str]:
    ids = [campaign.chains.heavy]
    if campaign.chains.light:
        ids.append(campaign.chains.light)
    ids.append(campaign.chains.antigen)
    return ids


def apply_mutation(seqs: dict[str, str], chain: str, pos1: int, wt: str, mut: str) -> dict[str, str]:
    if chain not in seqs:
        raise KeyError(f"序列中没有链 {chain}")
    s = seqs[chain]
    i = pos1 - 1
    if i < 0 or i >= len(s):
        raise ValueError(f"{chain}{pos1} 超出序列长度 {len(s)}")
    if s[i] != wt:
        raise ValueError(f"{chain}{pos1}: FASTA 为 {s[i]}，候选表为 {wt}")
    out = dict(seqs)
    out[chain] = s[:i] + mut + s[i + 1 :]
    return out


SEQUENCES_FASTA_NAME = "sequences_wt_mutants.fasta"


def _wrap_seq(seq: str, width: int = 60) -> str:
    seq = seq.replace(" ", "").strip()
    if not seq:
        return ""
    return "\n".join(seq[i : i + width] for i in range(0, len(seq), width))


def build_wt_mutant_fasta(
    seqs: dict[str, str],
    ranked: list[dict],
    *,
    antigen_chain: str | None = None,
) -> str:
    """WT + 每个突变体的完整复合物序列；header 标明 WT / 突变。"""
    lines: list[str] = []
    for cid, seq in seqs.items():
        lines.append(f">WT chain={cid} role=wild-type")
        lines.append(_wrap_seq(seq))
    for row in ranked:
        chain = str(row.get("chain") or "").strip()
        wt = str(row.get("wt") or "").strip()
        mut = str(row.get("mut") or "").strip()
        label = str(row.get("label") or "").strip()
        try:
            pos = int(row.get("position"))
        except (TypeError, ValueError):
            continue
        if not chain or not wt or not mut:
            continue
        vid = str(row.get("variant_id") or "").strip() or variant_id(chain, label or f"{wt}{pos}{mut}")
        mut_tag = f"{chain}:{wt}{pos}{mut}"
        try:
            mut_seqs = apply_mutation(seqs, chain, pos, wt, mut)
        except (KeyError, ValueError):
            continue
        for cid, seq in mut_seqs.items():
            extra = " role=mutated" if cid == chain else " role=unchanged"
            if antigen_chain and cid == antigen_chain and cid != chain:
                extra = " role=antigen_unchanged"
            lines.append(
                f">{vid} chain={cid} mutation={mut_tag} wt={wt} mut={mut} position={pos}{extra}"
            )
            lines.append(_wrap_seq(seq))
    return "\n".join(lines) + "\n"


def variant_id(chain: str, label: str) -> str:
    return f"{chain}_{label}"


def _pair_iptm(pair: dict | None, i: str, j: str) -> float | None:
    if not pair:
        return None
    inner = pair.get(str(i)) or pair.get(i)
    if not isinstance(inner, dict):
        return None
    val = inner.get(str(j), inner.get(j))
    return float(val) if val is not None else None


def load_merged_rows(campaign_dir: Path) -> list[dict]:
    merged = campaign_dir / "round1" / "merged"
    rows: list[dict] = []
    for tier in ("A", "B", "C"):
        path = merged / f"tier_{tier}.csv"
        if not path.is_file():
            continue
        with path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                r["tier"] = tier
                rows.append(r)
    if rows:
        return rows
    # fallback: reconstruct from tops if merge csv missing
    plm = campaign_dir / "round1" / "plm" / "top_per_chain.csv"
    st = campaign_dir / "round1" / "structure" / "top_per_chain.csv"
    if plm.is_file() and st.is_file():
        from affinity_redesign.pipeline.merge import merge_tracks
        from affinity_redesign.schemas import MergeConfig

        tiers = merge_tracks(
            load_plm_top_csv(plm),
            load_structure_top_csv(st),
            MergeConfig(),
            merged,
        )
        for name, recs in tiers.items():
            for rec in recs:
                rows.append(
                    {
                        "chain": rec.chain,
                        "position": str(rec.position),
                        "wt": rec.wt,
                        "mut": rec.mut,
                        "region": rec.region,
                        "tier": name,
                        "plm_score": "" if rec.plm_score is None else rec.plm_score,
                        "structure_score": "" if rec.structure_score is None else rec.structure_score,
                        "label": rec.label,
                    }
                )
    if not rows:
        raise FileNotFoundError(f"没有 merge 结果: {merged}")
    return rows


def _f(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def recommend_row(row: dict, cfg: RescoreConfig) -> tuple[str, str, bool]:
    """返回 (decision, reason, wetlab)."""
    if row.get("boltz2_status") != "ok":
        return "drop", "Boltz2 预测失败", False
    d_iptm = _f(row.get("delta_iptm"))
    if d_iptm is not None and d_iptm < cfg.delta_iptm_min:
        return "drop", f"ΔipTM {d_iptm:.3f} < {cfg.delta_iptm_min}", False
    ddg = _f(row.get("ddG"))
    if ddg is not None and ddg > cfg.max_ddg:
        return "review", f"Boltz2 过门，但 Rosetta ddG {ddg:.2f} > {cfg.max_ddg}", False
    flags = str(row.get("rosetta_flags") or "")
    if "severe_clash" in flags and row.get("tier") != "A":
        return "review", "Boltz2 过门，但 Rosetta 标 clash", False
    return "keep", "Boltz2 未明显变差" + ("" if ddg is None else " 且 Rosetta ddG 可接受"), True


def _run_rosetta(
    work_dir: Path,
    wt_pdb: Path,
    mutants: list[tuple[str, Path]],
    campaign: CampaignConfig,
    cfg: RescoreConfig,
) -> dict[str, dict]:
    work_dir.mkdir(parents=True, exist_ok=True)
    import os
    import subprocess

    staged = work_dir / "inputs"
    staged.mkdir(parents=True, exist_ok=True)
    wt_copy = staged / "WT.pdb"
    shutil.copy2(wt_pdb, wt_copy)
    mut_copies: list[Path] = []
    for name, path in mutants:
        dest = staged / f"{name}.pdb"
        shutil.copy2(path, dest)
        mut_copies.append(dest)

    n_jobs = int(cfg.n_jobs or 0)
    override = work_dir.parent / "n_jobs_override"
    if override.is_file():
        try:
            n_jobs = int(override.read_text(encoding="utf-8").strip())
        except ValueError:
            pass
    cmd = [
        settings.pyrosetta_python,
        str(settings.boltz2_root / "scripts" / "rosetta_eval_runner.py"),
        "--work-dir",
        str(work_dir),
        "--wt",
        str(wt_copy),
        "--nstruct",
        str(cfg.nstruct),
        "--n-jobs",
        str(n_jobs),
        "--antibody-chains",
        " ".join([campaign.chains.heavy] + ([campaign.chains.light] if campaign.chains.light else [])),
        "--antigen-chains",
        campaign.chains.antigen,
        "--pyrosetta-python",
        settings.pyrosetta_python,
        "--mutant",
        *[str(p) for p in mut_copies],
    ]
    log = work_dir / "rosetta.log"
    env = os.environ.copy()
    with log.open("w", encoding="utf-8") as f:
        proc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, text=True, check=False, env=env)
    if proc.returncode != 0:
        tail = log.read_text(encoding="utf-8", errors="replace")[-4000:]
        raise RuntimeError(f"Rosetta 失败 (code={proc.returncode}):\n{tail}")

    scores_path = work_dir / "scores.csv"
    by_name: dict[str, dict] = {}
    if scores_path.is_file():
        with scores_path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                by_name[r["name"]] = r
    return by_name


def _fold_kwargs(cfg: RescoreConfig) -> dict:
    return {
        "use_msa_server": cfg.use_msa_server,
        "recycling_steps": cfg.recycling_steps,
        "sampling_steps": cfg.sampling_steps,
        "diffusion_samples": cfg.diffusion_samples,
    }


def _run_folds_on_gpu_pool(
    jobs: list[tuple[str, Path]],
    fold_root: Path,
    cfg: RescoreConfig,
    gpu_ids: list[int],
    *,
    on_progress: Callable[[int, str], None] | None = None,
) -> dict[str, dict]:
    """每个 GPU 同时只跑 1 个 Boltz2；空卡数 = 并发数。"""
    if not jobs:
        return {}
    gpu_ids = gpu_ids or [0]
    gpu_q: Queue[int] = Queue()
    for gid in gpu_ids:
        gpu_q.put(gid)
    kwargs = _fold_kwargs(cfg)
    results: dict[str, dict] = {}
    n_workers = min(len(gpu_ids), len(jobs))

    def _one(vid: str, fasta: Path) -> tuple[str, dict]:
        gid = gpu_q.get()
        try:
            data = fold_complex(fasta, fold_root, vid, gpu_id=gid, **kwargs)
            return vid, data
        except Exception as exc:
            return vid, {"status": "failed", "error": str(exc)[:500], "job_id": vid}
        finally:
            gpu_q.put(gid)

    done = 0
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futs = {pool.submit(_one, vid, fasta): vid for vid, fasta in jobs}
        for fut in as_completed(futs):
            vid, data = fut.result()
            results[vid] = data
            done += 1
            if on_progress:
                on_progress(done, vid)
    return results


def run_rescore(
    campaign_dir: Path,
    campaign: CampaignConfig,
    config: Round1Config,
    *,
    on_stage: Callable[[str], None] | None = None,
) -> dict:
    campaign_dir = campaign_dir.resolve()
    cfg = config.rescore
    seqs = parse_fasta_file(campaign_dir / "input" / "sequences.fasta")
    order = _chain_order(campaign)
    seqs = {k: seqs[k] for k in order}

    merged_rows = load_merged_rows(campaign_dir)
    max_variants = int(getattr(cfg, "max_variants", 0) or 0)
    if max_variants > 0 and len(merged_rows) > max_variants:
        tier_rank = {"A": 0, "B": 1, "C": 2}

        def _score(row: dict) -> float:
            for key in ("structure_score", "plm_score"):
                raw = row.get(key)
                if raw is None or raw == "":
                    continue
                try:
                    return float(raw)
                except (TypeError, ValueError):
                    continue
            return float("-inf")

        merged_rows = sorted(
            merged_rows,
            key=lambda r: (
                tier_rank.get(str(r.get("tier") or ""), 9),
                -_score(r),
                str(r.get("label") or ""),
            ),
        )[:max_variants]

    rescore_dir = campaign_dir / "round1" / "rescore"
    fold_root = rescore_dir / "boltz2"
    fasta_dir = rescore_dir / "fastas"
    fasta_dir.mkdir(parents=True, exist_ok=True)
    fold_root.mkdir(parents=True, exist_ok=True)

    def stage(name: str) -> None:
        if on_stage:
            on_stage(name)

    max_gpus = int(getattr(cfg, "n_gpus", 0) or 0) or None
    gpu_ids = select_idle_gpu_ids(max_gpus=max_gpus)
    write_pool_status(rescore_dir / "gpu_pool.json", gpu_ids)

    stage("boltz2_wt")
    wt_fa = fasta_dir / "WT.fasta"
    write_fasta(seqs, wt_fa)

    fold_jobs: list[tuple[str, Path]] = [("WT", wt_fa)]
    prepared: list[tuple[dict, str]] = []
    for src in merged_rows:
        vid = variant_id(src["chain"], src.get("label") or f"{src['wt']}{src['position']}{src['mut']}")
        try:
            mut_seqs = apply_mutation(
                seqs,
                src["chain"],
                int(src["position"]),
                src["wt"],
                src["mut"],
            )
        except ValueError as exc:
            src = dict(src)
            src["_fold_skip"] = {
                **{k: src.get(k, "") for k in ("chain", "position", "wt", "mut", "region", "tier", "label")},
                "plm_score": src.get("plm_score", ""),
                "structure_score": src.get("structure_score", ""),
                "variant_id": vid,
                "boltz2_status": "failed",
                "error": str(exc),
            }
            prepared.append((src, vid))
            continue
        fa = fasta_dir / f"{vid}.fasta"
        write_fasta(mut_seqs, fa)
        fold_jobs.append((vid, fa))
        prepared.append((src, vid))

    n_fold = len(fold_jobs)
    stage(f"boltz2_0/{n_fold}_gpu{len(gpu_ids)}")

    def _progress(done: int, vid: str) -> None:
        stage(f"boltz2_{done}/{n_fold}_{vid}")

    folds = _run_folds_on_gpu_pool(
        fold_jobs,
        fold_root,
        cfg,
        gpu_ids,
        on_progress=_progress,
    )
    wt_fold = folds.get("WT") or {}
    if wt_fold.get("status") != "ok":
        raise RuntimeError(f"WT Boltz2 失败: {wt_fold.get('error')}")
    wt_iptm = wt_fold.get("iptm")
    wt_pair = wt_fold.get("pair_chains_iptm") or {}
    # indices: 0=heavy, 1=light if present else antigen, last=antigen
    ag_idx = str(len(order) - 1)
    h_idx = "0"
    l_idx = "1" if campaign.chains.light else None

    ranked: list[dict] = []
    mutant_pdbs: list[tuple[str, Path]] = []

    for src, vid in prepared:
        skip = src.pop("_fold_skip", None)
        if skip:
            ranked.append(skip)
            continue
        fold = folds.get(vid) or {"status": "failed", "error": "missing fold result"}
        iptm = fold.get("iptm")
        pair = fold.get("pair_chains_iptm") or {}
        row = {
            "chain": src["chain"],
            "position": src["position"],
            "wt": src["wt"],
            "mut": src["mut"],
            "region": src.get("region", ""),
            "tier": src.get("tier", ""),
            "label": src.get("label", ""),
            "plm_score": src.get("plm_score", ""),
            "structure_score": src.get("structure_score", ""),
            "variant_id": vid,
            "boltz2_status": fold.get("status"),
            "iptm": iptm,
            "delta_iptm": None if iptm is None or wt_iptm is None else round(float(iptm) - float(wt_iptm), 6),
            "ptm": fold.get("ptm"),
            "complex_plddt": fold.get("complex_plddt"),
            "iptm_H_A": _pair_iptm(pair, h_idx, ag_idx),
            "iptm_L_A": _pair_iptm(pair, l_idx, ag_idx) if l_idx else "",
            "pdockq": fold.get("pdockq"),
            "pred_pdb": fold.get("pred_pdb"),
            "error": fold.get("error") or "",
        }
        pdb = fold.get("pred_pdb")
        if fold.get("status") == "ok" and pdb and Path(pdb).is_file():
            mutant_pdbs.append((vid, Path(pdb)))
        ranked.append(row)

    stage("rosetta")
    wt_pdb = Path(wt_fold["pred_pdb"])
    rosetta_dir = rescore_dir / "rosetta"
    rosetta_by = {}
    if mutant_pdbs:
        rosetta_by = _run_rosetta(rosetta_dir, wt_pdb, mutant_pdbs, campaign, cfg)

    for row in ranked:
        vid = row["variant_id"]
        rr = rosetta_by.get(vid) or {}
        row["dG_separated"] = rr.get("dG_separated", "")
        row["ddG"] = rr.get("ddG", "")
        row["delta_E"] = rr.get("delta_E", "")
        row["rosetta_flags"] = rr.get("flags", "")
        decision, reason, wetlab = recommend_row(row, cfg)
        row["decision"] = decision
        row["reason"] = reason
        row["wetlab"] = "yes" if wetlab else "no"

    # sort: keep first, then A, then ddG, then -delta_iptm
    def sort_key(r: dict):
        dec = {"keep": 0, "review": 1, "drop": 2}.get(r.get("decision"), 9)
        tier = {"A": 0, "B": 1, "C": 2}.get(r.get("tier"), 9)
        ddg = _f(r.get("ddG"))
        ddg_k = ddg if ddg is not None else 99.0
        di = _f(r.get("delta_iptm"))
        di_k = -(di if di is not None else -99.0)
        return (dec, tier, ddg_k, di_k)

    ranked.sort(key=sort_key)
    for i, r in enumerate(ranked, start=1):
        r["rank"] = i

    exports = campaign_dir / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    struct_dir = exports / "structures"
    struct_dir.mkdir(parents=True, exist_ok=True)
    if wt_pdb.is_file():
        shutil.copy2(wt_pdb, struct_dir / "WT.pdb")

    fieldnames = [
        "rank",
        "decision",
        "wetlab",
        "reason",
        "tier",
        "chain",
        "label",
        "position",
        "wt",
        "mut",
        "region",
        "plm_score",
        "structure_score",
        "iptm",
        "delta_iptm",
        "iptm_H_A",
        "iptm_L_A",
        "ptm",
        "complex_plddt",
        "pdockq",
        "dG_separated",
        "ddG",
        "delta_E",
        "rosetta_flags",
        "variant_id",
        "pred_pdb",
        "error",
    ]
    ranked_path = exports / "ranked_mutations.csv"
    with ranked_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(ranked)

    wetlab_rows = [r for r in ranked if r.get("wetlab") == "yes"]
    wetlab_path = exports / "wetlab_candidates.csv"
    with wetlab_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(wetlab_rows)
        for r in wetlab_rows:
            src = r.get("pred_pdb")
            if src and Path(src).is_file():
                shutil.copy2(src, struct_dir / f"{r['variant_id']}.pdb")

    fasta_path = exports / SEQUENCES_FASTA_NAME
    fasta_path.write_text(
        build_wt_mutant_fasta(seqs, ranked, antigen_chain=campaign.chains.antigen),
        encoding="utf-8",
    )

    summary = {
        "status": "ok",
        "n_merged": len(merged_rows),
        "n_boltz2_ok": sum(1 for r in ranked if r.get("boltz2_status") == "ok"),
        "n_keep": sum(1 for r in ranked if r.get("decision") == "keep"),
        "n_review": sum(1 for r in ranked if r.get("decision") == "review"),
        "n_drop": sum(1 for r in ranked if r.get("decision") == "drop"),
        "n_wetlab": len(wetlab_rows),
        "wt_iptm": wt_iptm,
        "wt_iptm_H_A": _pair_iptm(wt_pair, h_idx, ag_idx),
        "wt_iptm_L_A": _pair_iptm(wt_pair, l_idx, ag_idx) if l_idx else None,
        "delta_iptm_min": cfg.delta_iptm_min,
        "max_ddg": cfg.max_ddg,
        "ranked_csv": str(ranked_path),
        "wetlab_csv": str(wetlab_path),
        "sequences_fasta": str(fasta_path),
        "structures_dir": str(struct_dir),
    }
    (exports / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (rescore_dir / "result.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return summary
