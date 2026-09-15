"""CIC workflow 目录迁移兼容契约。"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

from algorithm_paths import ALGORITHM_SOURCE_DIRS, bootstrap_algorithm_paths

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = ROOT / "workflows" / "cic_profile"
LEGACY_ROOT = ROOT / "cic_profile"


def test_cic_workflow_new_path_precedes_legacy_fallback():
    new_source = WORKFLOW_ROOT / "src"
    legacy_source = LEGACY_ROOT / "src"

    assert new_source.is_dir()
    assert ALGORITHM_SOURCE_DIRS.index(new_source) < ALGORITHM_SOURCE_DIRS.index(legacy_source)


def test_cic_legacy_root_resolves_to_workflow():
    if LEGACY_ROOT.is_symlink():
        assert os.readlink(LEGACY_ROOT) == "workflows/cic_profile"
    else:
        # 某些平台或归档还原流程不保留 symlink，至少必须解析到同一物理目录。
        assert LEGACY_ROOT.resolve() == WORKFLOW_ROOT.resolve()


def test_cic_import_and_public_entrypoint_from_workflow_path():
    bootstrap_algorithm_paths()
    for name in tuple(sys.modules):
        if name == "cic_profile" or name.startswith("cic_profile."):
            sys.modules.pop(name)

    package = importlib.import_module("cic_profile")
    workflow = importlib.import_module("cic_profile.workflow")

    assert Path(package.__file__).resolve().is_relative_to(WORKFLOW_ROOT.resolve())
    assert package.__all__ == ["run_workflow"]
    assert package.run_workflow is workflow.run_workflow
