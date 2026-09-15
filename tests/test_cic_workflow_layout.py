"""CIC workflow 标准目录与公开导入契约。"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from algorithm_paths import ALGORITHM_SOURCE_DIRS, bootstrap_algorithm_paths

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = ROOT / "workflows" / "cic_profile"
LEGACY_ROOT = ROOT / "cic_profile"


def test_cic_workflow_uses_standard_source_layout():
    source = WORKFLOW_ROOT / "src"

    assert source.is_dir()
    assert source in ALGORITHM_SOURCE_DIRS


def test_cic_legacy_root_entry_is_absent():
    assert not LEGACY_ROOT.exists()
    assert not LEGACY_ROOT.is_symlink()


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
