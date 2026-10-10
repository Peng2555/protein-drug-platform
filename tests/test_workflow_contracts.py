"""Hydro/CIC/TNP 工作流入口、阶段与低成本产物契约。"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for source_root in (
    ROOT / "scripts",
    ROOT / "workflows" / "affinity_redesign" / "src",
    ROOT / "workflows" / "hydro_redesign" / "src",
    ROOT / "workflows" / "cic_profile" / "src",
    ROOT / "workflows" / "tnp_profile" / "src",
):
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))


def _parameter_contract(callable_obj) -> list[tuple[str, object, inspect._ParameterKind]]:
    return [
        (name, parameter.default, parameter.kind)
        for name, parameter in inspect.signature(callable_obj).parameters.items()
    ]


def test_antibody_workflows_public_api_and_hydro_sasa_imports():
    import antibody_workflows
    from hydro_redesign.sasa import load_atoms, res_iter, residue_sasa

    assert antibody_workflows.__all__ == [
        "copy_structure_input",
        "export_structure_files",
        "fold_antibody",
        "parse_fasta",
        "to_cif",
        "write_csv",
        "write_fasta",
    ]
    assert all(callable(getattr(antibody_workflows, name)) for name in antibody_workflows.__all__)
    assert all(callable(obj) for obj in (load_atoms, res_iter, residue_sasa))


def test_workflow_and_runner_entry_signatures():
    from cic_profile.workflow import run_workflow as run_cic_workflow
    from cic_profile_runner import run_cic_profile_job
    from hydro_redesign.workflow import run_workflow as run_hydro_workflow
    from hydro_redesign_runner import run_hydro_redesign_job
    from tnp_profile.workflow import run_workflow as run_tnp_workflow
    from tnp_profile_runner import run_tnp_profile_job

    empty = inspect.Parameter.empty
    positional = inspect.Parameter.POSITIONAL_OR_KEYWORD
    keyword_only = inspect.Parameter.KEYWORD_ONLY
    assert _parameter_contract(run_hydro_workflow) == [
        ("work_dir", empty, positional),
        ("fasta_text", empty, keyword_only),
        ("structure_path", None, keyword_only),
        ("allow_cdr", False, keyword_only),
        ("allow_charged", False, keyword_only),
        ("on_stage", None, keyword_only),
    ]
    assert _parameter_contract(run_cic_workflow) == [
        ("work_dir", empty, positional),
        ("fasta_text", empty, keyword_only),
        ("structure_path", None, keyword_only),
        ("ph", 7.0, keyword_only),
        ("on_stage", None, keyword_only),
    ]
    assert _parameter_contract(run_tnp_workflow) == [
        ("work_dir", empty, positional),
        ("fasta_text", empty, keyword_only),
        ("structure_path", None, keyword_only),
        ("on_stage", None, keyword_only),
    ]
    for runner in (run_hydro_redesign_job, run_cic_profile_job, run_tnp_profile_job):
        assert _parameter_contract(runner) == [
            ("work_dir", empty, keyword_only),
            ("params", None, keyword_only),
            ("fasta_text", "", keyword_only),
            ("on_stage", None, keyword_only),
        ]


def _mock_structure_exports(monkeypatch: pytest.MonkeyPatch, workflow, source: Path) -> None:
    monkeypatch.setattr(workflow, "copy_structure_input", lambda *_args, **_kwargs: source)

    def fake_export(_source: Path, cif_path: Path, pdb_path: Path) -> None:
        cif_path.parent.mkdir(parents=True, exist_ok=True)
        cif_path.write_text("cif", encoding="utf-8")
        pdb_path.write_text("pdb", encoding="utf-8")

    monkeypatch.setattr(workflow, "export_structure_files", fake_export)


def test_hydro_workflow_stage_and_artifact_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import hydro_redesign.workflow as workflow
    from hydro_redesign.sequences import ALL_MUTANT_FASTA, TOP20_MUTANT_FASTA

    source = tmp_path / "source.pdb"
    source.write_text("END\n", encoding="utf-8")
    _mock_structure_exports(monkeypatch, workflow, source)
    monkeypatch.setattr(workflow, "_annotate_regions", lambda _seqs: {("H", 1): "FR1"})
    monkeypatch.setattr(
        workflow,
        "cluster_patches",
        lambda *_args, **_kwargs: (
            [{"chain": "H", "position": 1, "aa": "A", "hydrophobic": False, "surface": True}],
            [],
        ),
    )
    monkeypatch.setattr(workflow, "enumerate_mutations", lambda *_args, **_kwargs: ([], []))
    stages: list[str] = []

    result = workflow.run_workflow(
        tmp_path / "hydro",
        fasta_text=">H\nAAAAA\n",
        structure_path=source,
        on_stage=stages.append,
    )

    assert stages == ["fold", "patches", "enumerate", "done"]
    assert result["summary"]["n_residues"] == 1
    assert result["summary"]["hydrophobicity_scale"] == "SAP atom-level / Black–Mould (Gly=0), R=5 Å"
    assert (tmp_path / "hydro" / "exports" / "pred.cif").is_file()
    assert (tmp_path / "hydro" / "exports" / "summary.json").is_file()
    assert (tmp_path / "hydro" / "exports" / ALL_MUTANT_FASTA).is_file()
    assert (tmp_path / "hydro" / "exports" / TOP20_MUTANT_FASTA).is_file()
    assert (tmp_path / "hydro" / "workflow_status.json").is_file()


def test_cic_workflow_stage_and_artifact_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import cic_profile.workflow as workflow

    source = tmp_path / "source.pdb"
    source.write_text("END\n", encoding="utf-8")
    _mock_structure_exports(monkeypatch, workflow, source)
    monkeypatch.setattr(workflow, "_annotate_regions", lambda _seqs: {("H", 1): "FR1"})
    monkeypatch.setattr(
        workflow,
        "cluster_cic_patches",
        lambda *_args, **_kwargs: (
            [{"chain": "H", "position": 1, "aa": "A"}],
            [{"patch_id": "P1", "kind": "positive", "n_residues": 1, "score": 1.0, "residues": ["H:A1"]}],
        ),
    )
    stages: list[str] = []

    result = workflow.run_workflow(
        tmp_path / "cic",
        fasta_text=">H\nAAAAA\n",
        structure_path=source,
        on_stage=stages.append,
    )

    assert stages == ["fold", "patches", "done"]
    assert result["summary"]["n_positive_patches"] == 1
    for relative in (
        "exports/pred.cif",
        "exports/residue_features.csv",
        "exports/patches.csv",
        "exports/summary.json",
        "patches/patches.json",
        "workflow_status.json",
    ):
        assert (tmp_path / "cic" / relative).is_file()


def test_tnp_workflow_stage_and_artifact_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import tnp_profile.workflow as workflow

    source = tmp_path / "source.pdb"
    source.write_text("END\n", encoding="utf-8")
    _mock_structure_exports(monkeypatch, workflow, source)
    annotation = {
        "L": 5,
        "L3": 1,
        "residues": [],
        "tetrad_motif": "AAAA",
        "tetrad": [],
        "cdr_h1": "",
        "cdr_h2": "",
        "cdr_h3": "",
    }
    monkeypatch.setattr(workflow, "annotate_kabat", lambda _sequence: annotation)
    monkeypatch.setattr(workflow, "load_residues", lambda _path: [])
    monkeypatch.setattr(workflow, "pick_chain", lambda *_args, **_kwargs: "H")
    monkeypatch.setattr(workflow, "compactness_rho", lambda *_args, **_kwargs: 1.0)
    monkeypatch.setattr(workflow, "compactness_score", lambda *_args, **_kwargs: 2.0)
    monkeypatch.setattr(
        workflow,
        "patch_scores",
        lambda *_args, **_kwargs: {
            "PSH": 0.0,
            "PPC": 0.0,
            "PNC": 0.0,
            "n_vicinity": 0,
            "n_surface": 0,
            "residues": [],
        },
    )
    monkeypatch.setattr(workflow, "load_thresholds", lambda: {"note": "test"})
    monkeypatch.setattr(
        workflow,
        "flag_metrics",
        lambda raw, _thresholds: {
            key: {"value": value, "flag": "pending", "calibrated": False, "thresholds": None}
            for key, value in raw.items()
        },
    )
    stages: list[str] = []

    result = workflow.run_workflow(
        tmp_path / "tnp",
        fasta_text=">H\nAAAAA\n",
        structure_path=source,
        on_stage=stages.append,
    )

    assert stages == ["fold", "score", "done"]
    assert result["summary"]["L"] == 5
    for relative in (
        "exports/pred.cif",
        "exports/residue_features.csv",
        "exports/patches.csv",
        "exports/summary.json",
        "score/metrics.json",
        "workflow_status.json",
    ):
        assert (tmp_path / "tnp" / relative).is_file()
