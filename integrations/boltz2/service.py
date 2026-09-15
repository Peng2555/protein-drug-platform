"""Boltz2 folding orchestration and stable result contract."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .input import (
    job_id_from_seqs,
    read_fasta,
    validate_boltz_chain_ids,
    write_boltz_yaml,
    write_fasta,
)
from .process import _boltz_run_error, run_boltz_predict
from .results import cif_to_pdb, extract_metrics

DEFAULT_OUT_ROOT = Path(os.environ.get("BOLTZ2_OUT_ROOT", "/home/pengpai/data/Company_Project/Boltz2/outputs"))


@dataclass
class FoldResult:
    job_id: str
    status: str  # ok | failed
    fasta: str | None
    num_chains: int
    total_length: int
    chains: dict[str, int]
    pred_cif: str | None
    pred_pdb: str | None
    iptm: float | None
    ptm: float | None
    confidence_score: float | None
    complex_plddt: float | None
    seconds: float
    pdockq: float | None = None
    pdockq2: float | None = None
    error: str | None = None


def fold_sequences(
    seqs: dict[str, str],
    out_root: Path | None = None,
    job_id: str | None = None,
    *,
    use_msa_server: bool = True,
    recycling_steps: int = 3,
    sampling_steps: int = 200,
    diffusion_samples: int = 1,
    max_parallel_samples: int | None = 5,
    step_scale: float | None = None,
    seed: int | None = None,
    output_format: str = "mmcif",
    model: str = "boltz2",
    method: str | None = None,
    use_potentials: bool = False,
    msa_pairing_strategy: str = "greedy",
    max_msa_seqs: int = 8192,
    subsample_msa: bool = False,
    num_subsampled_msa: int = 1024,
    write_full_pae: bool = False,
    write_full_pde: bool = False,
    write_embeddings: bool = False,
    skip_if_done: bool = True,
    write_pdb: bool = True,
    fasta_path: Path | None = None,
    yaml_text: str | None = None,
) -> FoldResult:
    """Run Boltz2 on a chain_id -> sequence mapping."""
    t0 = time.time()
    out_root = out_root or DEFAULT_OUT_ROOT
    job_id = job_id or job_id_from_seqs(seqs)
    job_dir = out_root / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    chains_len = {k: len(v) for k, v in seqs.items()}
    total_len = sum(chains_len.values())
    result_path = job_dir / "result.json"

    if skip_if_done and (job_dir / "metrics.json").exists():
        m = json.loads((job_dir / "metrics.json").read_text())
        n_have = int(m.get("n_samples") or 1)
        has_pred = (job_dir / "pred.cif").is_file() or (job_dir / "pred.pdb").is_file()
        if n_have >= int(diffusion_samples or 1) and has_pred:
            return FoldResult(
                job_id=job_id,
                status="ok",
                fasta=str(fasta_path) if fasta_path else None,
                num_chains=len(seqs),
                total_length=total_len,
                chains=chains_len,
                pred_cif=m.get("pred_cif"),
                pred_pdb=str(job_dir / "pred.pdb") if (job_dir / "pred.pdb").exists() else None,
                iptm=m.get("iptm"),
                ptm=m.get("ptm"),
                confidence_score=m.get("confidence_score"),
                complex_plddt=m.get("complex_plddt"),
                pdockq=m.get("pdockq"),
                pdockq2=m.get("pdockq2"),
                seconds=m.get("seconds") or 0.0,
            )

    try:
        if seqs:
            validate_boltz_chain_ids(seqs)

        fasta_out = job_dir / "input.fasta"
        yaml_out = job_dir / "input.yaml"
        if seqs:
            write_fasta(seqs, fasta_out)
        if yaml_text and yaml_text.strip():
            yaml_out.write_text(yaml_text, encoding="utf-8")
        else:
            if not seqs:
                raise ValueError("No sequences or YAML provided for Boltz2")
            write_boltz_yaml(seqs, yaml_out)

        predict_kwargs = {
            "use_msa_server": use_msa_server,
            "recycling_steps": recycling_steps,
            "sampling_steps": sampling_steps,
            "diffusion_samples": diffusion_samples,
            "max_parallel_samples": max_parallel_samples,
            "step_scale": step_scale,
            "seed": seed,
            "output_format": output_format,
            "model": model,
            "method": method,
            "use_potentials": use_potentials,
            "msa_pairing_strategy": msa_pairing_strategy,
            "max_msa_seqs": max_msa_seqs,
            "subsample_msa": subsample_msa,
            "num_subsampled_msa": num_subsampled_msa,
            "write_full_pae": write_full_pae,
            "write_full_pde": write_full_pde,
            "write_embeddings": write_embeddings,
        }
        (job_dir / "boltz_params.json").write_text(
            json.dumps(predict_kwargs, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        proc = run_boltz_predict(yaml_out, job_dir, **predict_kwargs)
        elapsed = time.time() - t0

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "boltz predict failed").strip()
            (job_dir / "error.log").write_text(err, encoding="utf-8")
            result = FoldResult(
                job_id=job_id,
                status="failed",
                fasta=str(fasta_path or fasta_out),
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

        # Any diffusion sample is enough to proceed; metrics 会选 best / 算 median
        cif_hits = [p for p in sorted(job_dir.rglob("*_model_*.cif")) if p.name != "pred.cif"]
        pdb_hits = sorted(job_dir.rglob("*_model_*.pdb"))
        if not cif_hits and not pdb_hits:
            err = _boltz_run_error(job_dir, proc)
            (job_dir / "error.log").write_text(err, encoding="utf-8")
            result = FoldResult(
                job_id=job_id,
                status="failed",
                fasta=str(fasta_path or fasta_out),
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

        metrics = extract_metrics(job_dir, seconds=elapsed, num_chains=len(seqs))
        pred_cif_s = metrics.get("pred_cif")
        pred_pdb_s = metrics.get("pred_pdb")
        if write_pdb and pred_cif_s and Path(pred_cif_s).is_file() and not (pred_pdb_s and Path(pred_pdb_s).is_file()):
            try:
                pdb_path = job_dir / "pred.pdb"
                cif_to_pdb(Path(pred_cif_s), pdb_path)
                pred_pdb_s = str(pdb_path)
            except ImportError:
                pass

        result = FoldResult(
            job_id=job_id,
            status="ok",
            fasta=str(fasta_path or fasta_out),
            num_chains=len(seqs),
            total_length=total_len,
            chains=chains_len,
            pred_cif=pred_cif_s,
            pred_pdb=pred_pdb_s,
            iptm=metrics.get("iptm"),
            ptm=metrics.get("ptm"),
            confidence_score=metrics.get("confidence_score"),
            complex_plddt=metrics.get("complex_plddt"),
            pdockq=metrics.get("pdockq"),
            pdockq2=metrics.get("pdockq2"),
            seconds=elapsed,
        )
        result_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
        return result

    except Exception as exc:
        elapsed = time.time() - t0
        result = FoldResult(
            job_id=job_id,
            status="failed",
            fasta=str(fasta_path) if fasta_path else None,
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
            error=str(exc),
        )
        result_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
        return result


def fold_fasta(
    fasta: Path,
    out_root: Path | None = None,
    job_id: str | None = None,
    **kwargs,
) -> FoldResult:
    seqs = read_fasta(fasta)
    jid = job_id or job_id_from_seqs(seqs, prefix=fasta.stem)
    return fold_sequences(seqs, out_root=out_root, job_id=jid, fasta_path=fasta, **kwargs)
