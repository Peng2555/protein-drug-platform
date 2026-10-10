"""Fine-grained Boltz2 integration tests; no model or external service is started."""

from __future__ import annotations

import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _write_sample(
    directory: Path,
    index: int,
    *,
    suffix: str = "cif",
    iptm: float = 0.0,
    ptm: float = 0.0,
    confidence: float = 0.0,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"input_model_{index}.{suffix}").write_text(
        f"{suffix} model {index}", encoding="utf-8"
    )
    (directory / f"confidence_input_model_{index}.json").write_text(
        json.dumps(
            {
                "iptm": iptm,
                "ptm": ptm,
                "confidence_score": confidence,
            }
        ),
        encoding="utf-8",
    )


def test_input_component_metadata_and_yaml(tmp_path: Path):
    from integrations.boltz2.input import (
        build_boltz_yaml_text,
        chains_meta_from_components,
        polymer_seqs_from_components,
        write_boltz_complex_yaml,
    )

    components = [
        {
            "entity": "protein",
            "ids": ["A", "B"],
            "sequence": "ac def",
            "cyclic": True,
            "modifications": [{"position": 2, "ccd": "MSE"}],
        },
        {"entity": "ligand", "ids": ["L"], "smiles": "C'C"},
    ]
    text = build_boltz_yaml_text(
        components,
        constraints=[
            {
                "type": "contact",
                "token1": ["A", 1],
                "token2": ["L", 1],
                "max_distance": 4,
                "force": True,
            }
        ],
        affinity_binder="L",
    )
    output = tmp_path / "input.yaml"

    assert write_boltz_complex_yaml(
        output,
        components,
        constraints=[
            {
                "type": "contact",
                "token1": ["A", 1],
                "token2": ["L", 1],
                "max_distance": 4,
                "force": True,
            }
        ],
        affinity_binder="L",
    ) == text
    assert output.read_text(encoding="utf-8") == text
    assert "      id: [A, B]\n" in text
    assert "      smiles: 'C''C'\n" in text
    assert polymer_seqs_from_components(components) == {"A": "ACDEF", "B": "ACDEF"}
    assert chains_meta_from_components(components) == {"A": 5, "B": 5, "L": 3}


def test_process_builds_cli_argv_and_uses_check_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from integrations.boltz2 import process

    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(argv, 0, "ok", "")

    monkeypatch.setattr(process.subprocess, "run", fake_run)
    yaml_path = tmp_path / "input.yaml"
    result = process.run_boltz_predict(
        yaml_path,
        tmp_path / "out",
        use_msa_server=True,
        recycling_steps=4,
        sampling_steps=50,
        diffusion_samples=3,
        max_parallel_samples=2,
        step_scale=1.5,
        seed=7,
        output_format="pdb",
        model="boltz1",
        method="foo",
        use_potentials=True,
        msa_pairing_strategy="complete",
        max_msa_seqs=42,
        subsample_msa=True,
        num_subsampled_msa=21,
        write_full_pae=True,
        write_full_pde=True,
        write_embeddings=True,
    )

    argv = captured["argv"]
    assert result.returncode == 0
    assert argv[:3] == [str(process.BOLTZ_BIN), "predict", str(yaml_path)]
    assert argv[argv.index("--output_format") + 1] == "pdb"
    assert argv[argv.index("--model") + 1] == "boltz1"
    assert argv[argv.index("--diffusion_samples") + 1] == "3"
    assert {
        "--use_msa_server",
        "--use_potentials",
        "--subsample_msa",
        "--write_full_pae",
        "--write_full_pde",
        "--write_embeddings",
        "--override",
    }.issubset(argv)
    assert captured["kwargs"]["capture_output"] is True
    assert captured["kwargs"]["text"] is True
    assert captured["kwargs"]["check"] is False


def test_results_complex_selects_max_iptm_but_reports_median(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from integrations.boltz2 import results

    samples = tmp_path / "predictions"
    _write_sample(samples, 0, iptm=0.2, ptm=0.9, confidence=0.2)
    _write_sample(samples, 1, iptm=0.8, ptm=0.4, confidence=0.8)
    _write_sample(samples, 2, iptm=0.5, ptm=0.6, confidence=0.5)
    monkeypatch.setattr(results, "cif_to_pdb", lambda *_args: None)

    metrics = results.extract_metrics(tmp_path, num_chains=2)

    assert metrics["selected_model"] == 1
    assert metrics["iptm"] == 0.5
    assert metrics["iptm_max"] == 0.8
    assert metrics["has_interface"] is True
    assert (tmp_path / "pred.cif").read_text(encoding="utf-8") == "cif model 1"


def test_results_monomer_selects_ptm_and_suppresses_iptm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from integrations.boltz2 import results

    samples = tmp_path / "predictions"
    _write_sample(samples, 0, iptm=0.9, ptm=0.4, confidence=0.9)
    _write_sample(samples, 1, iptm=0.1, ptm=0.8, confidence=0.2)
    monkeypatch.setattr(results, "cif_to_pdb", lambda *_args: None)

    metrics = results.extract_metrics(tmp_path, num_chains=1)

    assert metrics["selected_model"] == 1
    assert metrics["iptm"] is None
    assert metrics["ptm"] == 0.8
    assert metrics["has_interface"] is False
    assert all(sample["iptm"] is None for sample in metrics["samples"])


def test_results_pdb_only_creates_stable_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from integrations.boltz2 import results

    _write_sample(tmp_path / "predictions", 0, suffix="pdb", ptm=0.7, confidence=0.6)

    def fake_pdb_to_cif(_pdb: Path, cif: Path) -> None:
        cif.write_text("converted cif", encoding="utf-8")

    monkeypatch.setattr(results, "pdb_to_cif", fake_pdb_to_cif)
    metrics = results.extract_metrics(tmp_path, num_chains=1)

    assert Path(metrics["pred_pdb"]).read_text(encoding="utf-8") == "pdb model 0"
    assert Path(metrics["pred_cif"]).read_text(encoding="utf-8") == "converted cif"


def test_service_success_failure_and_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from integrations.boltz2 import service

    calls = {"predict": 0}

    def successful_predict(_yaml: Path, out_dir: Path, **_kwargs):
        calls["predict"] += 1
        _write_sample(out_dir / "predictions", 0, iptm=0.7, ptm=0.6, confidence=0.5)
        return subprocess.CompletedProcess([], 0, "ok", "")

    def fake_metrics(out_dir: Path, **_kwargs):
        pred = out_dir / "pred.cif"
        pred.write_text("selected", encoding="utf-8")
        metrics = {
            "pred_cif": str(pred),
            "pred_pdb": None,
            "iptm": 0.7,
            "ptm": 0.6,
            "confidence_score": 0.5,
            "complex_plddt": 0.4,
            "n_samples": 1,
            "seconds": 1.0,
        }
        (out_dir / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
        return metrics

    monkeypatch.setattr(service, "run_boltz_predict", successful_predict)
    monkeypatch.setattr(service, "extract_metrics", fake_metrics)
    monkeypatch.setattr(service, "cif_to_pdb", lambda *_args: None)
    result = service.fold_sequences(
        {"A": "ACDEF"}, out_root=tmp_path, job_id="success", write_pdb=False
    )

    job_dir = tmp_path / "success"
    assert result.status == "ok"
    assert calls["predict"] == 1
    assert {
        "input.fasta",
        "input.yaml",
        "boltz_params.json",
        "pred.cif",
        "metrics.json",
        "result.json",
    }.issubset(path.name for path in job_dir.iterdir())

    cached = service.fold_sequences(
        {"A": "ACDEF"}, out_root=tmp_path, job_id="success", write_pdb=False
    )
    assert cached.status == "ok"
    assert calls["predict"] == 1

    monkeypatch.setattr(
        service,
        "run_boltz_predict",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 2, "", "x" * 5000),
    )
    failed = service.fold_sequences(
        {"A": "ACDEF"}, out_root=tmp_path, job_id="failed", write_pdb=False
    )
    assert failed.status == "failed"
    assert len(failed.error or "") == 4000
    assert (tmp_path / "failed" / "error.log").read_text(encoding="utf-8") == "x" * 5000
    assert (tmp_path / "failed" / "result.json").is_file()


def test_shim_exports_identical_symbols_and_signature():
    import boltz_runner
    import integrations.boltz2 as integration

    assert boltz_runner.FoldResult is integration.FoldResult
    assert boltz_runner.fold_sequences is integration.fold_sequences
    assert boltz_runner._model_index is integration._model_index
    assert inspect.signature(boltz_runner.fold_sequences) == inspect.signature(
        integration.fold_sequences
    )
    assert set(integration.__all__).issubset(set(boltz_runner.__all__))
