"""PyRosetta 显式双 Cys 建模：虚拟 SG 起步，约束优化后验收。"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from tm_disulfide.constants import (
    BUILD_ANGLE_CONSTRAINT_SD,
    BUILD_CB_SG_MAX,
    BUILD_CB_SG_MIN,
    BUILD_CHI3_DEVIATION_MAX,
    BUILD_LOCAL_CA_RADIUS,
    BUILD_SS_CONSTRAINT,
    BUILD_SS_CONSTRAINT_SD,
    BUILD_SS_MAX,
    BUILD_SS_MIN,
    CHI3_TARGETS,
    MINIMUM_MODELS_PASSED,
    SG_CLASH_DISTANCE,
    SS_DISTANCE_TARGET,
    THREE_TO_ONE,
)
from tm_disulfide.ensemble import run_ensemble_alignment
from tm_disulfide.geometry import (
    bond_angle,
    dihedral,
    extract_pair_frames,
    min_deviation,
    run_geometry_search,
)
from tm_disulfide.pairs import run_pair_screen
from tm_disulfide.qc import _pick_atom
from tm_disulfide.sites import run_site_mask

WORKER = Path(__file__).with_name("pyrosetta_worker.py")
PYROSETTA_PYTHON = os.environ.get(
    "PYROSETTA_PYTHON", "/home/pengpai/data/envs/pyrosetta/bin/python"
)


def _xyz(atom) -> np.ndarray | None:
    pos = atom.pos
    arr = np.array([float(pos.x), float(pos.y), float(pos.z)], dtype=float)
    if not np.all(np.isfinite(arr)):
        return arr * np.nan
    return arr


def cif_to_pdb(cif_path: Path, pdb_path: Path) -> Path:
    import gemmi

    structure = gemmi.read_structure(str(cif_path))
    pdb_path.parent.mkdir(parents=True, exist_ok=True)
    structure.write_pdb(str(pdb_path))
    return pdb_path


def _ca_table(structure) -> dict[tuple[str, int], np.ndarray]:
    table = {}
    for chain in structure[0]:
        seq_index = 0
        for res in chain:
            if THREE_TO_ONE.get(res.name) is None:
                continue
            seq_index += 1
            ca = _pick_atom(res, "CA")
            if ca is None:
                continue
            pos = ca.pos
            table[(chain.name, seq_index)] = np.array(
                [float(pos.x), float(pos.y), float(pos.z)], dtype=float
            )
    return table


def _sg_clash_count(structure, key1: tuple[str, int], key2: tuple[str, int]) -> tuple[int, float | None]:
    extracted = extract_pair_frames(structure, key1, key2)
    sg_atoms = []
    env = list(extracted["env"])
    wanted = {key1, key2}
    for chain in structure[0]:
        seq_index = 0
        for res in chain:
            if THREE_TO_ONE.get(res.name) is None:
                continue
            seq_index += 1
            key = (chain.name, seq_index)
            if key not in wanted:
                continue
            sg = _pick_atom(res, "SG")
            if sg is not None:
                pos = sg.pos
                sg_atoms.append(np.array([float(pos.x), float(pos.y), float(pos.z)], dtype=float))
    if len(sg_atoms) != 2:
        return 999, None
    env_arr = np.array(env, dtype=float) if env else np.zeros((0, 3))
    mins = []
    clashes = 0
    for sg in sg_atoms:
        if env_arr.size == 0:
            mins.append(float("inf"))
            continue
        dist = np.sqrt(np.sum((env_arr - sg) ** 2, axis=1))
        mins.append(float(dist.min()))
        clashes += int(np.sum(dist < SG_CLASH_DISTANCE))
    return clashes, round(min(mins), 3) if mins else None


def evaluate_built_geometry(
    built_pdb: Path,
    reference_pdb: Path,
    site1: tuple[str, int],
    site2: tuple[str, int],
) -> dict[str, Any]:
    import gemmi

    built = gemmi.read_structure(str(built_pdb))
    reference = gemmi.read_structure(str(reference_pdb))
    frames = extract_pair_frames(built, site1, site2)["frames"]
    f1, f2 = frames[site1], frames[site2]
    sg1 = None
    sg2 = None
    for chain in built[0]:
        seq_index = 0
        for res in chain:
            if THREE_TO_ONE.get(res.name) is None:
                continue
            seq_index += 1
            key = (chain.name, seq_index)
            sg = _pick_atom(res, "SG")
            if sg is None:
                continue
            pos = np.array([float(sg.pos.x), float(sg.pos.y), float(sg.pos.z)], dtype=float)
            if key == site1:
                sg1 = pos
            if key == site2:
                sg2 = pos
    if sg1 is None or sg2 is None:
        raise ValueError("建成结构缺少 SG")
    ss = float(np.linalg.norm(sg1 - sg2))
    cb_sg1 = float(np.linalg.norm(f1["CB"] - sg1))
    cb_sg2 = float(np.linalg.norm(f2["CB"] - sg2))
    angle1 = bond_angle(f1["CB"], sg1, sg2)
    angle2 = bond_angle(sg1, sg2, f2["CB"])
    chi1 = dihedral(f1["N"], f1["CA"], f1["CB"], sg1)
    chi2 = dihedral(f1["CA"], f1["CB"], sg1, sg2)
    chi3 = dihedral(f1["CB"], sg1, sg2, f2["CB"])
    chi2p = dihedral(sg1, sg2, f2["CB"], f2["CA"])
    chi1p = dihedral(sg2, f2["CB"], f2["CA"], f2["N"])
    chi3_dev = min_deviation(chi3, CHI3_TARGETS)
    clash_count, min_env = _sg_clash_count(built, site1, site2)

    ref_ca = _ca_table(reference)
    built_ca = _ca_table(built)
    common = sorted(set(ref_ca) & set(built_ca))
    if not common:
        raise ValueError("建成结构与参考结构没有共同 CA")
    ref_xyz = np.stack([ref_ca[k] for k in common])
    built_xyz = np.stack([built_ca[k] for k in common])
    global_rmsd = float(np.sqrt(np.mean(np.sum((ref_xyz - built_xyz) ** 2, axis=1))))
    disp = {k: float(np.linalg.norm(built_ca[k] - ref_ca[k])) for k in common}
    site1_disp = disp.get(site1)
    site2_disp = disp.get(site2)
    local_keys = []
    for key, xyz in ref_ca.items():
        if key not in built_ca:
            continue
        d1 = float(np.linalg.norm(xyz - ref_ca[site1])) if site1 in ref_ca else 999.0
        d2 = float(np.linalg.norm(xyz - ref_ca[site2])) if site2 in ref_ca else 999.0
        if min(d1, d2) <= BUILD_LOCAL_CA_RADIUS:
            local_keys.append(key)
    if local_keys:
        local_rmsd = float(
            np.sqrt(np.mean([disp[k] ** 2 for k in local_keys if k in disp]))
        )
    else:
        local_rmsd = global_rmsd

    return {
        "ss_distance": round(ss, 4),
        "cb_sg1": round(cb_sg1, 4),
        "cb_sg2": round(cb_sg2, 4),
        "angle1": round(angle1, 2),
        "angle2": round(angle2, 2),
        "chi1": round(chi1, 2),
        "chi2": round(chi2, 2),
        "chi3": round(chi3, 2),
        "chi2_prime": round(chi2p, 2),
        "chi1_prime": round(chi1p, 2),
        "chi3_deviation": round(chi3_dev, 2),
        "clash_count": int(clash_count),
        "min_env_distance": min_env,
        "global_ca_rmsd": round(global_rmsd, 4),
        "local_ca_rmsd": round(local_rmsd, 4),
        "site1_ca_displacement": None if site1_disp is None else round(site1_disp, 4),
        "site2_ca_displacement": None if site2_disp is None else round(site2_disp, 4),
        "maximum_ca_displacement": round(max(disp.values()), 4),
    }


def build_pass(pyrosetta_result: dict[str, Any], geom: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons = []
    if pyrosetta_result.get("error"):
        reasons.append("pyrosetta_error")
    if not pyrosetta_result.get("site1_is_cys"):
        reasons.append("site1_not_cys")
    if not pyrosetta_result.get("site2_is_cys"):
        reasons.append("site2_not_cys")
    if not pyrosetta_result.get("new_disulfide_bonded"):
        reasons.append("not_bonded")
    if not pyrosetta_result.get("native_disulfides_preserved"):
        reasons.append("native_disulfide_lost")
    ss = geom.get("ss_distance")
    if ss is None or not (BUILD_SS_MIN <= ss <= BUILD_SS_MAX):
        reasons.append("ss_distance")
    if geom.get("chi3_deviation", 999) > BUILD_CHI3_DEVIATION_MAX:
        reasons.append("chi3")
    if geom.get("clash_count", 1) != 0:
        reasons.append("clash")
    for key in ("cb_sg1", "cb_sg2"):
        value = geom.get(key)
        if value is None or not (BUILD_CB_SG_MIN <= value <= BUILD_CB_SG_MAX):
            reasons.append(key)
    return not reasons, reasons


def _ss_to_target(geom: dict[str, Any] | None) -> float:
    ss = (geom or {}).get("ss_distance")
    if ss is None:
        return 999.0
    return abs(float(ss) - SS_DISTANCE_TARGET)


def select_best_attempt(attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """优先已通过；否则已成键且保留原生二硫；同档取更接近 2.03 Å 的。"""
    if not attempts:
        return None
    passing = [row for row in attempts if row.get("build_pass")]
    if passing:
        return min(passing, key=lambda row: _ss_to_target(row.get("geometry")))

    def rank(row: dict[str, Any]) -> tuple[int, float]:
        pyro = row.get("pyrosetta") or {}
        if pyro.get("new_disulfide_bonded") and pyro.get("native_disulfides_preserved"):
            return (0, _ss_to_target(row.get("geometry")))
        if pyro.get("new_disulfide_bonded"):
            return (1, _ss_to_target(row.get("geometry")))
        return (2, _ss_to_target(row.get("geometry")))

    return min(attempts, key=rank)


def apply_best_attempt(record: dict[str, Any]) -> dict[str, Any]:
    best = select_best_attempt(record.get("attempts") or [])
    if best is None:
        record["build_pass"] = False
        record["failure_reasons"] = record.get("failure_reasons") or ["missing_worker_result"]
        record["selected_attempt"] = None
        return record
    record["build_pass"] = bool(best.get("build_pass"))
    record["failure_reasons"] = list(best.get("failure_reasons") or [])
    record["selected_attempt"] = best.get("backbone_mode")
    return record


def _run_worker(payload: dict[str, Any], timeout: int | None = None) -> dict[str, Any] | list[dict[str, Any]]:
    n_jobs = len(payload["jobs"]) if payload.get("jobs") else 1
    if timeout is None:
        timeout = max(900, 480 * n_jobs)
    if not Path(PYROSETTA_PYTHON).is_file():
        raise RuntimeError(f"找不到 PyRosetta: {PYROSETTA_PYTHON}")
    proc = subprocess.run(
        [PYROSETTA_PYTHON, str(WORKER)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if proc.returncode != 0 or not lines:
        raise RuntimeError(
            "PyRosetta worker 失败: "
            + ((proc.stderr or proc.stdout)[-4000:] or f"exit {proc.returncode}")
        )
    data = json.loads(lines[-1])
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    return data


def _pair_slug(pair_id: str) -> str:
    return pair_id.replace(":", "_")


def _site_tuple(pair: dict[str, Any], which: str) -> tuple[str, int]:
    site = pair[which]
    return str(site["structure_chain"]), int(site["sequence_index"])


def _record_attempt(
    worker: dict[str, Any],
    site1: tuple[str, int],
    site2: tuple[str, int],
    *,
    mode: str,
) -> dict[str, Any]:
    built_pdb = Path(worker.get("out_pdb") or "")
    ref_pdb = Path(worker.get("reference_pdb") or "")
    geom: dict[str, Any] = {}
    try:
        if worker.get("new_disulfide_bonded") and built_pdb.is_file() and ref_pdb.is_file():
            geom = evaluate_built_geometry(built_pdb, ref_pdb, site1, site2)
        elif built_pdb.is_file() and ref_pdb.is_file():
            try:
                geom = evaluate_built_geometry(built_pdb, ref_pdb, site1, site2)
            except Exception as exc:  # noqa: BLE001
                geom = {"error": str(exc)}
        ok, reasons = build_pass(worker, geom)
        if worker.get("mover_ok") is False and not worker.get("new_disulfide_bonded"):
            if "not_bonded" not in reasons:
                reasons.append("not_bonded")
            ok = False
    except Exception as exc:  # noqa: BLE001
        geom = {"error": str(exc)}
        ok, reasons = False, ["geometry_eval_failed"]
        if worker.get("error"):
            reasons.append("pyrosetta_error")
    return {
        "backbone_mode": mode,
        "relax_bb": mode == "relaxbb",
        "build_pass": ok,
        "failure_reasons": reasons,
        "pyrosetta": worker,
        "geometry": geom,
        "output_structure": str(built_pdb) if built_pdb else None,
    }


def _virtual_best_for_model(pair: dict[str, Any], model_name: str) -> dict[str, Any] | None:
    for row in pair.get("models") or []:
        if row.get("model") == model_name:
            best = row.get("best")
            return best if isinstance(best, dict) else None
    return None


def _jobs_for_pairs(
    pairs: list[dict[str, Any]],
    out_dir: Path,
    model_stem: str,
    model_name: str,
    *,
    relax_bb: bool,
) -> list[dict[str, Any]]:
    mode = "relaxbb" if relax_bb else "fixedbb"
    jobs = []
    for pair in pairs:
        slug = _pair_slug(pair["pair_id"])
        site1, site2 = _site_tuple(pair, "site1"), _site_tuple(pair, "site2")
        best = _virtual_best_for_model(pair, model_name)
        jobs.append(
            {
                "id": pair["pair_id"],
                "chain1": site1[0],
                "seq1": site1[1],
                "chain2": site2[0],
                "seq2": site2[1],
                "relax_bb": relax_bb,
                "out_pdb": str(out_dir / model_stem / f"{slug}_{mode}.pdb"),
                "reference_pdb": str(out_dir / model_stem / f"{slug}_{mode}_reference.pdb"),
                "sg1": None if not best else best.get("sg1"),
                "sg2": None if not best else best.get("sg2"),
                "ss_target": BUILD_SS_CONSTRAINT,
                "ss_sd": BUILD_SS_CONSTRAINT_SD,
                "angle_sd": BUILD_ANGLE_CONSTRAINT_SD,
            }
        )
    return jobs


def _build_pairs_on_model(
    input_pdb: Path,
    pairs: list[dict[str, Any]],
    model_name: str,
    out_dir: Path,
) -> list[dict[str, Any]]:
    """对一个结构上的多对位点先 fixed BB，失败的再 relax BB。单对失败不中断。"""
    model_stem = Path(model_name).stem
    (out_dir / model_stem).mkdir(parents=True, exist_ok=True)
    by_id = {pair["pair_id"]: pair for pair in pairs}
    fixed_jobs = _jobs_for_pairs(pairs, out_dir, model_stem, model_name, relax_bb=False)
    try:
        fixed_results = _run_worker({"pdb": str(input_pdb), "jobs": fixed_jobs})
        if isinstance(fixed_results, dict):
            fixed_results = [fixed_results]
    except Exception as exc:  # noqa: BLE001
        return [
            {
                "pair_id": pair["pair_id"],
                "model_name": model_name,
                "site1": pair["site1"],
                "site2": pair["site2"],
                "build_pass": False,
                "failure_reasons": ["worker_failed"],
                "error": str(exc),
                "attempts": [],
            }
            for pair in pairs
        ]

    records = {}
    retry = []
    for worker in fixed_results:
        pair_id = worker.get("id")
        if pair_id not in by_id:
            continue
        pair = by_id[pair_id]
        site1, site2 = _site_tuple(pair, "site1"), _site_tuple(pair, "site2")
        attempt = _record_attempt(worker, site1, site2, mode="fixedbb")
        records[pair["pair_id"]] = {
            "pair_id": pair["pair_id"],
            "model_name": model_name,
            "site1": pair["site1"],
            "site2": pair["site2"],
            "attempts": [attempt],
            "build_pass": attempt["build_pass"],
            "failure_reasons": attempt["failure_reasons"],
        }
        apply_best_attempt(records[pair["pair_id"]])
        if not records[pair["pair_id"]]["build_pass"]:
            retry.append(pair)

    for pair in pairs:
        if pair["pair_id"] not in records:
            records[pair["pair_id"]] = {
                "pair_id": pair["pair_id"],
                "model_name": model_name,
                "site1": pair["site1"],
                "site2": pair["site2"],
                "attempts": [],
                "build_pass": False,
                "failure_reasons": ["missing_worker_result"],
            }
            retry.append(pair)

    if retry:
        relax_jobs = _jobs_for_pairs(retry, out_dir, model_stem, model_name, relax_bb=True)
        try:
            relax_results = _run_worker({"pdb": str(input_pdb), "jobs": relax_jobs})
            if isinstance(relax_results, dict):
                relax_results = [relax_results]
        except Exception as exc:  # noqa: BLE001
            for pair in retry:
                records[pair["pair_id"]]["attempts"].append(
                    {
                        "backbone_mode": "relaxbb",
                        "relax_bb": True,
                        "build_pass": False,
                        "failure_reasons": ["worker_failed"],
                        "pyrosetta": {"error": str(exc)},
                        "geometry": {},
                        "output_structure": None,
                    }
                )
            relax_results = []
        for worker in relax_results:
            pair_id = worker.get("id")
            if pair_id not in by_id:
                continue
            pair = by_id[pair_id]
            site1, site2 = _site_tuple(pair, "site1"), _site_tuple(pair, "site2")
            attempt = _record_attempt(worker, site1, site2, mode="relaxbb")
            records[pair["pair_id"]]["attempts"].append(attempt)
        for pair in retry:
            apply_best_attempt(records[pair["pair_id"]])
    return [records[pair["pair_id"]] for pair in pairs]


def summarize_pair_builds(pair: dict[str, Any], model_records: list[dict[str, Any]]) -> dict[str, Any]:
    n_pass = sum(1 for row in model_records if row.get("build_pass"))
    return {
        "pair_id": pair["pair_id"],
        "site1": pair["site1"],
        "site2": pair["site2"],
        "n_models_passed": n_pass,
        "n_models": len(model_records),
        "pair_build_pass": n_pass >= MINIMUM_MODELS_PASSED,
        "models": model_records,
    }


def run_build_all(
    fasta_text: str,
    structure_paths: list[Path] | Path,
    out_dir: Path,
    *,
    geometry_report: dict[str, Any] | None = None,
    ensemble: dict[str, Any] | None = None,
    pair_ids: list[str] | None = None,
    model_names: list[str] | None = None,
) -> dict[str, Any]:
    """对虚拟几何通过的候选 × 全部模型做显式成键；单对失败只记录原因。"""
    ensemble_report = ensemble or run_ensemble_alignment(fasta_text, structure_paths)
    mask = run_site_mask(fasta_text, structure_paths, ensemble=ensemble_report)
    pair_report = run_pair_screen(fasta_text, structure_paths, site_table=mask)
    geo = geometry_report or run_geometry_search(fasta_text, structure_paths, pair_report=pair_report)
    pairs = list(geo.get("pairs") or [])
    if pair_ids is not None:
        wanted = set(pair_ids)
        pairs = [pair for pair in pairs if pair["pair_id"] in wanted]
    if not pairs:
        raise ValueError("没有要建模的候选")

    paths = [Path(p) for p in ensemble_report["structure_paths"]]
    if model_names is not None:
        wanted_models = set(model_names)
        paths = [path for path in paths if path.name in wanted_models]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    by_pair: dict[str, list[dict[str, Any]]] = {pair["pair_id"]: [] for pair in pairs}
    for cif_path in paths:
        input_pdb = cif_to_pdb(cif_path, out / "inputs" / f"{cif_path.stem}.pdb")
        try:
            model_rows = _build_pairs_on_model(input_pdb, pairs, cif_path.name, out)
        except Exception as exc:  # noqa: BLE001
            model_rows = [
                {
                    "pair_id": pair["pair_id"],
                    "model_name": cif_path.name,
                    "site1": pair["site1"],
                    "site2": pair["site2"],
                    "build_pass": False,
                    "failure_reasons": ["model_failed"],
                    "error": str(exc),
                    "attempts": [],
                }
                for pair in pairs
            ]
        for row in model_rows:
            by_pair[row["pair_id"]].append(row)

    summaries = [summarize_pair_builds(pair, by_pair[pair["pair_id"]]) for pair in pairs]
    result = {
        "n_input_pairs": len(pairs),
        "n_models": len(paths),
        "n_pair_pass": sum(1 for row in summaries if row["pair_build_pass"]),
        "minimum_models_passed": MINIMUM_MODELS_PASSED,
        "pairs": summaries,
    }
    (out / "build.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def _select_pilot(geo: dict[str, Any], ensemble: dict[str, Any]) -> tuple[dict[str, Any], str, Path]:
    if not geo.get("pairs"):
        raise ValueError("没有虚拟几何通过的候选")
    pair = min(
        geo["pairs"],
        key=lambda row: row.get("median_best_score") if row.get("median_best_score") is not None else 1e9,
    )
    medoid_name = ensemble["medoid_name"]
    paths = [Path(p) for p in ensemble["structure_paths"]]
    match = next((path for path in paths if path.name == medoid_name), None)
    if match is None:
        raise ValueError(f"找不到 medoid 结构 {medoid_name}")
    return pair, medoid_name, match


def run_build_pilot(
    fasta_text: str,
    structure_paths: list[Path] | Path,
    out_dir: Path,
    *,
    geometry_report: dict[str, Any] | None = None,
    ensemble: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """兼容入口：只建几何最好的一对 × medoid。批量请用 run_build_all。"""
    ensemble_report = ensemble or run_ensemble_alignment(fasta_text, structure_paths)
    mask = run_site_mask(fasta_text, structure_paths, ensemble=ensemble_report)
    pair_report = run_pair_screen(fasta_text, structure_paths, site_table=mask)
    geo = geometry_report or run_geometry_search(fasta_text, structure_paths, pair_report=pair_report)
    pair, model_name, _cif = _select_pilot(geo, ensemble_report)
    batch = run_build_all(
        fasta_text,
        structure_paths,
        out_dir,
        geometry_report=geo,
        ensemble=ensemble_report,
        pair_ids=[pair["pair_id"]],
        model_names=[model_name],
    )
    row = batch["pairs"][0]
    model = row["models"][0]
    result = {
        "pair_id": row["pair_id"],
        "model_name": model["model_name"],
        "site1": row["site1"],
        "site2": row["site2"],
        "attempts": model.get("attempts") or [],
        "build_pass": model.get("build_pass", False),
        "batch": batch,
    }
    (Path(out_dir) / "pilot.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result
