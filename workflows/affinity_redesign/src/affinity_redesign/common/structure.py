"""结构文件路径校验（后续接 CIF/PDB 转换）。"""

from __future__ import annotations

from pathlib import Path

VALID_SUFFIXES = {".pdb", ".ent", ".cif", ".mmcif"}


def resolve_structure_path(campaign_dir: Path, rel_path: str | None) -> Path | None:
    if not rel_path:
        return None
    path = campaign_dir / rel_path
    if not path.is_file():
        return None
    if path.suffix.lower() not in VALID_SUFFIXES:
        raise ValueError(f"不支持的结构格式: {path.suffix}")
    return path
