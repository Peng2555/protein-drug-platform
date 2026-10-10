"""Hydro redesign workflow 标准目录与公开导入契约。"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import tomllib

from algorithm_paths import ALGORITHM_SOURCE_DIRS, bootstrap_algorithm_paths

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = ROOT / "workflows" / "hydro_redesign"
LEGACY_ROOT = ROOT / "hydro_redesign"


def test_hydro_workflow_uses_standard_source_layout():
    source = WORKFLOW_ROOT / "src"

    assert source.is_dir()
    assert source in ALGORITHM_SOURCE_DIRS


def test_hydro_legacy_root_entry_is_absent():
    assert not LEGACY_ROOT.exists()
    assert not LEGACY_ROOT.is_symlink()


def test_hydro_dependencies_are_declared():
    metadata = tomllib.loads((WORKFLOW_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = metadata["project"]["dependencies"]

    assert any(item.startswith("boltzfold-shared") for item in dependencies)
    assert any(item.startswith("numpy") for item in dependencies)
    assert any(item.startswith("gemmi") for item in dependencies)


def test_hydro_import_entrypoint_and_sasa_compatibility():
    bootstrap_algorithm_paths()
    for name in tuple(sys.modules):
        if name == "hydro_redesign" or name.startswith("hydro_redesign."):
            sys.modules.pop(name)

    package = importlib.import_module("hydro_redesign")
    workflow = importlib.import_module("hydro_redesign.workflow")
    sasa = importlib.import_module("hydro_redesign.sasa")
    shared_sasa = importlib.import_module("boltzfold_shared.geometry.sasa")

    assert Path(package.__file__).resolve().is_relative_to(WORKFLOW_ROOT.resolve())
    assert callable(workflow.run_workflow)
    assert sasa.__all__ == ["THREE_TO_ONE", "load_atoms", "res_iter", "residue_sasa"]
    assert sasa.load_atoms is shared_sasa.load_atoms
    assert sasa.res_iter is shared_sasa.res_iter
    assert sasa.residue_sasa is shared_sasa.residue_sasa
