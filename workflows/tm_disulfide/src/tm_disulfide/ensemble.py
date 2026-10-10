"""把多套 Boltz2 模型叠到同一坐标系，并计算残基 CA 波动。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from tm_disulfide.constants import CORE_RMSF_DROP_FRACTION, MIN_ALIGNMENT_CA, THREE_TO_ONE
from tm_disulfide.qc import _pick_atom, run_structure_qc


def _as_gemmi_transform(rotation: np.ndarray, translation: np.ndarray):
    import gemmi

    transform = gemmi.Transform()
    transform.mat.fromlist(np.asarray(rotation, dtype=float).tolist())
    transform.vec.fromlist(np.asarray(translation, dtype=float).tolist())
    return transform


def _identity_rotation_translation() -> tuple[np.ndarray, np.ndarray]:
    return np.eye(3, dtype=float), np.zeros(3, dtype=float)


def kabsch_superpose(target: np.ndarray, mobile: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """求把 mobile CA 叠到 target 上的刚体变换（镜像校正后的 Kabsch）。"""
    target = np.asarray(target, dtype=float)
    mobile = np.asarray(mobile, dtype=float)
    if len(target) < MIN_ALIGNMENT_CA:
        raise ValueError(f"叠合至少需要 {MIN_ALIGNMENT_CA} 个 CA")
    mobile_center = mobile.mean(axis=0)
    target_center = target.mean(axis=0)
    centered_mobile = mobile - mobile_center
    centered_target = target - target_center
    covariance = centered_mobile.T @ centered_target
    u, _singular, vt = np.linalg.svd(covariance)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt = vt.copy()
        vt[-1] *= -1
        rotation = vt.T @ u.T
    translation = target_center - mobile_center @ rotation.T
    aligned = mobile @ rotation.T + translation
    rmsd = float(np.sqrt(np.mean(np.sum((aligned - target) ** 2, axis=1))))
    return rotation, translation, rmsd


def raw_rmsd(left: np.ndarray, right: np.ndarray) -> float:
    delta = np.asarray(left, dtype=float) - np.asarray(right, dtype=float)
    return float(np.sqrt(np.mean(np.sum(delta * delta, axis=1))))


def _extract_ca(structure) -> dict[tuple[str, int], tuple[str, np.ndarray]]:
    table: dict[tuple[str, int], tuple[str, np.ndarray]] = {}
    for chain in structure[0]:
        seq_index = 0
        for res in chain:
            aa = THREE_TO_ONE.get(res.name)
            if aa is None:
                continue
            seq_index += 1
            ca = _pick_atom(res, "CA")
            if ca is None:
                continue
            pos = ca.pos
            table[(chain.name, seq_index)] = (
                aa,
                np.array([float(pos.x), float(pos.y), float(pos.z)], dtype=float),
            )
    return table


def _common_keys(ca_tables: list[dict[tuple[str, int], tuple[str, np.ndarray]]]) -> list[tuple[str, int]]:
    keys = set(ca_tables[0])
    for table in ca_tables[1:]:
        keys &= set(table)
    common: list[tuple[str, int]] = []
    for key in sorted(keys, key=lambda item: (item[0], item[1])):
        amino = ca_tables[0][key][0]
        if all(table[key][0] == amino for table in ca_tables):
            common.append(key)
    if len(common) < MIN_ALIGNMENT_CA:
        raise ValueError("共同 CA 不足，无法叠合")
    return common


def _stack_ca(
    ca_tables: list[dict[tuple[str, int], tuple[str, np.ndarray]]],
    keys: list[tuple[str, int]],
) -> np.ndarray:
    return np.stack(
        [np.stack([table[key][1] for key in keys], axis=0) for table in ca_tables],
        axis=0,
    )


def _transform_lists(rotation: np.ndarray, translation: np.ndarray) -> tuple[list[list[float]], list[float]]:
    return (
        [[round(float(value), 8) for value in row] for row in np.asarray(rotation)],
        [round(float(value), 8) for value in np.asarray(translation)],
    )


def _pairwise_kabsch_rmsd(coords: np.ndarray) -> np.ndarray:
    n_models = coords.shape[0]
    matrix = np.zeros((n_models, n_models), dtype=float)
    for i in range(n_models):
        for j in range(i + 1, n_models):
            _rotation, _translation, rmsd = kabsch_superpose(coords[i], coords[j])
            matrix[i, j] = rmsd
            matrix[j, i] = rmsd
    return matrix


def _mean_pairwise(matrix: np.ndarray) -> np.ndarray:
    n_models = matrix.shape[0]
    if n_models == 1:
        return np.zeros(1, dtype=float)
    totals = matrix.sum(axis=1)
    return totals / (n_models - 1)


def _apply_transform(structure, transform) -> None:
    structure[0].transform_pos_and_adp(transform)


def _residue_rmsf(coords: np.ndarray) -> dict[str, np.ndarray]:
    """coords: (n_models, n_residues, 3)。RMSF 按模型数 M 平均。"""
    mean_xyz = coords.mean(axis=0)
    delta = coords - mean_xyz
    sq = np.sum(delta * delta, axis=2)
    rmsf = np.sqrt(sq.mean(axis=0))
    max_disp = np.sqrt(sq.max(axis=0))
    return {"mean_ca": mean_xyz, "ca_rmsf": rmsf, "max_displacement": max_disp}


def _core_mask(rmsf: np.ndarray) -> np.ndarray:
    n_res = int(rmsf.size)
    n_keep = n_res - int(n_res * CORE_RMSF_DROP_FRACTION)
    if n_keep < MIN_ALIGNMENT_CA:
        n_keep = min(n_res, MIN_ALIGNMENT_CA)
    if n_keep >= n_res:
        return np.ones(n_res, dtype=bool)
    order = np.argsort(rmsf, kind="mergesort")
    mask = np.zeros(n_res, dtype=bool)
    mask[order[:n_keep]] = True
    return mask


def run_ensemble_alignment(
    fasta_text: str,
    structure_paths: list[Path] | Path,
    *,
    aligned_dir: Path | None = None,
) -> dict[str, Any]:
    """质控通过后：全体 CA 取 medoid，全原子叠合，再按 RMSF 最高 20% 做一次核心叠合。"""
    import gemmi

    qc = run_structure_qc(fasta_text, structure_paths)
    if not qc["ok"]:
        raise ValueError("结构质控未通过: " + "; ".join(qc["errors"][:8]))

    paths = [Path(row["path"]) for row in qc["models"]]
    structures = [gemmi.read_structure(str(path)) for path in paths]
    originals = [structure.clone() for structure in structures]
    names = [row["name"] for row in qc["models"]]

    ca_tables = [_extract_ca(structure) for structure in structures]
    common = _common_keys(ca_tables)
    coords = _stack_ca(ca_tables, common)

    rmsd_matrix = _pairwise_kabsch_rmsd(coords)
    mean_rmsd = _mean_pairwise(rmsd_matrix)
    medoid = int(np.argmin(mean_rmsd))

    rmsd_before = [raw_rmsd(coords[medoid], coords[index]) for index in range(len(structures))]
    full_transforms = []
    for index, structure in enumerate(structures):
        if index == medoid:
            rotation, translation = _identity_rotation_translation()
            rmsd_after = 0.0
        else:
            rotation, translation, rmsd_after = kabsch_superpose(coords[medoid], coords[index])
            _apply_transform(structure, _as_gemmi_transform(rotation, translation))
        rot_list, trans_list = _transform_lists(rotation, translation)
        full_transforms.append(
            {
                "name": names[index],
                "rmsd_before_alignment": round(float(rmsd_before[index]), 4),
                "rmsd_after_full_ca": round(float(rmsd_after), 4),
                "rotation_matrix": rot_list,
                "translation_vector": trans_list,
            }
        )

    aligned_tables = [_extract_ca(structure) for structure in structures]
    aligned_coords = _stack_ca(aligned_tables, common)
    first_rmsf = _residue_rmsf(aligned_coords)
    core = _core_mask(first_rmsf["ca_rmsf"])
    core_keys = [key for key, keep in zip(common, core) if keep]
    target_core = np.stack([aligned_tables[medoid][key][1] for key in core_keys], axis=0)

    core_rmsds: list[float] = []
    for index, structure in enumerate(structures):
        if index == medoid:
            core_rmsds.append(0.0)
            continue
        mobile_core = np.stack([aligned_tables[index][key][1] for key in core_keys], axis=0)
        rotation, translation, core_rmsd = kabsch_superpose(target_core, mobile_core)
        core_rmsds.append(core_rmsd)
        _apply_transform(structure, _as_gemmi_transform(rotation, translation))

    final_tables = [_extract_ca(structure) for structure in structures]
    final_coords = _stack_ca(final_tables, common)
    stats = _residue_rmsf(final_coords)

    transforms = []
    for index, structure in enumerate(structures):
        original_ca = _stack_ca([_extract_ca(originals[index])], common)[0]
        if index == medoid:
            rotation, translation = _identity_rotation_translation()
        else:
            rotation, translation, _rmsd = kabsch_superpose(final_coords[index], original_ca)
        rot_list, trans_list = _transform_lists(rotation, translation)
        transforms.append(
            {
                "name": names[index],
                "is_medoid": index == medoid,
                "rmsd_before_alignment": full_transforms[index]["rmsd_before_alignment"],
                "rmsd_after_full_ca": full_transforms[index]["rmsd_after_full_ca"],
                "rmsd_after_core": round(float(raw_rmsd(final_coords[medoid], final_coords[index])), 4),
                "core_rmsd": round(core_rmsds[index], 4),
                "rotation_matrix": rot_list,
                "translation_vector": trans_list,
            }
        )

    aligned_paths: list[str] = []
    if aligned_dir is not None:
        out = Path(aligned_dir)
        out.mkdir(parents=True, exist_ok=True)
        for path, structure in zip(paths, structures):
            dest = out / f"{path.stem}_aligned.cif"
            structure.make_mmcif_document().write_file(str(dest))
            aligned_paths.append(str(dest))

    residues = []
    amino = {key: ca_tables[0][key][0] for key in common}
    for res_index, key in enumerate(common):
        chain, sequence_index = key
        residues.append(
            {
                "structure_chain": chain,
                "sequence_index": sequence_index,
                "amino_acid": amino[key],
                "in_alignment_core": bool(core[res_index]),
                "mean_ca": [round(float(v), 4) for v in stats["mean_ca"][res_index]],
                "ca_rmsf": round(float(stats["ca_rmsf"][res_index]), 4),
                "max_displacement": round(float(stats["max_displacement"][res_index]), 4),
                "ca_xyz": [
                    [round(float(v), 4) for v in final_coords[model_index, res_index]]
                    for model_index in range(final_coords.shape[0])
                ],
            }
        )

    return {
        "n_models": len(names),
        "model_names": names,
        "n_common_ca": len(common),
        "rmsd_matrix": [[round(float(v), 4) for v in row] for row in rmsd_matrix],
        "mean_pairwise_rmsd": [round(float(v), 4) for v in mean_rmsd],
        "medoid_index": medoid,
        "medoid_name": names[medoid],
        "core_drop_fraction": CORE_RMSF_DROP_FRACTION,
        "n_core_ca": int(core.sum()),
        "transforms": transforms,
        "residues": residues,
        "aligned_paths": aligned_paths,
        "structure_paths": [str(path) for path in paths],
        "qc": {"ok": qc["ok"], "n_models": qc["n_models"], "errors": qc["errors"]},
    }
