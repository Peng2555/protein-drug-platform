"""仓库内算法源码路径的唯一 bootstrap。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent
ALGORITHM_SOURCE_DIRS = (
    ROOT / "shared" / "src",
    ROOT / "affinity_redesign" / "src",
    ROOT / "hydro_redesign" / "src",
    ROOT / "workflows" / "cic_profile" / "src",
    ROOT / "cic_profile" / "src",
    ROOT / "tnp_profile" / "src",
)


def bootstrap_algorithm_paths(
    *, include_scripts: bool = False, extra_paths: Iterable[Path] = ()
) -> tuple[Path, ...]:
    """将存在的源码目录加入 sys.path，兼容尚未 editable install 的部署。"""
    paths = (*ALGORITHM_SOURCE_DIRS, *extra_paths)
    if include_scripts:
        paths = (*paths, ROOT / "scripts")
    added = []
    for path in reversed(paths):
        if path.is_dir() and str(path) not in sys.path:
            sys.path.insert(0, str(path))
            added.append(path)
    return tuple(reversed(added))
