"""额外二硫键编排：阶段、CSV 产物与套数门槛（不调用 PyRosetta）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from algorithm_paths import bootstrap_algorithm_paths

bootstrap_algorithm_paths()

from tm_disulfide.constants import MINIMUM_MODELS_PASSED
from tm_disulfide.workflow import run_workflow


def test_run_workflow_writes_ranked_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fasta = ">H\nACDEFGHIKLMNPQRSTVWY\n"
    models = [tmp_path / f"input_model_{i}.cif" for i in range(4)]
    for path in models:
        path.write_text("data_x\n", encoding="utf-8")

    monkeypatch.setattr(
        "tm_disulfide.workflow.run_structure_qc",
        lambda *_args, **_kwargs: {"ok": True, "n_models": 4, "errors": []},
    )
    monkeypatch.setattr(
        "tm_disulfide.workflow.run_ensemble_alignment",
        lambda *_args, **_kwargs: {"medoid_name": "input_model_0.cif", "structure_paths": [str(p) for p in models]},
    )
    monkeypatch.setattr(
        "tm_disulfide.workflow.run_site_mask",
        lambda *_args, **_kwargs: {"n_eligible": 6},
    )
    monkeypatch.setattr(
        "tm_disulfide.workflow.run_pair_screen",
        lambda *_args, **_kwargs: {"n_passed": 2, "pairs": []},
    )
    geometry = {
        "n_passed": 2,
        "pairs": [
            {
                "pair_id": "H:6-H:20",
                "pair_geometry_pass": True,
                "site1": {"structure_chain": "H", "sequence_index": 6},
                "site2": {"structure_chain": "H", "sequence_index": 20},
            },
            {
                "pair_id": "H:3-H:18",
                "pair_geometry_pass": True,
                "site1": {"structure_chain": "H", "sequence_index": 3},
                "site2": {"structure_chain": "H", "sequence_index": 18},
            },
        ],
    }
    monkeypatch.setattr("tm_disulfide.workflow.run_geometry_search", lambda *_a, **_k: geometry)
    monkeypatch.setattr(
        "tm_disulfide.workflow.run_build_all",
        lambda *_a, **_k: {
            "n_pair_pass": 2,
            "pairs": [
                {"pair_id": "H:6-H:20", "pair_build_pass": True, "n_models_passed": 4},
                {"pair_id": "H:3-H:18", "pair_build_pass": True, "n_models_passed": 4},
            ],
        },
    )
    monkeypatch.setattr(
        "tm_disulfide.workflow.run_energy_compare",
        lambda *_a, **_k: {
            "n_pair_pass": 1,
            "pairs": [
                {"pair_id": "H:6-H:20", "pair_energy_pass": True, "n_models_passed": 4, "median_ddg": 4.2},
                {"pair_id": "H:3-H:18", "pair_energy_pass": False, "n_models_passed": 2, "median_ddg": -1.0},
            ],
        },
    )

    work = tmp_path / "job"
    stages: list[str] = []
    result = run_workflow(work, fasta_text=fasta, structure_paths=models, on_stage=stages.append)

    assert stages == ["qc", "ensemble", "sites", "pairs", "geometry", "build", "energy", "done"]
    assert result["n_energy_pass"] == 1
    assert result["candidates"][0]["pair_id"] == "H:6-H:20"
    assert result["candidates"][0]["energy_pass"] is True
    assert result["candidates"][0]["rank"] == 1
    csv_text = (work / "exports" / "candidates.csv").read_text(encoding="utf-8")
    assert "H:6-H:20" in csv_text
    summary = (work / "exports" / "summary.json").read_text(encoding="utf-8")
    assert str(MINIMUM_MODELS_PASSED) in summary
    assert (work / "input" / "source_models.json").is_file()


def test_run_workflow_rejects_fewer_than_four_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fasta = ">H\nACDEFGHIKLMNPQRSTVWY\n"
    models = [tmp_path / f"input_model_{i}.cif" for i in range(3)]
    for path in models:
        path.write_text("data_x\n", encoding="utf-8")
    monkeypatch.setattr(
        "tm_disulfide.workflow.run_structure_qc",
        lambda *_args, **_kwargs: {"ok": True, "n_models": 3, "errors": []},
    )
    with pytest.raises(ValueError, match="结构套数不足"):
        run_workflow(tmp_path / "job", fasta_text=fasta, structure_paths=models)
