"""上传结构暂存与标准结构产物导出。"""

from __future__ import annotations

import shutil
from pathlib import Path


def copy_structure_input(source: Path, fold_root: Path) -> Path:
    """按原工作流命名规则把上传结构复制到 fold 目录。"""
    destination = fold_root / f"input{source.suffix.lower() or '.pdb'}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def to_cif(source: Path, destination: Path) -> Path:
    """用 gemmi 将结构转换为 mmCIF；转换错误原样向上传递。"""
    import gemmi

    destination.parent.mkdir(parents=True, exist_ok=True)
    structure = gemmi.read_structure(str(source))
    structure.make_mmcif_document().write_file(str(destination))
    return destination


def export_structure_files(source: Path, cif_path: Path, pdb_path: Path) -> None:
    """生成工作流兼容的 pred.cif，并尽可能同时生成 pred.pdb。"""
    try:
        to_cif(source, cif_path)
    except Exception:
        shutil.copy2(source, cif_path)

    if source.suffix.lower() == ".pdb":
        shutil.copy2(source, pdb_path)
        return

    try:
        import gemmi

        structure = gemmi.read_structure(str(source))
        if hasattr(structure, "write_pdb"):
            structure.write_pdb(str(pdb_path))
        else:
            pdb_path.write_text(structure.make_pdb_string(), encoding="utf-8")
    except Exception:
        pass
