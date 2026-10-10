"""额外二硫键：已有 Boltz2 多模型 → 质控 → 几何 → 成键 → 折叠态能量。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Iterable

from boltzfold_shared.io import parse_fasta, write_csv, write_fasta
from tm_disulfide.build import run_build_all
from tm_disulfide.constants import MINIMUM_MODELS_PASSED
from tm_disulfide.energy import run_energy_compare
from tm_disulfide.ensemble import run_ensemble_alignment
from tm_disulfide.geometry import run_geometry_search
from tm_disulfide.pairs import run_pair_screen
from tm_disulfide.qc import discover_boltz_models, run_structure_qc
from tm_disulfide.sites import run_site_mask

CANDIDATE_COLUMNS = (
    "rank",
    "pair_id",
    "site1",
    "site2",
    "geometry_pass",
    "build_pass",
    "energy_pass",
    "n_models_build",
    "n_models_energy",
    "median_ddg",
)


def _resolve_structure_paths(structure_paths: Iterable[Path] | Path) -> list[Path]:
    if isinstance(structure_paths, Path):
        return discover_boltz_models(structure_paths)
    return [Path(path) for path in structure_paths]


def _site_label(site: dict[str, Any] | None) -> str:
    if not site:
        return ""
    chain = site.get("structure_chain") or site.get("chain") or ""
    index = site.get("sequence_index") or site.get("resi") or ""
    return f"{chain}:{index}"


def _write_status(
    work_dir: Path,
    stage: str,
    *,
    status: str = "running",
    summary: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {"stage": stage, "status": status}
    if summary is not None:
        payload["summary"] = summary
    (work_dir / "workflow_status.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _candidate_rows(
    geometry_report: dict[str, Any],
    build_report: dict[str, Any] | None,
    energy_report: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    build_by_id = {row["pair_id"]: row for row in (build_report or {}).get("pairs") or []}
    energy_by_id = {row["pair_id"]: row for row in (energy_report or {}).get("pairs") or []}
    rows: list[dict[str, Any]] = []
    for pair in geometry_report.get("pairs") or []:
        pair_id = str(pair["pair_id"])
        built = build_by_id.get(pair_id) or {}
        scored = energy_by_id.get(pair_id) or {}
        energy_pass = bool(scored.get("pair_energy_pass"))
        median = scored.get("median_ddg")
        rows.append(
            {
                "pair_id": pair_id,
                "site1": _site_label(pair.get("site1")),
                "site2": _site_label(pair.get("site2")),
                "geometry_pass": bool(pair.get("pair_geometry_pass")),
                "build_pass": bool(built.get("pair_build_pass")),
                "energy_pass": energy_pass,
                "n_models_build": built.get("n_models_passed") or 0,
                "n_models_energy": scored.get("n_models_passed") or 0,
                "median_ddg": median,
                "_sort_ddg": float(median) if median is not None else 1e9,
            }
        )
    rows.sort(key=lambda row: (not row["energy_pass"], row["_sort_ddg"], row["pair_id"]))
    out = []
    for index, row in enumerate(rows, start=1):
        row = dict(row)
        row["rank"] = index
        row.pop("_sort_ddg", None)
        out.append(row)
    return out


def run_workflow(
    work_dir: Path,
    *,
    fasta_text: str,
    structure_paths: list[Path] | Path,
    on_stage: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    work_dir = work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    inp = work_dir / "input"
    exports = work_dir / "exports"
    build_dir = work_dir / "build"
    energy_dir = work_dir / "energy"
    aligned_dir = work_dir / "ensemble"
    for folder in (inp, exports, build_dir, energy_dir, aligned_dir):
        folder.mkdir(parents=True, exist_ok=True)

    def stage(name: str, summary: dict[str, Any] | None = None) -> None:
        _write_status(work_dir, name, summary=summary)
        if on_stage:
            on_stage(name)

    seqs = parse_fasta(fasta_text)
    if not seqs:
        raise ValueError("FASTA 无效")
    write_fasta(seqs, inp / "sequences.fasta")

    paths = _resolve_structure_paths(structure_paths)
    if not paths:
        raise ValueError("没有可用的 Boltz2 模型（需要 *_model_N.cif）")
    (inp / "source_models.json").write_text(
        json.dumps(
            {
                "n_models": len(paths),
                "paths": [str(path) for path in paths],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    stage("qc")
    qc_report = run_structure_qc(fasta_text, paths)
    if qc_report["n_models"] < MINIMUM_MODELS_PASSED:
        raise ValueError(
            f"结构套数不足：需要至少 {MINIMUM_MODELS_PASSED} 套，实际 {qc_report['n_models']}"
        )
    if not qc_report["ok"]:
        raise ValueError("结构质控未通过: " + "; ".join(qc_report["errors"][:8]))

    stage("ensemble")
    ensemble_report = run_ensemble_alignment(fasta_text, paths, aligned_dir=aligned_dir)

    stage("sites")
    site_report = run_site_mask(fasta_text, paths, ensemble=ensemble_report)

    stage("pairs")
    pair_report = run_pair_screen(fasta_text, paths, site_table=site_report)

    stage("geometry")
    geometry_report = run_geometry_search(fasta_text, paths, pair_report=pair_report)

    build_report: dict[str, Any] = {"pairs": [], "n_pair_pass": 0, "n_input_pairs": 0}
    energy_report: dict[str, Any] = {"pairs": [], "n_pair_pass": 0, "n_input_pairs": 0}

    stage("build")
    if geometry_report.get("pairs"):
        try:
            build_report = run_build_all(
                fasta_text,
                paths,
                build_dir,
                geometry_report=geometry_report,
                ensemble=ensemble_report,
            )
        except ValueError as exc:
            build_report = {"pairs": [], "n_pair_pass": 0, "n_input_pairs": 0, "error": str(exc)}

    stage("energy")
    if any(row.get("pair_build_pass") for row in build_report.get("pairs") or []):
        try:
            energy_report = run_energy_compare(
                fasta_text,
                paths,
                energy_dir,
                build_report=build_report,
                build_dir=build_dir,
                ensemble=ensemble_report,
            )
        except ValueError as exc:
            energy_report = {"pairs": [], "n_pair_pass": 0, "n_input_pairs": 0, "error": str(exc)}

    candidates = _candidate_rows(geometry_report, build_report, energy_report)
    write_csv(exports / "candidates.csv", candidates, CANDIDATE_COLUMNS)
    summary = {
        "n_models": qc_report["n_models"],
        "n_eligible_sites": site_report.get("n_eligible"),
        "n_distance_pairs": pair_report.get("n_passed") or len(pair_report.get("pairs") or []),
        "n_geometry_pass": geometry_report.get("n_passed") or len(geometry_report.get("pairs") or []),
        "n_build_pass": build_report.get("n_pair_pass")
        or sum(1 for row in build_report.get("pairs") or [] if row.get("pair_build_pass")),
        "n_energy_pass": energy_report.get("n_pair_pass")
        or sum(1 for row in energy_report.get("pairs") or [] if row.get("pair_energy_pass")),
        "minimum_models_passed": MINIMUM_MODELS_PASSED,
        "medoid": ensemble_report.get("medoid_name") or ensemble_report.get("medoid"),
    }
    (exports / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    stage("done", summary)
    _write_status(work_dir, "done", status="ok", summary=summary)
    return {
        "summary": summary,
        "candidates": candidates,
        "qc": {"ok": qc_report["ok"], "n_models": qc_report["n_models"], "errors": qc_report["errors"]},
        "n_geometry_pass": summary["n_geometry_pass"],
        "n_build_pass": summary["n_build_pass"],
        "n_energy_pass": summary["n_energy_pass"],
    }
