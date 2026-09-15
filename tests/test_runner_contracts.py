"""Runner 公共边界契约；全部测试均不启动模型或外部服务。"""

from __future__ import annotations

import inspect
import json
import sys
from dataclasses import fields
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


def _signature_defaults(callable_obj) -> dict[str, object]:
    return {
        name: parameter.default
        for name, parameter in inspect.signature(callable_obj).parameters.items()
    }


def test_boltz_runner_public_imports_and_fold_result_schema():
    from boltz_runner import (
        FoldResult,
        _model_index,
        extract_metrics,
        fold_sequences,
        parse_fasta_text,
    )

    assert all(callable(obj) for obj in (fold_sequences, parse_fasta_text, extract_metrics, _model_index))
    assert [field.name for field in fields(FoldResult)] == [
        "job_id",
        "status",
        "fasta",
        "num_chains",
        "total_length",
        "chains",
        "pred_cif",
        "pred_pdb",
        "iptm",
        "ptm",
        "confidence_score",
        "complex_plddt",
        "seconds",
        "pdockq",
        "pdockq2",
        "error",
    ]


def test_fold_sequences_signature_names_and_defaults():
    from boltz_runner import fold_sequences

    empty = inspect.Parameter.empty
    assert _signature_defaults(fold_sequences) == {
        "seqs": empty,
        "out_root": None,
        "job_id": None,
        "use_msa_server": True,
        "recycling_steps": 3,
        "sampling_steps": 200,
        "diffusion_samples": 1,
        "max_parallel_samples": 5,
        "step_scale": None,
        "seed": None,
        "output_format": "mmcif",
        "model": "boltz2",
        "method": None,
        "use_potentials": False,
        "msa_pairing_strategy": "greedy",
        "max_msa_seqs": 8192,
        "subsample_msa": False,
        "num_subsampled_msa": 1024,
        "write_full_pae": False,
        "write_full_pde": False,
        "write_embeddings": False,
        "skip_if_done": True,
        "write_pdb": True,
        "fasta_path": None,
        "yaml_text": None,
    }


def test_boltz_input_validation_yaml_and_model_index_contract(tmp_path: Path):
    from boltz_runner import (
        _model_index,
        build_boltz_yaml_text,
        parse_fasta_text,
        validate_boltz_chain_ids,
        write_boltz_yaml,
    )

    assert parse_fasta_text(">H note\nACDEF\n>L\nGGGGG\n") == {"H": "ACDEF", "L": "GGGGG"}
    with pytest.raises(ValueError, match="invalid letters"):
        parse_fasta_text(">H\nACDXF\n")
    with pytest.raises(ValueError, match="too short"):
        parse_fasta_text(">H\nACDE\n")
    with pytest.raises(ValueError, match="不能超过 4"):
        validate_boltz_chain_ids({"HEAVY": "ACDEF"})

    simple_yaml = tmp_path / "input.yaml"
    write_boltz_yaml({"H": "ACDEF", "L": "GGGGG"}, simple_yaml)
    assert simple_yaml.read_text(encoding="utf-8") == (
        "version: 1\n"
        "sequences:\n"
        "  - protein:\n"
        "      id: H\n"
        "      sequence: ACDEF\n"
        "  - protein:\n"
        "      id: L\n"
        "      sequence: GGGGG\n"
    )
    assert build_boltz_yaml_text(
        [
            {"entity": "protein", "ids": ["H"], "sequence": "ac def"},
            {"entity": "ligand", "ids": ["X"], "smiles": "C'C"},
        ],
        affinity_binder="X",
    ).endswith("properties:\n  - affinity:\n      binder: X\n")

    assert _model_index(Path("confidence_input_model_12.json")) == 12
    assert _model_index(Path("input_model_3.cif")) == 3
    assert _model_index(Path("pred.cif")) is None


def test_extract_metrics_selects_best_complex_model_and_stable_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import boltz_runner

    sample_dir = tmp_path / "predictions"
    sample_dir.mkdir()
    for index, iptm in ((0, 0.41), (1, 0.83), (2, 0.62)):
        (sample_dir / f"input_model_{index}.cif").write_text(f"model {index}", encoding="utf-8")
        (sample_dir / f"confidence_input_model_{index}.json").write_text(
            json.dumps({"iptm": iptm, "ptm": 0.7, "confidence_score": iptm}),
            encoding="utf-8",
        )
    monkeypatch.setattr(boltz_runner, "cif_to_pdb", lambda *_args, **_kwargs: None)

    metrics = boltz_runner.extract_metrics(tmp_path, seconds=1.5, num_chains=2)

    assert metrics["selected_model"] == 1
    assert metrics["iptm"] == 0.62
    assert (tmp_path / "pred.cif").read_text(encoding="utf-8") == "model 1"
    assert (tmp_path / "metrics.json").is_file()


def test_worker_exports_exactly_thirteen_named_celery_tasks():
    from worker import tasks

    task_names = [
        "run_fold_job",
        "run_md_job",
        "run_maturation_job",
        "run_ras_docking_job",
        "run_small_molecule_docking_job",
        "run_developability_job",
        "run_design_job",
        "run_rosetta_eval_job",
        "run_affinity_redesign_job",
        "run_masking_peptide_job",
        "run_hydro_redesign_job",
        "run_cic_profile_job",
        "run_tnp_profile_job",
    ]
    assert len(task_names) == 13
    assert {
        name
        for name, value in vars(tasks).items()
        if name.startswith("run_") and getattr(value, "name", "").startswith("worker.tasks.run_")
    } == set(task_names)
    for name in task_names:
        task = getattr(tasks, name)
        assert task.name == f"worker.tasks.{name}"
