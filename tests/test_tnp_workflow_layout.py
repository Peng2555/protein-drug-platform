"""TNP workflow 目录迁移、数据打包与导入兼容契约。"""

from __future__ import annotations

import importlib
import importlib.resources
import os
import sys
import tomllib
from pathlib import Path

from algorithm_paths import ALGORITHM_SOURCE_DIRS, bootstrap_algorithm_paths

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = ROOT / "workflows" / "tnp_profile"
LEGACY_ROOT = ROOT / "tnp_profile"


def test_tnp_workflow_new_path_precedes_legacy_fallback():
    new_source = WORKFLOW_ROOT / "src"
    legacy_source = LEGACY_ROOT / "src"

    assert new_source.is_dir()
    assert ALGORITHM_SOURCE_DIRS.index(new_source) < ALGORITHM_SOURCE_DIRS.index(legacy_source)


def test_tnp_legacy_root_resolves_to_workflow():
    if LEGACY_ROOT.is_symlink():
        assert os.readlink(LEGACY_ROOT) == "workflows/tnp_profile"
    else:
        assert LEGACY_ROOT.resolve() == WORKFLOW_ROOT.resolve()


def test_tnp_package_data_is_declared_and_available():
    metadata = tomllib.loads((WORKFLOW_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = metadata["project"]["dependencies"]
    assert any(item.startswith("boltzfold-shared") for item in dependencies)
    assert any(item.startswith("numpy") for item in dependencies)
    assert any(item.startswith("gemmi") for item in dependencies)
    assert "anarci" in dependencies
    assert metadata["tool"]["setuptools"]["package-data"]["tnp_profile"] == ["data/*"]

    bootstrap_algorithm_paths()
    data = importlib.resources.files("tnp_profile").joinpath("data")
    assert data.joinpath("thresholds.json").is_file()
    assert data.joinpath("clinical_vhh.fasta").is_file()


def test_tnp_import_and_public_entrypoint_from_workflow_path():
    bootstrap_algorithm_paths()
    for name in tuple(sys.modules):
        if name == "tnp_profile" or name.startswith("tnp_profile."):
            sys.modules.pop(name)

    package = importlib.import_module("tnp_profile")
    workflow = importlib.import_module("tnp_profile.workflow")

    assert Path(package.__file__).resolve().is_relative_to(WORKFLOW_ROOT.resolve())
    assert package.__all__ == ["run_workflow"]
    assert package.run_workflow is workflow.run_workflow
