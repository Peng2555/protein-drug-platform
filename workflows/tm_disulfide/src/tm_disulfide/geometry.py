"""虚拟 Cys SG 几何搜索：主链与 CA–CB 方向不变。"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from tm_disulfide.constants import (
    BACKBONE_ATOMS,
    CA_CB_SG_ANGLE,
    CB_SG_BOND_LENGTH,
    CB_SG_SG_ANGLE_MAX,
    CB_SG_SG_ANGLE_MIN,
    CB_SG_SG_ANGLE_TARGET,
    CHI1_DEVIATION_MAX,
    CHI1_TARGETS,
    CHI3_DEVIATION_MAX,
    CHI3_TARGETS,
    GEOMETRY_TOP_N,
    MINIMUM_MODELS_PASSED,
    SG_CLASH_DISTANCE,
    SG_ROTATION_STEP,
    SS_DISTANCE_MAX,
    SS_DISTANCE_MIN,
    SS_DISTANCE_TARGET,
    THREE_TO_ONE,
)
from tm_disulfide.pairs import run_pair_screen
from tm_disulfide.qc import _pick_atom

_KEPT_ATOMS = set(BACKBONE_ATOMS) | {"CB"}


def _as_xyz(atom) -> np.ndarray | None:
    pos = atom.pos
    xyz = np.array([float(pos.x), float(pos.y), float(pos.z)], dtype=float)
    if not np.all(np.isfinite(xyz)):
        return None
    return xyz


def normalize(vector: np.ndarray) -> np.ndarray:
    arr = np.asarray(vector, dtype=float)
    norm = float(np.linalg.norm(arr))
    if norm < 1e-8:
        raise ValueError("零向量无法归一化")
    return arr / norm


def circular_difference(angle1: float, angle2: float) -> float:
    return abs((float(angle1) - float(angle2) + 180.0) % 360.0 - 180.0)


def bond_angle(left: np.ndarray, vertex: np.ndarray, right: np.ndarray) -> float:
    a = normalize(left - vertex)
    b = normalize(right - vertex)
    cosine = float(np.clip(np.dot(a, b), -1.0, 1.0))
    return float(np.degrees(np.arccos(cosine)))


def dihedral(p0: np.ndarray, p1: np.ndarray, p2: np.ndarray, p3: np.ndarray) -> float:
    b0 = p0 - p1
    b1 = p2 - p1
    b2 = p3 - p2
    axis = normalize(b1)
    v = b0 - np.dot(b0, axis) * axis
    w = b2 - np.dot(b2, axis) * axis
    x = float(np.dot(v, w))
    y = float(np.dot(np.cross(axis, v), w))
    return float(np.degrees(np.arctan2(y, x)))


def _perp_basis(axis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    unit = normalize(axis)
    reference = np.array([1.0, 0.0, 0.0])
    if abs(float(np.dot(unit, reference))) > 0.9:
        reference = np.array([0.0, 1.0, 0.0])
    basis1 = normalize(np.cross(unit, reference))
    basis2 = np.cross(unit, basis1)
    return basis1, basis2


def virtual_sg_positions(ca: np.ndarray, cb: np.ndarray) -> np.ndarray:
    """绕 CA–CB 轴每隔 SG_ROTATION_STEP 度放一个 SG。"""
    axis = normalize(np.asarray(ca, dtype=float) - np.asarray(cb, dtype=float))
    basis1, basis2 = _perp_basis(axis)
    theta = math.radians(CA_CB_SG_ANGLE)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    angles = np.arange(0.0, 360.0, SG_ROTATION_STEP)
    phis = np.radians(angles)
    radial = np.outer(np.cos(phis), basis1) + np.outer(np.sin(phis), basis2)
    vectors = CB_SG_BOND_LENGTH * (cos_t * axis + sin_t * radial)
    return np.asarray(cb, dtype=float) + vectors


def min_deviation(angle: float, targets: tuple[float, ...]) -> float:
    return min(circular_difference(angle, target) for target in targets)


def geometry_score(
    ss_distance: float,
    angle1: float,
    angle2: float,
    chi3_deviation: float,
    chi1_deviation_site1: float,
    chi1_deviation_site2: float,
) -> float:
    return float(
        ((ss_distance - SS_DISTANCE_TARGET) / 0.20) ** 2
        + ((angle1 - CB_SG_SG_ANGLE_TARGET) / 15.0) ** 2
        + ((angle2 - CB_SG_SG_ANGLE_TARGET) / 15.0) ** 2
        + (chi3_deviation / 30.0) ** 2
        + (chi1_deviation_site1 / 40.0) ** 2
        + (chi1_deviation_site2 / 40.0) ** 2
    )


def _atom_name(atom) -> str:
    return atom.name.strip()


def _is_hydrogen(atom) -> bool:
    element = str(getattr(atom.element, "name", atom.element) or "").upper()
    return element in {"H", "D"} or _atom_name(atom).startswith("H")


def extract_pair_frames(structure, key1: tuple[str, int], key2: tuple[str, int]) -> dict[str, Any]:
    frames: dict[tuple[str, int], dict[str, Any]] = {}
    env: list[np.ndarray] = []
    wanted = {key1, key2}
    for chain in structure[0]:
        seq_index = 0
        for res in chain:
            aa = THREE_TO_ONE.get(res.name)
            if aa is None:
                continue
            seq_index += 1
            key = (chain.name, seq_index)
            if key in wanted:
                coords = {}
                for atom in res:
                    if _is_hydrogen(atom):
                        continue
                    name = _atom_name(atom)
                    xyz = _as_xyz(atom)
                    if xyz is None:
                        continue
                    if name in _KEPT_ATOMS:
                        coords[name] = xyz
                frames[key] = {"amino_acid": aa, **coords}
            else:
                for atom in res:
                    if _is_hydrogen(atom):
                        continue
                    xyz = _as_xyz(atom)
                    if xyz is not None:
                        env.append(xyz)
    missing = [key for key in wanted if key not in frames]
    if missing:
        raise ValueError(f"结构中缺少位点 {missing}")
    for key, frame in frames.items():
        for name in ("N", "CA", "C", "O", "CB"):
            if name not in frame:
                raise ValueError(f"{key} 缺原子 {name}")
    return {"frames": frames, "env": np.array(env, dtype=float) if env else np.zeros((0, 3))}


def _min_env_distance(sg: np.ndarray, env: np.ndarray) -> float:
    if env.size == 0:
        return float("inf")
    delta = env - sg
    return float(np.sqrt(np.min(np.sum(delta * delta, axis=1))))


def search_sg_conformers(frame1: dict[str, Any], frame2: dict[str, Any], env: np.ndarray) -> dict[str, Any]:
    """对一对残基搜索虚拟 SG 组合；先距离，再角/χ，最后碰撞。"""
    sg1 = virtual_sg_positions(frame1["CA"], frame1["CB"])
    sg2 = virtual_sg_positions(frame2["CA"], frame2["CB"])
    n_total = int(sg1.shape[0] * sg2.shape[0])
    delta = sg1[:, None, :] - sg2[None, :, :]
    ss = np.sqrt(np.sum(delta * delta, axis=2))
    ii, jj = np.nonzero((ss >= SS_DISTANCE_MIN) & (ss <= SS_DISTANCE_MAX))
    n_ss = int(ii.size)

    hits: list[dict[str, Any]] = []
    n_geometry = 0
    n_clash_free = 0
    cb1, ca1, n1 = frame1["CB"], frame1["CA"], frame1["N"]
    cb2, ca2, n2 = frame2["CB"], frame2["CA"], frame2["N"]
    for i, j in zip(ii.tolist(), jj.tolist()):
        p1 = sg1[i]
        p2 = sg2[j]
        dist = float(ss[i, j])
        angle1 = bond_angle(cb1, p1, p2)
        angle2 = bond_angle(p1, p2, cb2)
        if not (CB_SG_SG_ANGLE_MIN <= angle1 <= CB_SG_SG_ANGLE_MAX):
            continue
        if not (CB_SG_SG_ANGLE_MIN <= angle2 <= CB_SG_SG_ANGLE_MAX):
            continue
        chi1 = dihedral(n1, ca1, cb1, p1)
        chi2 = dihedral(ca1, cb1, p1, p2)
        chi3 = dihedral(cb1, p1, p2, cb2)
        chi2p = dihedral(p1, p2, cb2, ca2)
        chi1p = dihedral(p2, cb2, ca2, n2)
        chi3_dev = min_deviation(chi3, CHI3_TARGETS)
        chi1_dev = min_deviation(chi1, CHI1_TARGETS)
        chi1p_dev = min_deviation(chi1p, CHI1_TARGETS)
        if chi3_dev > CHI3_DEVIATION_MAX:
            continue
        if chi1_dev > CHI1_DEVIATION_MAX or chi1p_dev > CHI1_DEVIATION_MAX:
            continue
        n_geometry += 1
        min1 = _min_env_distance(p1, env)
        min2 = _min_env_distance(p2, env)
        clash_count = int(min1 < SG_CLASH_DISTANCE) + int(min2 < SG_CLASH_DISTANCE)
        if clash_count:
            continue
        n_clash_free += 1
        score = geometry_score(dist, angle1, angle2, chi3_dev, chi1_dev, chi1p_dev)
        hits.append(
            {
                "score": round(score, 4),
                "ss": round(dist, 4),
                "angle1": round(angle1, 2),
                "angle2": round(angle2, 2),
                "chi1": round(chi1, 2),
                "chi2": round(chi2, 2),
                "chi3": round(chi3, 2),
                "chi2_prime": round(chi2p, 2),
                "chi1_prime": round(chi1p, 2),
                "chi3_deviation": round(chi3_dev, 2),
                "chi1_deviation_site1": round(chi1_dev, 2),
                "chi1_deviation_site2": round(chi1p_dev, 2),
                "min_env_site1": None if math.isinf(min1) else round(min1, 3),
                "min_env_site2": None if math.isinf(min2) else round(min2, 3),
                "sg1": [round(float(v), 3) for v in p1],
                "sg2": [round(float(v), 3) for v in p2],
            }
        )
    hits.sort(key=lambda row: row["score"])
    best = hits[0] if hits else None
    reasons: list[str] = []
    if n_ss == 0:
        reasons.append("no_ss_distance")
    elif n_geometry == 0:
        reasons.append("no_angle_or_chi")
    elif n_clash_free == 0:
        reasons.append("clash")
    return {
        "n_total": n_total,
        "n_ss": n_ss,
        "n_geometry": n_geometry,
        "n_clash_free": n_clash_free,
        "geometry_pass": n_clash_free > 0,
        "failure_reasons": reasons,
        "best": best,
        "top": hits[:GEOMETRY_TOP_N],
    }


def _site_from_pair(pair: dict[str, Any], which: str) -> tuple[str, int]:
    site = pair[which]
    return str(site["structure_chain"]), int(site["sequence_index"])


def evaluate_pair_on_structures(
    structure_paths: list[Path],
    site1: tuple[str, int],
    site2: tuple[str, int],
    *,
    pair_meta: dict[str, Any] | None = None,
    model_names: list[str] | None = None,
) -> dict[str, Any]:
    import gemmi

    paths = [Path(path) for path in structure_paths]
    names = model_names or [path.name for path in paths]
    models = []
    n_pass = 0
    scores = []
    clash_free = []
    for path, name in zip(paths, names):
        structure = gemmi.read_structure(str(path))
        extracted = extract_pair_frames(structure, site1, site2)
        result = search_sg_conformers(
            extracted["frames"][site1],
            extracted["frames"][site2],
            extracted["env"],
        )
        result["model"] = name
        models.append(result)
        if result["geometry_pass"]:
            n_pass += 1
            scores.append(result["best"]["score"])
            clash_free.append(result["n_clash_free"])
    pair_pass = n_pass >= MINIMUM_MODELS_PASSED
    summary = {
        "pair_id": f"{site1[0]}:{site1[1]}-{site2[0]}:{site2[1]}",
        "site1": {"structure_chain": site1[0], "sequence_index": site1[1]},
        "site2": {"structure_chain": site2[0], "sequence_index": site2[1]},
        "n_models_passed": n_pass,
        "n_models": len(paths),
        "pass_fraction": round(n_pass / len(paths), 4) if paths else 0.0,
        "pair_geometry_pass": pair_pass,
        "median_best_score": None if not scores else round(float(np.median(scores)), 4),
        "max_best_score": None if not scores else round(float(max(scores)), 4),
        "min_clash_free_count": None if not clash_free else int(min(clash_free)),
        "models": models,
    }
    if pair_meta:
        summary["site1"].update({k: pair_meta["site1"].get(k) for k in ("amino_acid", "kabat_number")})
        summary["site2"].update({k: pair_meta["site2"].get(k) for k in ("amino_acid", "kabat_number")})
        summary["sequence_separation"] = pair_meta.get("sequence_separation")
    return summary


def run_geometry_search(
    fasta_text: str,
    structure_paths: list[Path] | Path,
    *,
    pair_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """对距离粗筛通过的残基对做虚拟 SG 几何搜索。"""
    from tm_disulfide.qc import discover_boltz_models

    report = pair_report or run_pair_screen(fasta_text, structure_paths)
    if isinstance(structure_paths, Path):
        paths = discover_boltz_models(structure_paths)
    else:
        paths = [Path(path) for path in structure_paths]
    passed = []
    for pair in report.get("pairs") or []:
        site1 = _site_from_pair(pair, "site1")
        site2 = _site_from_pair(pair, "site2")
        evaluated = evaluate_pair_on_structures(paths, site1, site2, pair_meta=pair)
        if evaluated["pair_geometry_pass"]:
            passed.append(evaluated)
    return {
        "n_input_pairs": len(report.get("pairs") or []),
        "n_passed": len(passed),
        "thresholds": {
            "ss_distance": [SS_DISTANCE_MIN, SS_DISTANCE_MAX],
            "cb_sg_sg_angle": [CB_SG_SG_ANGLE_MIN, CB_SG_SG_ANGLE_MAX],
            "chi3_deviation_max": CHI3_DEVIATION_MAX,
            "chi1_deviation_max": CHI1_DEVIATION_MAX,
            "sg_clash_distance": SG_CLASH_DISTANCE,
            "minimum_models_passed": MINIMUM_MODELS_PASSED,
        },
        "pairs": passed,
    }
