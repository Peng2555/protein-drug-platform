#!/usr/bin/env python3
"""ESMFold2 runner — same FoldResult interface as boltz_runner."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from boltz_runner import FoldResult, job_id_from_seqs, parse_fasta_text, write_fasta

ESMFOLD_PY = Path(os.environ.get("ESMFOLD_PY", "/home/pengpai/data/envs/esmfold2/bin/python"))
DEFAULT_OUT_ROOT = Path(os.environ.get("BOLTZ2_OUT_ROOT", str(ROOT / "outputs")))
MODEL_NAME = os.environ.get("ESMFOLD_MODEL", "biohub/ESMFold2")
DEFAULT_OPTS = {
    "num_loops": int(os.environ.get("ESMFOLD_NUM_LOOPS", "10")),
    "num_sampling_steps": int(os.environ.get("ESMFOLD_NUM_SAMPLING_STEPS", "68")),
    "num_diffusion_samples": int(os.environ.get("ESMFOLD_NUM_DIFFUSION_SAMPLES", "5")),
    "seed": int(os.environ.get("ESMFOLD_SEED", "0")),
}
INLINE = os.environ.get("ESMFOLD_RUNNER_INLINE") == "1"
PARAMS_FILE = "esmfold_params.json"

_MODEL = None
_BUILDER = None


def _device() -> str:
    return os.environ.get("ESMFOLD_DEVICE", "cuda:0")


def _resolve_opts(
    job_dir: Path | None = None,
    *,
    num_loops: int | None = None,
    num_sampling_steps: int | None = None,
    num_diffusion_samples: int | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    opts = dict(DEFAULT_OPTS)
    if job_dir is not None:
        params_path = job_dir / PARAMS_FILE
        if params_path.is_file():
            opts.update(json.loads(params_path.read_text(encoding="utf-8")))
    overrides = {
        "num_loops": num_loops,
        "num_sampling_steps": num_sampling_steps,
        "num_diffusion_samples": num_diffusion_samples,
        "seed": seed,
    }
    opts.update({k: v for k, v in overrides.items() if v is not None})
    opts["model"] = MODEL_NAME
    return opts


def _write_opts(job_dir: Path, opts: dict[str, Any]) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / PARAMS_FILE).write_text(json.dumps(opts, indent=2), encoding="utf-8")


def _esmfold_env(opts: dict[str, Any] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("HF_HOME", "/home/pengpai/data/cache/huggingface")
    env.setdefault("TORCH_HOME", "/home/pengpai/data/cache/torch")
    env["ESMFOLD_RUNNER_INLINE"] = "1"
    if opts:
        env["ESMFOLD_NUM_LOOPS"] = str(opts["num_loops"])
        env["ESMFOLD_NUM_SAMPLING_STEPS"] = str(opts["num_sampling_steps"])
        env["ESMFOLD_NUM_DIFFUSION_SAMPLES"] = str(opts["num_diffusion_samples"])
        env["ESMFOLD_SEED"] = str(opts["seed"])
    return env


def _pick_best(result):
    if isinstance(result, list):
        return max(result, key=lambda r: float(r.iptm if r.iptm is not None else r.plddt.mean()))
    return result


def _load_esmfold():
    global _MODEL, _BUILDER
    if _MODEL is not None:
        return _MODEL, _BUILDER

    from transformers.models.esmfold2.modeling_esmfold2 import ESMFold2Model
    from esm.models.esmfold2 import ESMFold2InputBuilder

    device = _device()
    t0 = time.time()
    model = ESMFold2Model.from_pretrained(MODEL_NAME).to(device).eval()
    model.set_kernel_backend("fused")
    _MODEL = model
    _BUILDER = ESMFold2InputBuilder()
    print(f"ESMFold2 model ready on {device} in {time.time() - t0:.1f}s", file=sys.stderr)
    return _MODEL, _BUILDER


def _configure_memory(model, total_length: int) -> None:
    if total_length > 450:
        model.set_chunk_size(64)
    else:
        model.set_chunk_size(None)


def _write_plddt_npz(plddt, job_dir: Path) -> Path:
    out = job_dir / "plddt_model_0.npz"
    np.savez(out, plddt=np.asarray(plddt, dtype=np.float32))
    return out


def _attach_pdockq(job_dir: Path, metrics: dict) -> None:
    try:
        from pdockq_runner import compute_pdockq_from_boltz_dir

        pq = compute_pdockq_from_boltz_dir(job_dir)
        if pq.pdockq is not None:
            metrics["pdockq"] = pq.pdockq
            metrics["pdockq2"] = pq.pdockq2
    except Exception:
        pass


def _fold_inline(
    seqs: dict[str, str],
    job_dir: Path,
    *,
    skip_if_done: bool = False,
    num_loops: int | None = None,
    num_sampling_steps: int | None = None,
    num_diffusion_samples: int | None = None,
    seed: int | None = None,
) -> FoldResult:
    import torch
    from esm.models.esmfold2 import ProteinInput, StructurePredictionInput

    opts = _resolve_opts(
        job_dir,
        num_loops=num_loops,
        num_sampling_steps=num_sampling_steps,
        num_diffusion_samples=num_diffusion_samples,
        seed=seed,
    )
    chains_len = {k: len(v) for k, v in seqs.items()}
    total_len = sum(chains_len.values())
    result_path = job_dir / "result.json"
    metrics_path = job_dir / "metrics.json"

    if skip_if_done and metrics_path.is_file():
        m = json.loads(metrics_path.read_text(encoding="utf-8"))
        return FoldResult(
            job_id=job_dir.name,
            status="ok",
            fasta=str(job_dir / "input.fasta"),
            num_chains=len(seqs),
            total_length=total_len,
            chains=chains_len,
            pred_cif=m.get("pred_cif"),
            pred_pdb=str(job_dir / "pred.pdb") if (job_dir / "pred.pdb").exists() else None,
            iptm=m.get("iptm"),
            ptm=m.get("ptm"),
            confidence_score=None,
            complex_plddt=m.get("complex_plddt"),
            seconds=m.get("seconds") or 0.0,
            pdockq=m.get("pdockq"),
            pdockq2=m.get("pdockq2"),
        )

    t0 = time.time()
    try:
        model, builder = _load_esmfold()
        _configure_memory(model, total_len)
        spi = StructurePredictionInput(
            sequences=[ProteinInput(id=cid, sequence=seq) for cid, seq in seqs.items()]
        )
        with torch.inference_mode():
            results = builder.fold(
                model,
                spi,
                num_loops=int(opts["num_loops"]),
                num_sampling_steps=int(opts["num_sampling_steps"]),
                num_diffusion_samples=int(opts["num_diffusion_samples"]),
                seed=int(opts["seed"]),
                complex_id=job_dir.name,
            )
        best = _pick_best(results)
        elapsed = time.time() - t0

        pred_cif = job_dir / "pred.cif"
        pred_cif.write_text(best.complex.to_mmcif(), encoding="utf-8")
        _write_plddt_npz(best.plddt, job_dir)

        metrics = {
            "pred_cif": str(pred_cif),
            "engine": "esmfold2",
            "model": opts["model"],
            "num_loops": int(opts["num_loops"]),
            "num_sampling_steps": int(opts["num_sampling_steps"]),
            "num_diffusion_samples": int(opts["num_diffusion_samples"]),
            "seed": int(opts["seed"]),
            "complex_plddt": float(best.plddt.mean()),
            "plddt_mean": float(best.plddt.mean()),
            "ptm": float(best.ptm) if best.ptm is not None else None,
            "iptm": float(best.iptm) if best.iptm is not None else None,
            "seconds": elapsed,
        }
        _attach_pdockq(job_dir, metrics)
        metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

        result = FoldResult(
            job_id=job_dir.name,
            status="ok",
            fasta=str(job_dir / "input.fasta"),
            num_chains=len(seqs),
            total_length=total_len,
            chains=chains_len,
            pred_cif=str(pred_cif),
            pred_pdb=None,
            iptm=metrics.get("iptm"),
            ptm=metrics.get("ptm"),
            confidence_score=None,
            complex_plddt=metrics.get("complex_plddt"),
            seconds=elapsed,
            pdockq=metrics.get("pdockq"),
            pdockq2=metrics.get("pdockq2"),
        )
        result_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
        return result
    except Exception as exc:
        elapsed = time.time() - t0
        err = str(exc)
        (job_dir / "error.log").write_text(err, encoding="utf-8")
        result = FoldResult(
            job_id=job_dir.name,
            status="failed",
            fasta=str(job_dir / "input.fasta"),
            num_chains=len(seqs),
            total_length=total_len,
            chains=chains_len,
            pred_cif=None,
            pred_pdb=None,
            iptm=None,
            ptm=None,
            confidence_score=None,
            complex_plddt=None,
            seconds=elapsed,
            error=err[-4000:],
        )
        result_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
        return result


def _fold_subprocess(
    seqs: dict[str, str],
    job_dir: Path,
    *,
    skip_if_done: bool = False,
    num_loops: int | None = None,
    num_sampling_steps: int | None = None,
    num_diffusion_samples: int | None = None,
    seed: int | None = None,
) -> FoldResult:
    job_dir.mkdir(parents=True, exist_ok=True)
    write_fasta(seqs, job_dir / "input.fasta")
    opts = _resolve_opts(
        job_dir,
        num_loops=num_loops,
        num_sampling_steps=num_sampling_steps,
        num_diffusion_samples=num_diffusion_samples,
        seed=seed,
    )
    _write_opts(job_dir, opts)
    cmd = [
        str(ESMFOLD_PY),
        str(Path(__file__).resolve()),
        "fold",
        "--job-dir",
        str(job_dir),
    ]
    if skip_if_done:
        cmd.append("--skip-if-done")
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=_esmfold_env(opts),
        check=False,
    )
    result_path = job_dir / "result.json"
    if not result_path.is_file():
        err = (proc.stderr or proc.stdout or "ESMFold2 subprocess failed").strip()
        chains_len = {k: len(v) for k, v in seqs.items()}
        return FoldResult(
            job_id=job_dir.name,
            status="failed",
            fasta=str(job_dir / "input.fasta"),
            num_chains=len(seqs),
            total_length=sum(chains_len.values()),
            chains=chains_len,
            pred_cif=None,
            pred_pdb=None,
            iptm=None,
            ptm=None,
            confidence_score=None,
            complex_plddt=None,
            seconds=0.0,
            error=err[-4000:],
        )
    data = json.loads(result_path.read_text(encoding="utf-8"))
    return FoldResult(**data)


def fold_sequences(
    seqs: dict[str, str],
    out_root: Path | None = None,
    job_id: str | None = None,
    *,
    skip_if_done: bool = True,
    num_loops: int | None = None,
    num_sampling_steps: int | None = None,
    num_diffusion_samples: int | None = None,
    seed: int | None = None,
    **kwargs,
) -> FoldResult:
    out_root = out_root or DEFAULT_OUT_ROOT
    job_id = job_id or job_id_from_seqs(seqs)
    job_dir = out_root / job_id
    fold_kwargs = {
        "skip_if_done": skip_if_done,
        "num_loops": num_loops,
        "num_sampling_steps": num_sampling_steps,
        "num_diffusion_samples": num_diffusion_samples,
        "seed": seed,
    }
    if INLINE:
        return _fold_inline(seqs, job_dir, **fold_kwargs)
    return _fold_subprocess(seqs, job_dir, **fold_kwargs)


def _cli_fold() -> None:
    parser = argparse.ArgumentParser(description="Run one ESMFold2 job (internal)")
    parser.add_argument("fold", nargs="?")
    parser.add_argument("--job-dir", type=Path, required=True)
    parser.add_argument("--skip-if-done", action="store_true")
    args = parser.parse_args()
    fasta = args.job_dir / "input.fasta"
    if not fasta.is_file():
        raise SystemExit(f"Missing {fasta}")
    seqs = parse_fasta_text(fasta.read_text(encoding="utf-8"))
    os.environ["ESMFOLD_RUNNER_INLINE"] = "1"
    result = _fold_inline(seqs, args.job_dir, skip_if_done=args.skip_if_done)
    if result.status != "ok":
        raise SystemExit(result.error or "fold failed")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "fold":
        _cli_fold()
    else:
        raise SystemExit("Usage: esmfold_runner.py fold --job-dir <dir>")
