#!/usr/bin/env python3
"""Generic receptor/ligand docking: SMILES → ETKDG starts → global Vina."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class DockingResult:
    status: str
    stage: str
    seconds: float
    results: dict
    error: str | None = None


def _command(name: str) -> str | None:
    return shutil.which(name)


def _reference_coords(path: Path) -> list[list[float]]:
    """Read heavy-atom coordinates from common reference-ligand formats."""
    suffix = path.suffix.lower()
    if suffix in {".sdf", ".sd", ".mol", ".mol2"}:
        from rdkit import Chem

        if suffix in {".sdf", ".sd"}:
            mol = next(iter(Chem.SDMolSupplier(str(path), removeHs=False)), None)
        elif suffix == ".mol2":
            mol = Chem.MolFromMol2File(str(path), removeHs=False)
        else:
            mol = Chem.MolFromMolFile(str(path), removeHs=False)
        if mol is None or mol.GetNumConformers() == 0:
            raise ValueError("参考配体没有可用的三维坐标")
        conf = mol.GetConformer()
        return [
            [conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y, conf.GetAtomPosition(i).z]
            for i, atom in enumerate(mol.GetAtoms())
            if atom.GetAtomicNum() > 1
        ]
    if suffix in {".cif", ".mmcif"}:
        import gemmi

        structure = gemmi.read_structure(str(path))
        return [
            [atom.pos.x, atom.pos.y, atom.pos.z]
            for model in structure
            for chain in model
            for residue in chain
            for atom in residue
            if atom.element.name != "H"
        ]
    coords: list[list[float]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith(("ATOM", "HETATM")):
            try:
                coords.append([float(line[30:38]), float(line[38:46]), float(line[46:54])])
            except ValueError:
                fields = line.split()
                if len(fields) >= 8:
                    coords.append([float(fields[5]), float(fields[6]), float(fields[7])])
    if not coords:
        raise ValueError("参考配体没有可用的原子坐标")
    return coords


def _box_from_reference(path: Path, padding: float) -> tuple[list[float], list[float]]:
    import numpy as np

    coords = np.asarray(_reference_coords(path), dtype=float)
    center = coords.mean(axis=0)
    size = coords.max(axis=0) - coords.min(axis=0) + 2 * padding
    return center.tolist(), size.tolist()


def _pose_scores(path: Path) -> list[dict]:
    scores: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.search(r"REMARK VINA RESULT:\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)", line)
        if match:
            scores.append({
                "pose": len(scores) + 1,
                "affinity_kcal_mol": float(match.group(1)),
                "rmsd_lb": float(match.group(2)),
                "rmsd_ub": float(match.group(3)),
            })
    return scores


def _first_pose(path: Path) -> str:
    """Return the first MODEL from a multi-pose PDBQT file."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    pose: list[str] = []
    in_model = False
    for line in lines:
        if line.startswith("MODEL"):
            if in_model:
                break
            in_model = True
        if in_model:
            pose.append(line)
        if in_model and line.startswith("ENDMDL"):
            break
    if not pose:
        raise RuntimeError("对接结果中没有找到 Pose")
    return "\n".join(pose) + "\n"


def _build_complex(
    receptor_pdbqt: Path,
    poses_pdbqt: Path,
    work_dir: Path,
    env: dict[str, str],
    obabel_bin: str | None = None,
) -> tuple[Path, Path]:
    """Combine receptor and best ligand pose, then convert to PDB."""
    complex_pdbqt = work_dir / "docked_complex.pdbqt"
    receptor_text = receptor_pdbqt.read_text(encoding="utf-8", errors="replace")
    ligand_text = _first_pose(poses_pdbqt)
    complex_pdbqt.write_text(
        receptor_text.rstrip() + "\n" + ligand_text + "END\n",
        encoding="utf-8",
    )
    complex_pdb = work_dir / "docked_complex.pdb"
    obabel = obabel_bin if obabel_bin and Path(obabel_bin).is_file() else _command("obabel")
    if not obabel:
        raise RuntimeError("已生成 docked_complex.pdbqt，但未找到 Open Babel，无法转换 PDB")
    proc = subprocess.run(
        [obabel, "-ipdbqt", str(complex_pdbqt), "-opdb", "-O", str(complex_pdb)],
        env=env, capture_output=True, text=True, check=False,
    )
    if proc.returncode or not complex_pdb.is_file():
        raise RuntimeError(f"复合物 PDB 转换失败: {(proc.stderr or proc.stdout)[-3000:]}")
    return complex_pdbqt, complex_pdb


def _convert(
    src: Path,
    dst: Path,
    kind: str,
    env: dict[str, str],
    obabel_bin: str | None = None,
) -> None:
    if src.suffix.lower() == ".pdbqt":
        shutil.copy2(src, dst)
        return
    if src.suffix.lower() in {".cif", ".mmcif"}:
        try:
            import gemmi
            converted = dst.with_suffix(".pdb")
            gemmi.read_structure(str(src)).write_pdb(str(converted))
            _convert(converted, dst, kind, env, obabel_bin)
            converted.unlink(missing_ok=True)
            return
        except Exception as exc:
            raise RuntimeError(f"{kind} mmCIF 转 PDB 失败: {exc}") from exc
    obabel = obabel_bin if obabel_bin and Path(obabel_bin).is_file() else _command("obabel")
    if not obabel:
        raise RuntimeError(
            f"需要 Open Babel 将{kind} {src.suffix} 转为 PDBQT；"
            "请安装 obabel，或直接上传 PDBQT"
        )
    input_type = {
        ".pdb": "pdb", ".sdf": "sdf", ".sd": "sdf",
        ".mol": "mol", ".mol2": "mol2",
    }.get(src.suffix.lower())
    if not input_type:
        raise ValueError(f"不支持的{kind}格式: {src.suffix}")
    proc = subprocess.run(
        [obabel, f"-i{input_type}", str(src), "-opdbqt", "-O", str(dst), "-h"],
        env=env, capture_output=True, text=True, check=False,
    )
    if proc.returncode or not dst.is_file():
        raise RuntimeError(f"{kind}转换失败: {(proc.stderr or proc.stdout)[-3000:]}")


def _ligand_smiles(params: dict, ligand: Path | None) -> str:
    smiles = str(params.get("ligand_smiles") or "").strip()
    if smiles:
        return smiles
    if ligand and ligand.is_file() and ligand.suffix.lower() in {".smi", ".smiles", ".txt"}:
        return ligand.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    raise ValueError("请提供小分子 SMILES，系统会采样构象作为对接起点")


def _prepare_ligand_pdbqt(sdf: Path, dst: Path, env: dict[str, str], obabel_bin: str | None) -> str:
    """Prepare PDBQT with Meeko (movable macrocycles); fall back to Open Babel."""

    cmd = [
        sys.executable, "-m", "meeko.cli.mk_prepare_ligand",
        "-i", str(sdf), "-o", str(dst), "--add_index_map",
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    if proc.returncode == 0 and dst.is_file() and dst.stat().st_size > 0:
        return "meeko"
    _convert(sdf, dst, "配体", env, obabel_bin)
    return "obabel"


def _split_pdbqt_models(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks: list[str] = []
    current: list[str] = []
    in_model = False
    for line in text.splitlines():
        if line.startswith("MODEL"):
            if current:
                blocks.append("\n".join(current) + "\n")
            current = [line]
            in_model = True
            continue
        if in_model:
            current.append(line)
            if line.startswith("ENDMDL"):
                blocks.append("\n".join(current) + "\n")
                current = []
                in_model = False
    if current:
        blocks.append("\n".join(current) + "\n")
    if not blocks and "ATOM" in text:
        blocks.append(text if text.endswith("\n") else text + "\n")
    return blocks


def _score_from_block(block: str) -> dict | None:
    match = re.search(
        r"REMARK VINA RESULT:\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)",
        block,
    )
    if not match:
        return None
    return {
        "affinity_kcal_mol": float(match.group(1)),
        "rmsd_lb": float(match.group(2)),
        "rmsd_ub": float(match.group(3)),
    }


def _run_vina_one(
    *,
    receptor_pdbqt: Path,
    ligand_pdbqt: Path,
    output: Path,
    params: dict,
    vina_bin: str,
    gnina_bin: str,
    work_dir: Path,
    env: dict[str, str],
    seed: int,
) -> str:
    engine = str(params.get("engine", "vina"))
    executable = gnina_bin if engine == "gnina" else vina_bin
    cpu = int(params.get("cpu_per_job") or min(4, max(1, os.cpu_count() or 1)))
    vina_seed = int(params.get("base_seed", 20260811)) + int(seed)
    if engine == "vina" and not Path(executable).is_file() and not _command(executable):
        try:
            from vina import Vina
        except ImportError as exc:
            raise FileNotFoundError(
                "未找到 Vina 可执行文件，且当前 Python 环境没有 vina 模块"
            ) from exc
        try:
            vina = Vina(sf_name="vina", verbosity=1, cpu=cpu, seed=vina_seed)
        except TypeError:
            vina = Vina(sf_name="vina", verbosity=1)
        vina.set_receptor(str(receptor_pdbqt))
        vina.set_ligand_from_file(str(ligand_pdbqt))
        center = [params["center_x"], params["center_y"], params["center_z"]]
        box = [params["size_x"], params["size_y"], params["size_z"]]
        vina.compute_vina_maps(center=center, box_size=box)
        vina.dock(
            exhaustiveness=int(params["exhaustiveness"]),
            n_poses=int(params["num_modes"]),
        )
        vina.write_poses(
            str(output),
            n_poses=int(params["num_modes"]),
            energy_range=float(params["energy_range"]),
        )
        return "AutoDock Vina Python API completed\n"
    if not Path(executable).is_file() and not _command(executable):
        raise FileNotFoundError(f"未找到对接程序: {executable}")
    cmd = [
        executable, "--receptor", str(receptor_pdbqt),
        "--ligand", str(ligand_pdbqt), "--out", str(output),
        "--center_x", str(params["center_x"]),
        "--center_y", str(params["center_y"]),
        "--center_z", str(params["center_z"]),
        "--size_x", str(params["size_x"]),
        "--size_y", str(params["size_y"]),
        "--size_z", str(params["size_z"]),
        "--exhaustiveness", str(params["exhaustiveness"]),
        "--num_modes", str(params["num_modes"]),
        "--energy_range", str(params["energy_range"]),
        "--cpu", str(cpu),
        "--seed", str(vina_seed),
    ]
    if "--local_only" in cmd:
        raise AssertionError("Local-only docking is forbidden")
    proc = subprocess.run(cmd, cwd=work_dir, env=env, capture_output=True, text=True, check=False)
    log_text = "$ " + " ".join(cmd) + "\n\n" + proc.stdout + "\n" + proc.stderr
    if proc.returncode:
        raise RuntimeError(f"对接失败 (start {seed}): {(proc.stderr or proc.stdout)[-5000:]}")
    if not output.is_file():
        raise RuntimeError(f"对接程序未生成 poses（start {seed}）")
    return log_text


def run_small_molecule_docking(
    *,
    work_dir: Path,
    receptor: Path,
    ligand: Path | None = None,
    params: dict,
    vina_bin: str,
    gnina_bin: str,
    obabel_bin: str | None = None,
    on_stage: Callable[[str], None] | None = None,
) -> DockingResult:
    started = time.time()
    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        if on_stage:
            on_stage("prepare")

        dock_mode = str(params.get("dock_mode") or "manual").strip().lower()
        cavities: list[dict] = []
        reference_path = params.get("reference_ligand_path")

        if dock_mode == "auto_blind":
            if on_stage:
                on_stage("cavity")
            from cavity_detection import detect_cavities

            cavities = detect_cavities(
                receptor,
                num_cavities=int(params.get("num_cavities") or 5),
                box_padding=float(params.get("box_padding", 4.0)),
            )
            (work_dir / "cavities.json").write_text(
                json.dumps(cavities, indent=2, ensure_ascii=False), encoding="utf-8",
            )
            boxes = [
                {
                    "cavity_id": c["cavity_id"],
                    "center_x": c["center_x"],
                    "center_y": c["center_y"],
                    "center_z": c["center_z"],
                    "size_x": c["size_x"],
                    "size_y": c["size_y"],
                    "size_z": c["size_z"],
                    "box_source": "cavity_detection",
                    "volume": c.get("volume"),
                }
                for c in cavities
            ]
        elif reference_path:
            center, box_size = _box_from_reference(
                Path(reference_path), float(params.get("box_padding", 5.0)),
            )
            boxes = [{
                "cavity_id": 1,
                "center_x": center[0],
                "center_y": center[1],
                "center_z": center[2],
                "size_x": box_size[0],
                "size_y": box_size[1],
                "size_z": box_size[2],
                "box_source": "reference_ligand",
                "volume": None,
            }]
            cavities = [{
                "cavity_id": 1,
                "volume": None,
                "n_points": None,
                **{k: boxes[0][k] for k in (
                    "center_x", "center_y", "center_z", "size_x", "size_y", "size_z",
                )},
            }]
        else:
            boxes = [{
                "cavity_id": 1,
                "center_x": float(params["center_x"]),
                "center_y": float(params["center_y"]),
                "center_z": float(params["center_z"]),
                "size_x": float(params["size_x"]),
                "size_y": float(params["size_y"]),
                "size_z": float(params["size_z"]),
                "box_source": "manual",
                "volume": None,
            }]
            cavities = [{
                "cavity_id": 1,
                "volume": None,
                "n_points": None,
                **{k: boxes[0][k] for k in (
                    "center_x", "center_y", "center_z", "size_x", "size_y", "size_z",
                )},
            }]

        from ligand_sampling import sample_starts_from_smiles

        smiles = _ligand_smiles(params, ligand)
        n_starts = int(params.get("n_starts", 3 if dock_mode == "auto_blind" else 10))
        if dock_mode == "auto_blind":
            n_starts = max(1, min(n_starts, 5))
        n_conformers = int(params.get("n_conformers", 128))
        generation_seed = int(params.get("generation_seed", 0xC0FFEE))
        if on_stage:
            on_stage("sampling")
        sampled = sample_starts_from_smiles(
            smiles,
            work_dir,
            n_starts=n_starts,
            n_conformers=n_conformers,
            generation_seed=generation_seed,
        )
        sampling_info = {
            "method": "ETKDGv3 + MMFF94s + TFD cluster",
            "input_coordinates_retained": False,
            "requested_starts": n_starts,
            "requested_conformers": n_conformers,
            "generated_conformers": sampled.ensemble.molecule.GetNumConformers(),
            "cluster_method": sampled.ensemble.cluster_method,
            "cluster_count": len(sampled.ensemble.clusters),
            "force_field": sampled.ensemble.force_field,
            "canonical_smiles": sampled.canonical_smiles,
            "used_starts": len(sampled.starts),
            "note": (
                "起点来自构象采样，不是晶体坐标。"
                "表中 RMSD 下/上界是相对该次 Vina 起点的，不是相对晶体。"
            ),
        }
        (work_dir / "sampling.json").write_text(
            json.dumps(sampling_info, indent=2, ensure_ascii=False), encoding="utf-8",
        )

        receptor_pdbqt = work_dir / "receptor.pdbqt"
        _convert(receptor, receptor_pdbqt, "受体", env, obabel_bin)
        if on_stage:
            on_stage("docking")

        engine = str(params.get("engine", "vina"))
        log = work_dir / "docking.log"
        log_chunks: list[str] = []
        ranked: list[dict] = []
        cavity_best: list[dict] = []
        ligand_prep = None

        for box in boxes:
            cav_id = int(box["cavity_id"])
            box_params = {
                **params,
                "center_x": box["center_x"],
                "center_y": box["center_y"],
                "center_z": box["center_z"],
                "size_x": box["size_x"],
                "size_y": box["size_y"],
                "size_z": box["size_z"],
            }
            cavity_ranked: list[dict] = []
            for start in sampled.starts:
                seed = int(start["seed"])
                sdf = Path(start["sdf"])
                ligand_pdbqt = work_dir / f"cavity_{cav_id}_ligand_start_{seed}.pdbqt"
                poses_path = work_dir / f"cavity_{cav_id}_start_{seed}_poses.pdbqt"
                ligand_prep = _prepare_ligand_pdbqt(sdf, ligand_pdbqt, env, obabel_bin)
                chunk = _run_vina_one(
                    receptor_pdbqt=receptor_pdbqt,
                    ligand_pdbqt=ligand_pdbqt,
                    output=poses_path,
                    params=box_params,
                    vina_bin=vina_bin,
                    gnina_bin=gnina_bin,
                    work_dir=work_dir,
                    env=env,
                    seed=seed,
                )
                log_chunks.append(f"===== cavity {cav_id} start {seed} =====\n{chunk}")
                for vina_model, block in enumerate(_split_pdbqt_models(poses_path), start=1):
                    score = _score_from_block(block)
                    if not score:
                        continue
                    item = {
                        **score,
                        "cavity_id": cav_id,
                        "start_seed": seed,
                        "vina_model": vina_model,
                        "block": block,
                        "box": {
                            "center_x": box["center_x"],
                            "center_y": box["center_y"],
                            "center_z": box["center_z"],
                            "size_x": box["size_x"],
                            "size_y": box["size_y"],
                            "size_z": box["size_z"],
                            "box_source": box.get("box_source"),
                            "volume": box.get("volume"),
                        },
                    }
                    cavity_ranked.append(item)
                    ranked.append(item)
            if cavity_ranked:
                cavity_ranked.sort(
                    key=lambda item: (item["affinity_kcal_mol"], item["start_seed"], item["vina_model"])
                )
                best = cavity_ranked[0]
                cavity_best.append({
                    "cavity_id": cav_id,
                    "volume": box.get("volume"),
                    "center_x": box["center_x"],
                    "center_y": box["center_y"],
                    "center_z": box["center_z"],
                    "size_x": box["size_x"],
                    "size_y": box["size_y"],
                    "size_z": box["size_z"],
                    "best_affinity_kcal_mol": best["affinity_kcal_mol"],
                    "n_poses": len(cavity_ranked),
                })

        if not ranked:
            raise RuntimeError("所有口袋 / 起点均未产生有效对接 pose")
        ranked.sort(key=lambda item: (item["affinity_kcal_mol"], item.get("cavity_id", 0), item["start_seed"], item["vina_model"]))
        cavity_best.sort(key=lambda item: (item["best_affinity_kcal_mol"], item["cavity_id"]))
        combined = work_dir / "docked_poses.pdbqt"
        combined_parts: list[str] = []
        poses: list[dict] = []
        for rank, item in enumerate(ranked, start=1):
            block = item["block"]
            block = re.sub(r"^MODEL\s+\d+", f"MODEL {rank}", block, count=1, flags=re.M)
            if not block.lstrip().startswith("MODEL"):
                block = f"MODEL {rank}\n{block.rstrip()}\nENDMDL\n"
            remark = (
                f"REMARK CAVITY: {item.get('cavity_id', 1)} "
                f"START_SEED: {item['start_seed']} VINA_MODEL: {item['vina_model']}\n"
            )
            if "REMARK CAVITY:" not in block and "REMARK START_SEED:" not in block:
                lines = block.splitlines(True)
                inserted = False
                rebuilt: list[str] = []
                for line in lines:
                    rebuilt.append(line)
                    if not inserted and line.startswith("MODEL"):
                        rebuilt.append(remark)
                        inserted = True
                block = "".join(rebuilt)
            combined_parts.append(block if block.endswith("\n") else block + "\n")
            poses.append({
                "pose": rank,
                "cavity_id": item.get("cavity_id", 1),
                "start_seed": item["start_seed"],
                "vina_model": item["vina_model"],
                "affinity_kcal_mol": item["affinity_kcal_mol"],
                "rmsd_lb": item["rmsd_lb"],
                "rmsd_ub": item["rmsd_ub"],
            })
        combined.write_text("".join(combined_parts), encoding="utf-8")
        log.write_text("\n\n".join(log_chunks), encoding="utf-8")
        if on_stage:
            on_stage("complex")
        complex_pdbqt, complex_pdb = _build_complex(
            receptor_pdbqt, combined, work_dir, env, obabel_bin,
        )
        if on_stage:
            on_stage("analysis")
        best_box = ranked[0].get("box") or boxes[0]
        result = {
            "engine": engine,
            "protocol": (
                "cavity_guided_blind_vina" if dock_mode == "auto_blind" else "smiles_etkdg_global_vina"
            ),
            "dock_mode": dock_mode,
            "ligand_prep": ligand_prep or "meeko",
            "local_only": False,
            "receptor": str(receptor),
            "ligand_smiles": sampled.smiles,
            "canonical_smiles": sampled.canonical_smiles,
            "output": str(combined),
            "log": str(log),
            "complex_pdbqt": str(complex_pdbqt),
            "complex_pdb": str(complex_pdb),
            "sampling": sampling_info,
            "cavities": cavities,
            "cavity_ranking": cavity_best,
            "box": {
                "center_x": best_box["center_x"],
                "center_y": best_box["center_y"],
                "center_z": best_box["center_z"],
                "size_x": best_box["size_x"],
                "size_y": best_box["size_y"],
                "size_z": best_box["size_z"],
                "box_source": best_box.get("box_source"),
            },
            "output_files": sorted(p.name for p in work_dir.iterdir() if p.is_file()),
            "poses": poses,
            "best_pose": poses[0] if poses else None,
        }
        (work_dir / "summary.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8",
        )
        return DockingResult("ok", "done", time.time() - started, result)
    except Exception as exc:
        return DockingResult("failed", "failed", time.time() - started, {}, str(exc))

