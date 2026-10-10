"""WT 与突变体同一套局部受限松弛后的能量比较。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tm_disulfide.build import _run_worker, cif_to_pdb
from tm_disulfide.constants import (
    BUILD_SS_CONSTRAINT,
    BUILD_SS_CONSTRAINT_SD,
    ENERGY_DDG_MAX,
    ENERGY_LOCAL_RADIUS,
    ENERGY_REP_DELTA_MAX,
    MINIMUM_MODELS_PASSED,
)
from tm_disulfide.ensemble import run_ensemble_alignment


def _pair_slug(pair_id: str) -> str:
    return pair_id.replace(":", "_")


def _site_tuple(pair: dict[str, Any], which: str) -> tuple[str, int]:
    site = pair[which]
    return str(site["structure_chain"]), int(site["sequence_index"])


def selected_built_attempt(model_record: dict[str, Any]) -> dict[str, Any] | None:
    mode = model_record.get("selected_attempt")
    attempts = list(model_record.get("attempts") or [])
    if mode:
        for row in attempts:
            if row.get("backbone_mode") == mode and row.get("build_pass"):
                return row
    for row in attempts:
        if row.get("build_pass"):
            return row
    return None


def energy_pass(wt: dict[str, Any], mut: dict[str, Any]) -> tuple[bool, list[str], float | None]:
    """折叠态：键还在且没有严重碰撞即通过。ΔΔG（不含 ref）只返回供排序。"""
    reasons = []
    if wt.get("error"):
        reasons.append("wt_error")
    if mut.get("error"):
        reasons.append("mut_error")
    if not mut.get("designed_bonded"):
        reasons.append("mut_not_bonded")
    if not mut.get("disulfides_preserved"):
        reasons.append("mut_disulfide_lost")
    if not wt.get("disulfides_preserved"):
        reasons.append("wt_disulfide_lost")
    wt_score = wt.get("fa_score_noref")
    mut_score = mut.get("fa_score_noref")
    ddg = None
    if wt_score is None or mut_score is None:
        reasons.append("missing_score")
    else:
        ddg = round(float(mut_score) - float(wt_score), 3)
    wt_rep = wt.get("fa_rep")
    mut_rep = mut.get("fa_rep")
    if wt_rep is None or mut_rep is None:
        reasons.append("missing_fa_rep")
    elif float(mut_rep) - float(wt_rep) > ENERGY_REP_DELTA_MAX:
        reasons.append("fa_rep_clash")
    return not reasons, reasons, ddg


def summarize_pair_energy(pair: dict[str, Any], model_records: list[dict[str, Any]]) -> dict[str, Any]:
    ddgs = [row["ddg"] for row in model_records if row.get("ddg") is not None]
    n_pass = sum(1 for row in model_records if row.get("energy_pass"))
    median = None
    if ddgs:
        ordered = sorted(ddgs)
        mid = len(ordered) // 2
        median = ordered[mid] if len(ordered) % 2 else round((ordered[mid - 1] + ordered[mid]) / 2, 3)
    return {
        "pair_id": pair["pair_id"],
        "site1": pair.get("site1"),
        "site2": pair.get("site2"),
        "n_models_passed": n_pass,
        "n_models": len(model_records),
        "pair_energy_pass": n_pass >= MINIMUM_MODELS_PASSED,
        "median_ddg": median,
        "models": model_records,
    }


def _jobs_for_model(
    pairs: list[dict[str, Any]],
    model_records: dict[str, dict[str, Any]],
    wt_pdb: Path,
    out_dir: Path,
    model_stem: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    jobs = []
    skipped = []
    for pair in pairs:
        record = model_records.get(pair["pair_id"])
        if not record or not record.get("build_pass"):
            skipped.append(
                {
                    "pair_id": pair["pair_id"],
                    "model_name": record.get("model_name") if record else None,
                    "energy_pass": False,
                    "failure_reasons": ["build_not_passed"],
                    "ddg": None,
                }
            )
            continue
        attempt = selected_built_attempt(record)
        mut_pdb = Path((attempt or {}).get("output_structure") or "")
        if attempt is None or not mut_pdb.is_file():
            skipped.append(
                {
                    "pair_id": pair["pair_id"],
                    "model_name": record["model_name"],
                    "energy_pass": False,
                    "failure_reasons": ["missing_mutant_pdb"],
                    "ddg": None,
                }
            )
            continue
        site1, site2 = _site_tuple(pair, "site1"), _site_tuple(pair, "site2")
        slug = _pair_slug(pair["pair_id"])
        common = {
            "chain1": site1[0],
            "seq1": site1[1],
            "chain2": site2[0],
            "seq2": site2[1],
            "radius": ENERGY_LOCAL_RADIUS,
            "ss_target": BUILD_SS_CONSTRAINT,
            "ss_sd": BUILD_SS_CONSTRAINT_SD,
        }
        jobs.append(
            {
                **common,
                "id": f"{pair['pair_id']}::wt",
                "role": "wt",
                "pdb": str(wt_pdb),
                "out_pdb": str(out_dir / model_stem / f"{slug}_wt_relax.pdb"),
            }
        )
        jobs.append(
            {
                **common,
                "id": f"{pair['pair_id']}::mut",
                "role": "mut",
                "pdb": str(mut_pdb),
                "out_pdb": str(out_dir / model_stem / f"{slug}_mut_relax.pdb"),
            }
        )
    return jobs, skipped


def run_energy_compare(
    fasta_text: str,
    structure_paths: list[Path] | Path,
    out_dir: Path,
    *,
    build_report: dict[str, Any] | None = None,
    build_dir: Path | None = None,
    ensemble: dict[str, Any] | None = None,
    pair_ids: list[str] | None = None,
    model_names: list[str] | None = None,
) -> dict[str, Any]:
    """对建模通过的候选做 WT / 突变体同一套局部松弛，比较全原子能量。"""
    if build_report is None:
        if build_dir is None:
            raise ValueError("需要 build_report 或 build_dir")
        build_path = Path(build_dir) / "build.json"
        build_report = json.loads(build_path.read_text(encoding="utf-8"))
    ensemble_report = ensemble or run_ensemble_alignment(fasta_text, structure_paths)
    pairs = [pair for pair in build_report.get("pairs") or [] if pair.get("pair_build_pass")]
    if pair_ids is not None:
        wanted = set(pair_ids)
        pairs = [pair for pair in pairs if pair["pair_id"] in wanted]
    if not pairs:
        raise ValueError("没有建模通过的候选可做能量比较")

    paths = [Path(p) for p in ensemble_report["structure_paths"]]
    if model_names is not None:
        wanted_models = set(model_names)
        paths = [path for path in paths if path.name in wanted_models]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    build_inputs = Path(build_dir) / "inputs" if build_dir is not None else out / "inputs"

    by_pair: dict[str, list[dict[str, Any]]] = {pair["pair_id"]: [] for pair in pairs}
    for cif_path in paths:
        model_name = cif_path.name
        model_stem = cif_path.stem
        (out / model_stem).mkdir(parents=True, exist_ok=True)
        wt_pdb = build_inputs / f"{model_stem}.pdb"
        if not wt_pdb.is_file():
            wt_pdb = cif_to_pdb(cif_path, out / "inputs" / f"{model_stem}.pdb")
        model_records = {
            pair["pair_id"]: next(
                (row for row in pair.get("models") or [] if row.get("model_name") == model_name),
                None,
            )
            for pair in pairs
        }
        jobs, skipped = _jobs_for_model(pairs, model_records, wt_pdb, out, model_stem)
        for row in skipped:
            row["model_name"] = model_name
            by_pair[row["pair_id"]].append(row)
        if not jobs:
            continue
        try:
            results = _run_worker({"task": "local_relax", "pdb": str(wt_pdb), "jobs": jobs})
            if isinstance(results, dict):
                results = [results]
        except Exception as exc:  # noqa: BLE001
            for pair in pairs:
                if any(item["pair_id"] == pair["pair_id"] for item in skipped):
                    continue
                by_pair[pair["pair_id"]].append(
                    {
                        "pair_id": pair["pair_id"],
                        "model_name": model_name,
                        "energy_pass": False,
                        "failure_reasons": ["worker_failed"],
                        "error": str(exc),
                        "ddg": None,
                    }
                )
            continue
        by_id = {row.get("id"): row for row in results}
        for pair in pairs:
            wt = by_id.get(f"{pair['pair_id']}::wt")
            mut = by_id.get(f"{pair['pair_id']}::mut")
            if wt is None or mut is None:
                if not any(item.get("pair_id") == pair["pair_id"] and item.get("model_name") == model_name for item in skipped):
                    by_pair[pair["pair_id"]].append(
                        {
                            "pair_id": pair["pair_id"],
                            "model_name": model_name,
                            "energy_pass": False,
                            "failure_reasons": ["missing_worker_result"],
                            "ddg": None,
                        }
                    )
                continue
            ok, reasons, ddg = energy_pass(wt, mut)
            by_pair[pair["pair_id"]].append(
                {
                    "pair_id": pair["pair_id"],
                    "model_name": model_name,
                    "energy_pass": ok,
                    "failure_reasons": reasons,
                    "ddg": ddg,
                    "wt_score": wt.get("fa_score_noref"),
                    "mut_score": mut.get("fa_score_noref"),
                    "wt_score_raw": wt.get("fa_score"),
                    "mut_score_raw": mut.get("fa_score"),
                    "wt_rep": wt.get("fa_rep"),
                    "mut_rep": mut.get("fa_rep"),
                    "wt_dslf": wt.get("dslf_fa13_energy"),
                    "mut_dslf": mut.get("dslf_fa13_energy"),
                    "wt_n_local": wt.get("n_local"),
                    "mut_n_local": mut.get("n_local"),
                    "wt_structure": wt.get("out_pdb"),
                    "mut_structure": mut.get("out_pdb"),
                    "wt": wt,
                    "mut": mut,
                }
            )

    summaries = [summarize_pair_energy(pair, by_pair[pair["pair_id"]]) for pair in pairs]
    result = {
        "n_input_pairs": len(pairs),
        "n_models": len(paths),
        "n_pair_pass": sum(1 for row in summaries if row["pair_energy_pass"]),
        "minimum_models_passed": MINIMUM_MODELS_PASSED,
        "ddg_max": ENERGY_DDG_MAX,
        "fa_rep_delta_max": ENERGY_REP_DELTA_MAX,
        "local_radius": ENERGY_LOCAL_RADIUS,
        "pairs": summaries,
    }
    (out / "energy.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result
