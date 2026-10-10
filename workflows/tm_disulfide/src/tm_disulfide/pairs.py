"""可设计位点的 CA/CB 距离粗筛，并要求侧链面对面；不生成 SG。"""

from __future__ import annotations

import math
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np

from tm_disulfide.constants import (
    MAXIMUM_CA_CB_DOT,
    MAXIMUM_CA_DISTANCE,
    MAXIMUM_CA_DISTANCE_ANY,
    MAXIMUM_CB_DISTANCE,
    MAXIMUM_CB_DISTANCE_ANY,
    MAXIMUM_CB_TOWARD_ANGLE,
    MINIMUM_MODELS_PASSED,
    MINIMUM_SEQUENCE_SEPARATION,
    THREE_TO_ONE,
)
from tm_disulfide.qc import _pick_atom
from tm_disulfide.sites import run_site_mask


def _atom_xyz(atom) -> np.ndarray | None:
    pos = atom.pos
    xyz = np.array([float(pos.x), float(pos.y), float(pos.z)], dtype=float)
    if not np.all(np.isfinite(xyz)):
        return None
    return xyz


def extract_ca_cb(structure) -> dict[tuple[str, int], dict[str, Any]]:
    table: dict[tuple[str, int], dict[str, Any]] = {}
    for chain in structure[0]:
        seq_index = 0
        for res in chain:
            aa = THREE_TO_ONE.get(res.name)
            if aa is None:
                continue
            seq_index += 1
            ca = _pick_atom(res, "CA")
            cb = _pick_atom(res, "CB")
            table[(chain.name, seq_index)] = {
                "amino_acid": aa,
                "ca": None if ca is None else _atom_xyz(ca),
                "cb": None if cb is None else _atom_xyz(cb),
            }
    return table


def _site_key(row: dict[str, Any]) -> tuple[str, int]:
    return (str(row["structure_chain"]), int(row["sequence_index"]))


def _pair_order(left: dict[str, Any], right: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if _site_key(left) <= _site_key(right):
        return left, right
    return right, left


def sequence_separation(left: dict[str, Any], right: dict[str, Any]) -> int | None:
    """同链返回 |i-j|；链间没有序列间隔，返回 None。"""
    if left["structure_chain"] != right["structure_chain"]:
        return None
    return abs(int(left["sequence_index"]) - int(right["sequence_index"]))


def _distance(a: np.ndarray, b: np.ndarray) -> float:
    delta = a - b
    return float(np.linalg.norm(delta))


def _unit_or_none(vector: np.ndarray) -> np.ndarray | None:
    arr = np.asarray(vector, dtype=float)
    norm = float(np.linalg.norm(arr))
    if not math.isfinite(norm) or norm < 1e-8:
        return None
    return arr / norm


def facing_metrics(
    ca1: np.ndarray,
    cb1: np.ndarray,
    ca2: np.ndarray,
    cb2: np.ndarray,
) -> dict[str, Any]:
    """两边 CA→CB 是否朝向对方：夹角半球 + 两侧链不完全同向。"""
    u_cb1 = _unit_or_none(np.asarray(cb1, dtype=float) - np.asarray(ca1, dtype=float))
    u_cb2 = _unit_or_none(np.asarray(cb2, dtype=float) - np.asarray(ca2, dtype=float))
    u_to2 = _unit_or_none(np.asarray(ca2, dtype=float) - np.asarray(ca1, dtype=float))
    u_to1 = _unit_or_none(np.asarray(ca1, dtype=float) - np.asarray(ca2, dtype=float))
    if u_cb1 is None or u_cb2 is None or u_to2 is None or u_to1 is None:
        return {
            "toward_angle_1": None,
            "toward_angle_2": None,
            "ca_cb_dot": None,
            "pass": False,
            "reasons": ["facing_undefined"],
        }
    ang1 = float(np.degrees(np.arccos(float(np.clip(np.dot(u_cb1, u_to2), -1.0, 1.0)))))
    ang2 = float(np.degrees(np.arccos(float(np.clip(np.dot(u_cb2, u_to1), -1.0, 1.0)))))
    ca_cb_dot = float(np.dot(u_cb1, u_cb2))
    reasons: list[str] = []
    if ang1 > MAXIMUM_CB_TOWARD_ANGLE or ang2 > MAXIMUM_CB_TOWARD_ANGLE:
        reasons.append("cb_not_toward")
    if ca_cb_dot > MAXIMUM_CA_CB_DOT:
        reasons.append("cb_not_antiparallel")
    return {
        "toward_angle_1": round(ang1, 4),
        "toward_angle_2": round(ang2, 4),
        "ca_cb_dot": round(ca_cb_dot, 4),
        "pass": not reasons,
        "reasons": reasons,
    }


def _stats(values: list[float]) -> dict[str, float]:
    arr = np.asarray(values, dtype=float)
    return {
        "min": round(float(arr.min()), 4),
        "max": round(float(arr.max()), 4),
        "mean": round(float(arr.mean()), 4),
        "median": round(float(np.median(arr)), 4),
        "std": round(float(arr.std(ddof=0)), 4),
    }


def screen_pairs(
    structure_paths: list[Path],
    eligible_rows: list[dict[str, Any]],
    *,
    model_names: list[str] | None = None,
) -> dict[str, Any]:
    """对允许设计的位点做不重复两两组合，用五套结构的 CA/CB 距离和面对面朝向粗筛。"""
    import gemmi

    sites = sorted(eligible_rows, key=_site_key)
    keys = [_site_key(row) for row in sites]
    if len(keys) != len(set(keys)):
        raise ValueError("eligible 位点有重复")
    n_eligible = len(sites)
    n_combinations = n_eligible * (n_eligible - 1) // 2
    paths = [Path(path) for path in structure_paths]
    if not paths:
        raise ValueError("没有结构文件")
    tables = [extract_ca_cb(gemmi.read_structure(str(path))) for path in paths]
    names = model_names or [path.name for path in paths]

    n_close_seq = 0
    passed: list[dict[str, Any]] = []
    for left_raw, right_raw in combinations(sites, 2):
        left, right = _pair_order(left_raw, right_raw)
        if _site_key(left) == _site_key(right):
            raise ValueError("出现自己与自己配对")
        sep = sequence_separation(left, right)
        if sep is not None and sep < MINIMUM_SEQUENCE_SEPARATION:
            n_close_seq += 1
            continue
        key_i, key_j = _site_key(left), _site_key(right)
        ca_dists: list[float] = []
        cb_dists: list[float] = []
        toward_max: list[float] = []
        ca_cb_dots: list[float] = []
        n_model_pass = 0
        per_model: list[dict[str, Any]] = []
        for model_index, table in enumerate(tables):
            rec_i = table.get(key_i)
            rec_j = table.get(key_j)
            if rec_i is None or rec_j is None:
                raise ValueError(f"{names[model_index]} 缺少位点 {key_i} 或 {key_j}")
            if rec_i["ca"] is None or rec_j["ca"] is None:
                raise ValueError(f"{names[model_index]} {key_i}-{key_j} 缺 CA")
            if rec_i["cb"] is None or rec_j["cb"] is None:
                raise ValueError(f"{names[model_index]} {key_i}-{key_j} 缺 CB，不能用 CA 代替")
            ca = _distance(rec_i["ca"], rec_j["ca"])
            cb = _distance(rec_i["cb"], rec_j["cb"])
            if not math.isfinite(ca) or not math.isfinite(cb):
                raise ValueError(f"{names[model_index]} {key_i}-{key_j} 距离非有限")
            face = facing_metrics(rec_i["ca"], rec_i["cb"], rec_j["ca"], rec_j["cb"])
            model_reasons: list[str] = []
            if ca > MAXIMUM_CA_DISTANCE:
                model_reasons.append("ca_distance")
            if cb > MAXIMUM_CB_DISTANCE:
                model_reasons.append("cb_distance")
            model_reasons.extend(face["reasons"])
            model_ok = not model_reasons
            if model_ok:
                n_model_pass += 1
            ca_dists.append(ca)
            cb_dists.append(cb)
            if face["toward_angle_1"] is not None and face["toward_angle_2"] is not None:
                toward_max.append(max(face["toward_angle_1"], face["toward_angle_2"]))
            if face["ca_cb_dot"] is not None:
                ca_cb_dots.append(face["ca_cb_dot"])
            per_model.append(
                {
                    "model": names[model_index],
                    "ca": round(ca, 4),
                    "cb": round(cb, 4),
                    "toward_angle_1": face["toward_angle_1"],
                    "toward_angle_2": face["toward_angle_2"],
                    "ca_cb_dot": face["ca_cb_dot"],
                    "pass": model_ok,
                    "reasons": model_reasons,
                }
            )
        ca_stats = _stats(ca_dists)
        cb_stats = _stats(cb_dists)
        reasons: list[str] = []
        if n_model_pass < MINIMUM_MODELS_PASSED:
            reasons.append("too_few_models")
        if ca_stats["max"] > MAXIMUM_CA_DISTANCE_ANY:
            reasons.append("ca_max")
        if cb_stats["max"] > MAXIMUM_CB_DISTANCE_ANY:
            reasons.append("cb_max")
        if reasons:
            continue
        passed.append(
            {
                "pair_id": f"{key_i[0]}:{key_i[1]}-{key_j[0]}:{key_j[1]}",
                "site1": {
                    "structure_chain": left["structure_chain"],
                    "sequence_index": left["sequence_index"],
                    "amino_acid": left.get("amino_acid"),
                    "kabat_number": left.get("kabat_number"),
                },
                "site2": {
                    "structure_chain": right["structure_chain"],
                    "sequence_index": right["sequence_index"],
                    "amino_acid": right.get("amino_acid"),
                    "kabat_number": right.get("kabat_number"),
                },
                "sequence_separation": sep,
                "ca": ca_stats,
                "cb": cb_stats,
                "facing": {
                    "toward_angle_max": _stats(toward_max) if toward_max else None,
                    "ca_cb_dot": _stats(ca_cb_dots) if ca_cb_dots else None,
                },
                "n_models_passed": n_model_pass,
                "n_models": len(tables),
                "pass_fraction": round(n_model_pass / len(tables), 4),
                "models": per_model,
            }
        )

    pair_ids = [row["pair_id"] for row in passed]
    if len(pair_ids) != len(set(pair_ids)):
        raise ValueError("通过的残基对有重复")
    return {
        "n_eligible": n_eligible,
        "n_combinations": n_combinations,
        "n_close_sequence": n_close_seq,
        "n_passed": len(passed),
        "thresholds": {
            "minimum_sequence_separation": MINIMUM_SEQUENCE_SEPARATION,
            "maximum_ca_distance": MAXIMUM_CA_DISTANCE,
            "maximum_cb_distance": MAXIMUM_CB_DISTANCE,
            "maximum_ca_distance_any": MAXIMUM_CA_DISTANCE_ANY,
            "maximum_cb_distance_any": MAXIMUM_CB_DISTANCE_ANY,
            "minimum_models_passed": MINIMUM_MODELS_PASSED,
            "maximum_cb_toward_angle": MAXIMUM_CB_TOWARD_ANGLE,
            "maximum_ca_cb_dot": MAXIMUM_CA_CB_DOT,
        },
        "pairs": passed,
    }


def run_pair_screen(
    fasta_text: str,
    structure_paths: list[Path] | Path,
    *,
    site_table: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """位点掩码之后：对 eligible 位置做 CA/CB 距离和面对面朝向粗筛。"""
    mask = site_table or run_site_mask(fasta_text, structure_paths)
    eligible = [row for row in mask["residues"] if row["eligible_for_design"]]
    raw_paths = mask.get("structure_paths") or structure_paths
    if isinstance(raw_paths, Path):
        from tm_disulfide.qc import discover_boltz_models

        paths = discover_boltz_models(raw_paths)
    else:
        paths = [Path(path) for path in raw_paths]
    result = screen_pairs(paths, eligible)
    result["n_site_residues"] = mask["n_residues"]
    return result
