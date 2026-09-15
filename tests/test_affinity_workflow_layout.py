"""Affinity redesign workflow 目录迁移、导入与 CLI 兼容契约。"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import tomllib

from algorithm_paths import ALGORITHM_SOURCE_DIRS, bootstrap_algorithm_paths

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = ROOT / "workflows" / "affinity_redesign"
LEGACY_ROOT = ROOT / "affinity_redesign"


def test_affinity_workflow_layout_and_new_path_precedence():
    new_source = WORKFLOW_ROOT / "src"
    legacy_source = LEGACY_ROOT / "src"

    assert new_source.is_dir()
    assert ALGORITHM_SOURCE_DIRS.index(new_source) < ALGORITHM_SOURCE_DIRS.index(legacy_source)
    for name in ("pyproject.toml", "tests", "configs", "campaigns", "docs"):
        assert (WORKFLOW_ROOT / name).exists()


def test_affinity_legacy_root_is_relative_compatibility_link():
    assert LEGACY_ROOT.is_symlink()
    assert os.readlink(LEGACY_ROOT) == "workflows/affinity_redesign"
    assert LEGACY_ROOT.resolve() == WORKFLOW_ROOT.resolve()


def test_affinity_import_resolves_from_workflow_path():
    bootstrap_algorithm_paths()
    package = importlib.import_module("affinity_redesign")
    cli = importlib.import_module("affinity_redesign.cli")

    assert Path(package.__file__).resolve().is_relative_to(WORKFLOW_ROOT.resolve())
    assert callable(cli.main)


def test_affinity_cli_entrypoint_is_unchanged():
    metadata = tomllib.loads((WORKFLOW_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["name"] == "affinity-redesign"
    assert metadata["project"]["scripts"]["affinity-redesign"] == "affinity_redesign.cli:main"

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        (str(WORKFLOW_ROOT / "src"), str(ROOT / "shared" / "src"), env.get("PYTHONPATH", ""))
    )
    result = subprocess.run(
        [sys.executable, "-m", "affinity_redesign", "--help"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "affinity-redesign" in result.stdout
