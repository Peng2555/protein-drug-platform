"""Contracts for the isolated legacy application entry point."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]


def test_app_top_level_is_limited_to_supported_entries() -> None:
    allowed = {
        "__init__.py",
        "main.py",
        "common",
        "core",
        "legacy",
        "modules",
        "schemas",
    }
    actual = {
        path.name
        for path in (ROOT / "app").iterdir()
        if path.name not in {"__pycache__", ".pytest_cache"}
    }
    assert actual == allowed
    assert not (ROOT / "app" / "server.py").exists()


def test_legacy_server_import_and_health_route_without_model(
    monkeypatch,
) -> None:
    runner = ModuleType("boltz_runner")
    runner.DEFAULT_OUT_ROOT = ROOT / "outputs"
    runner.fold_sequences = lambda *_args, **_kwargs: None
    runner.parse_fasta_text = lambda _text: {}
    monkeypatch.setitem(sys.modules, "boltz_runner", runner)
    sys.modules.pop("app.legacy.server", None)

    server = importlib.import_module("app.legacy.server")

    assert server.ROOT == ROOT
    response = TestClient(server.app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "running_jobs": 0}


def test_legacy_start_script_uses_moved_module() -> None:
    script = (ROOT / "scripts" / "start_server.sh").read_text(encoding="utf-8")
    assert "app.legacy.server:app" in script
    assert ".".join(("app", "server")) not in script
