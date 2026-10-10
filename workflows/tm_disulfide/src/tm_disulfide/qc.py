"""Boltz2 多模型结构输入质控：确认 5 套结构与 FASTA 一一对应。"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from boltzfold_shared.io.fasta import parse_fasta
from tm_disulfide.constants import (
    BACKBONE_ATOMS,
    COORD_DUP_EPS,
    SS_SG_MAX,
    SS_SG_MIN,
    THREE_TO_ONE,
)


def discover_boltz_models(folder: Path) -> list[Path]:
    """收集 Boltz2 的 input_model_*.cif，按模型序号排序。"""
    folder = Path(folder)
    hits: list[tuple[int, Path]] = []
    for path in folder.rglob("*.cif"):
        if path.name.startswith("pred"):
            continue
        match = re.search(r"_model_(\d+)\.cif$", path.name)
        if match:
            hits.append((int(match.group(1)), path))
    hits.sort(key=lambda item: (item[0], str(item[1])))
    return [path for _idx, path in hits]


def _icode(res) -> str:
    raw = getattr(res.seqid, "icode", " ")
    text = str(raw or "").strip()
    return text or ""


def _atom_xyz(atom) -> tuple[float, float, float] | None:
    pos = atom.pos
    xyz = (float(pos.x), float(pos.y), float(pos.z))
    if not all(math.isfinite(v) for v in xyz):
        return None
    return xyz


def _pick_atom(res, name: str):
    """同一原子名若有 altloc，取 occupancy 最高者。"""
    candidates = []
    for atom in res:
        if atom.name.strip() != name:
            continue
        occ = float(atom.occ) if atom.occ is not None else 1.0
        candidates.append((occ, atom.altloc or "", atom))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]


def load_model(structure_path: Path) -> dict[str, Any]:
    import gemmi

    path = Path(structure_path)
    structure = gemmi.read_structure(str(path))
    if len(structure) < 1:
        raise ValueError(f"{path.name}: 没有模型")
    model = structure[0]
    residues: list[dict[str, Any]] = []
    issues: list[str] = []
    coords: list[tuple[float, float, float]] = []
    seen_res: set[tuple[str, int, str]] = set()

    for chain in model:
        seq_index = 0
        for res in chain:
            aa = THREE_TO_ONE.get(res.name)
            if aa is None:
                continue
            seqid = int(res.seqid.num)
            icode = _icode(res)
            key = (chain.name, seqid, icode)
            if key in seen_res:
                issues.append(f"{chain.name}:{seqid}{icode} 残基重复")
                continue
            seen_res.add(key)
            seq_index += 1
            atoms: dict[str, tuple[float, float, float]] = {}
            for atom in res:
                name = atom.name.strip()
                xyz = _atom_xyz(atom)
                if xyz is None:
                    issues.append(f"{chain.name}:{seqid} 原子 {name} 坐标非法")
                    continue
                picked = _pick_atom(res, name)
                if picked is not atom:
                    continue
                atoms[name] = xyz
                coords.append(xyz)
            missing = [name for name in BACKBONE_ATOMS if name not in atoms]
            if aa != "G" and "CB" not in atoms:
                missing.append("CB")
            if aa == "C" and "SG" not in atoms:
                missing.append("SG")
            bfactor = None
            ca = _pick_atom(res, "CA")
            if ca is not None:
                try:
                    bfactor = float(ca.b_iso)
                except (TypeError, ValueError):
                    bfactor = None
            residues.append(
                {
                    "sequence_index": seq_index,
                    "structure_chain": chain.name,
                    "structure_residue_number": seqid,
                    "insertion_code": icode,
                    "amino_acid": aa,
                    "missing_atoms": missing,
                    "has_sg": "SG" in atoms,
                    "ca_xyz": list(atoms["CA"]) if "CA" in atoms else None,
                    "sg_xyz": list(atoms["SG"]) if "SG" in atoms else None,
                    "bfactor": bfactor,
                }
            )

    for i, left in enumerate(coords):
        for right in coords[i + 1 :]:
            if all(abs(a - b) <= COORD_DUP_EPS for a, b in zip(left, right)):
                issues.append("存在坐标完全重合的原子")
                break
        else:
            continue
        break

    seqs: dict[str, str] = {}
    for row in residues:
        seqs[row["structure_chain"]] = seqs.get(row["structure_chain"], "") + row["amino_acid"]
    insertion_codes = [row["insertion_code"] for row in residues if row["insertion_code"]]

    return {
        "path": str(path),
        "name": path.name,
        "model_name": model.name or path.stem,
        "sequences": seqs,
        "residues": residues,
        "insertion_codes": insertion_codes,
        "issues": issues,
    }


def _cys_records(model: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cys = [row for row in model["residues"] if row["amino_acid"] == "C"]
    pairs: list[dict[str, Any]] = []
    for i, left in enumerate(cys):
        for right in cys[i + 1 :]:
            dist = None
            likely = False
            if left.get("sg_xyz") and right.get("sg_xyz"):
                dist = math.sqrt(
                    sum((a - b) ** 2 for a, b in zip(left["sg_xyz"], right["sg_xyz"]))
                )
                likely = SS_SG_MIN <= dist <= SS_SG_MAX
            pairs.append(
                {
                    "i": left["sequence_index"],
                    "j": right["sequence_index"],
                    "chain_i": left["structure_chain"],
                    "chain_j": right["structure_chain"],
                    "sg_distance": None if dist is None else round(dist, 3),
                    "likely_disulfide": likely,
                }
            )
    return [
        {
            "sequence_index": row["sequence_index"],
            "structure_chain": row["structure_chain"],
            "structure_residue_number": row["structure_residue_number"],
            "has_sg": row["has_sg"],
        }
        for row in cys
    ], pairs


def run_structure_qc(
    fasta_text: str,
    structure_paths: list[Path] | Path,
) -> dict[str, Any]:
    """对 Boltz2 多套模型做序列一致性和原子完整性检查。"""
    fasta = parse_fasta(fasta_text)
    if not fasta:
        raise ValueError("FASTA 无效")
    if isinstance(structure_paths, Path):
        paths = discover_boltz_models(structure_paths)
    else:
        paths = [Path(p) for p in structure_paths]
    if not paths:
        raise ValueError("没有可用的结构文件")

    models = [load_model(path) for path in paths]
    errors: list[str] = []
    ref = models[0]
    for model in models:
        if model["sequences"] != fasta:
            errors.append(
                f"{model['name']} 序列与 FASTA 不一致: 结构={model['sequences']} FASTA={fasta}"
            )
        if model["sequences"] != ref["sequences"]:
            errors.append(f"{model['name']} 与参考模型 {ref['name']} 序列不一致")
        if model["insertion_codes"]:
            errors.append(f"{model['name']} 含插入码: {model['insertion_codes']}")
        errors.extend(f"{model['name']}: {msg}" for msg in model["issues"])
        for row in model["residues"]:
            if row["missing_atoms"]:
                errors.append(
                    f"{model['name']} {row['structure_chain']}:{row['sequence_index']}"
                    f"{row['amino_acid']} 缺原子 {','.join(row['missing_atoms'])}"
                )

    cysteines = []
    for model in models:
        sites, pairs = _cys_records(model)
        cysteines.append({"model": model["name"], "sites": sites, "sg_pairs": pairs})

    mapping = [
        {
            "sequence_index": row["sequence_index"],
            "structure_chain": row["structure_chain"],
            "structure_residue_number": row["structure_residue_number"],
            "insertion_code": row["insertion_code"],
            "amino_acid": row["amino_acid"],
        }
        for row in ref["residues"]
    ]
    return {
        "ok": not errors,
        "n_models": len(models),
        "fasta": fasta,
        "reference_model": ref["name"],
        "residue_mapping": mapping,
        "models": [
            {
                "name": m["name"],
                "path": m["path"],
                "sequences": m["sequences"],
                "n_residues": len(m["residues"]),
                "n_missing_atom_residues": sum(1 for r in m["residues"] if r["missing_atoms"]),
            }
            for m in models
        ],
        "cysteines": cysteines,
        "errors": errors,
    }
