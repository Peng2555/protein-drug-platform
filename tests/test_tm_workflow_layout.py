"""Tm / 额外二硫键 workflow 标准目录与公开导入契约。"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import tomllib

from algorithm_paths import ALGORITHM_SOURCE_DIRS, bootstrap_algorithm_paths

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = ROOT / "workflows" / "tm_disulfide"


def test_tm_workflow_uses_standard_source_layout():
    source = WORKFLOW_ROOT / "src"

    assert source.is_dir()
    assert source in ALGORITHM_SOURCE_DIRS


def test_tm_dependencies_are_declared():
    metadata = tomllib.loads((WORKFLOW_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = metadata["project"]["dependencies"]

    assert any(item.startswith("boltzfold-shared") for item in dependencies)
    assert any(item.startswith("numpy") for item in dependencies)
    assert any(item.startswith("gemmi") for item in dependencies)
    assert "anarci" in dependencies


def test_tm_import_and_public_entrypoint_from_workflow_path():
    bootstrap_algorithm_paths()
    for name in tuple(sys.modules):
        if name == "tm_disulfide" or name.startswith("tm_disulfide."):
            sys.modules.pop(name)

    package = importlib.import_module("tm_disulfide")
    qc = importlib.import_module("tm_disulfide.qc")
    ensemble = importlib.import_module("tm_disulfide.ensemble")
    sites = importlib.import_module("tm_disulfide.sites")
    pairs = importlib.import_module("tm_disulfide.pairs")
    geometry = importlib.import_module("tm_disulfide.geometry")
    build = importlib.import_module("tm_disulfide.build")
    energy = importlib.import_module("tm_disulfide.energy")

    workflow = importlib.import_module("tm_disulfide.workflow")

    assert Path(package.__file__).resolve().is_relative_to(WORKFLOW_ROOT.resolve())
    assert package.__all__ == [
        "discover_boltz_models",
        "run_build_all",
        "run_build_pilot",
        "run_energy_compare",
        "run_ensemble_alignment",
        "run_geometry_search",
        "run_pair_screen",
        "run_site_mask",
        "run_structure_qc",
        "run_workflow",
    ]
    assert package.run_structure_qc is qc.run_structure_qc
    assert package.discover_boltz_models is qc.discover_boltz_models
    assert package.run_ensemble_alignment is ensemble.run_ensemble_alignment
    assert package.run_site_mask is sites.run_site_mask
    assert package.run_pair_screen is pairs.run_pair_screen
    assert package.run_geometry_search is geometry.run_geometry_search
    assert package.run_build_pilot is build.run_build_pilot
    assert package.run_build_all is build.run_build_all
    assert package.run_energy_compare is energy.run_energy_compare
    assert package.run_workflow is workflow.run_workflow
