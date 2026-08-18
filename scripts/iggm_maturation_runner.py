#!/usr/bin/env python3
"""IgGM affinity maturation runner for BoltzFold platform."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from boltz_runner import cif_to_pdb, fold_sequences as boltz_fold_sequences, parse_fasta_text
from iggm_mask_builder import build_maturation_fastas, write_maturation_fastas
from iggm_mutation_table import build_mutation_table

IGGM_ROOT = Path(os.environ.get("IGGM_ROOT", "/home/pengpai/data/Company_Project/IgGM"))
IGGM_PY = Path(os.environ.get("IGGM_PY", "/home/pengpai/data/envs/IgGM/bin/python"))
DESIGN_PY = IGGM_ROOT / "design.py"


@dataclass
class MaturationResult:
    status: str  # ok | failed
    seconds: float
    results: dict | None = None
    error: str | None = None
    stage: str | None = None


def _default_gpu_ids(gpu_count: int) -> list[int]:
    cap = int(os.environ.get("CELERY_GPU_COUNT", "4"))
    n = max(1, min(gpu_count, cap))
    return list(range(n))


def structure_to_pdb(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    suffix = src.suffix.lower()
    if suffix in {".pdb", ".ent"}:
        shutil.copy2(src, dest)
        return dest
    if suffix in {".cif", ".mmcif"}:
        cif_to_pdb(src, dest)
        return dest
    raise ValueError(f"Unsupported structure format: {src}")


def run_fold_for_structure(
    seqs: dict[str, str],
    work_dir: Path,
    *,
    fold_engine: str,
    fold_params: dict | None = None,
) -> Path:
    """Run Boltz2 or ESMFold2 and return path to pred.cif."""
    fold_dir = work_dir / "fold"
    fold_dir.mkdir(parents=True, exist_ok=True)
    fold_params = fold_params or {}

    if fold_engine == "esmfold2":
        from esmfold_runner import fold_sequences as esmfold_fold_sequences

        result = esmfold_fold_sequences(
            seqs,
            out_root=fold_dir.parent,
            job_id=fold_dir.name,
            skip_if_done=False,
            write_pdb=False,
            num_loops=fold_params.get("num_loops"),
            num_sampling_steps=fold_params.get("num_sampling_steps"),
            num_diffusion_samples=fold_params.get("num_diffusion_samples"),
            seed=fold_params.get("seed"),
        )
    else:
        result = boltz_fold_sequences(
            seqs,
            out_root=fold_dir.parent,
            job_id=fold_dir.name,
            skip_if_done=False,
            use_msa_server=fold_params.get("use_msa_server", True),
            recycling_steps=fold_params.get("recycling_steps", 3),
            sampling_steps=fold_params.get("sampling_steps", 200),
            diffusion_samples=fold_params.get("diffusion_samples", 1),
            write_pdb=False,
        )

    if result.status != "ok" or not result.pred_cif:
        raise RuntimeError(result.error or f"{fold_engine} structure prediction failed")

    pred = Path(result.pred_cif)
    if not pred.is_file():
        raise FileNotFoundError(f"Predicted structure not found: {pred}")
    return pred


def _design_cmd(
    *,
    mask_fasta: Path,
    origin_fasta: Path,
    complex_pdb: Path,
    output_dir: Path,
    num_samples: int,
    steps: int,
    max_antigen_size: int,
    temperature: float,
    chunk_size: int,
    relax: bool,
    epitope: list[int] | None,
) -> list[str]:
    cmd = [
        str(IGGM_PY),
        str(DESIGN_PY),
        "--fasta",
        str(mask_fasta),
        "--fasta_origin",
        str(origin_fasta),
        "--antigen",
        str(complex_pdb),
        "--output",
        str(output_dir),
        "--run_task",
        "affinity_maturation",
        "--num_samples",
        str(num_samples),
        "--steps",
        str(steps),
        "--max_antigen_size",
        str(max_antigen_size),
        "--temperature",
        str(temperature),
        "--chunk_size",
        str(chunk_size),
    ]
    if relax:
        cmd.append("--relax")
    if epitope:
        cmd.extend(["--epitope", *[str(x) for x in epitope]])
    return cmd


def run_iggm_maturation(
    *,
    work_dir: Path,
    mask_fasta: Path,
    origin_fasta: Path,
    complex_pdb: Path,
    origin_seq_h: str,
    num_samples: int = 100,
    steps: int = 10,
    max_antigen_size: int = 384,
    temperature: float = 1.0,
    chunk_size: int = 64,
    relax: bool = False,
    epitope: list[int] | None = None,
    gpu_count: int = 2,
    gpu_ids: list[int] | None = None,
    on_stage: Callable[[str], None] | None = None,
) -> MaturationResult:
    t0 = time.time()
    mat_dir = work_dir / "maturation"
    mat_dir.mkdir(parents=True, exist_ok=True)

    if on_stage:
        on_stage("maturation")

    gpu_ids = gpu_ids if gpu_ids is not None else _default_gpu_ids(gpu_count)
    gpu_ids = gpu_ids[: max(1, gpu_count)]
    procs: list[subprocess.Popen] = []
    logs: list[Path] = []

    base_cmd = _design_cmd(
        mask_fasta=mask_fasta,
        origin_fasta=origin_fasta,
        complex_pdb=complex_pdb,
        output_dir=mat_dir,
        num_samples=num_samples,
        steps=steps,
        max_antigen_size=max_antigen_size,
        temperature=temperature,
        chunk_size=chunk_size,
        relax=relax,
        epitope=epitope,
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(IGGM_ROOT)

    for gpu in gpu_ids:
        log_path = mat_dir / f"rank{gpu}.log"
        logs.append(log_path)
        gpu_env = env.copy()
        gpu_env["CUDA_VISIBLE_DEVICES"] = str(gpu)
        with open(log_path, "w", encoding="utf-8") as log_f:
            proc = subprocess.Popen(
                base_cmd,
                cwd=str(IGGM_ROOT),
                env=gpu_env,
                stdout=log_f,
                stderr=subprocess.STDOUT,
            )
        procs.append(proc)

    exit_codes = [proc.wait() for proc in procs]

    fasta_outputs = list(mat_dir.glob("*.fasta"))
    if not fasta_outputs:
        err_parts = []
        for log in logs:
            if log.is_file():
                err_parts.append(log.read_text(encoding="utf-8", errors="replace")[-2000:])
        err = "\n---\n".join(err_parts) or f"IgGM exited with codes {exit_codes}"
        return MaturationResult(
            status="failed",
            seconds=time.time() - t0,
            error=err[-8000:],
            stage="maturation",
        )

    if on_stage:
        on_stage("aggregate")

    env_collect = env.copy()
    collect_code = f"""
import sys
sys.path.insert(0, {str(IGGM_ROOT)!r})
sys.path.insert(0, {str(IGGM_ROOT / "scripts")!r})
from collect_plot import run_collect_plot
run_collect_plot(
    {str(mat_dir)!r},
    {str(mask_fasta)!r},
    original_seq_h={origin_seq_h!r},
    original_seq_l=None,
    maturation=True,
)
"""
    agg = subprocess.run(
        [str(IGGM_PY), "-c", collect_code],
        cwd=str(IGGM_ROOT),
        capture_output=True,
        text=True,
        env=env_collect,
    )
    agg_err = None
    if agg.returncode != 0:
        agg_err = (agg.stderr or agg.stdout or "collect_plot failed").strip()

    dedup_csv: Path | None = None
    summary_dir: Path | None = None
    for candidate in work_dir.rglob("dedup_diff_freq.csv"):
        dedup_csv = candidate
        summary_dir = candidate.parent
        break

    variant_count_raw = len(fasta_outputs)
    variant_count_dedup = 0
    if dedup_csv and dedup_csv.is_file():
        import csv

        with dedup_csv.open(encoding="utf-8") as f:
            variant_count_dedup = max(0, sum(1 for _ in csv.DictReader(f)))

    results = {
        "variant_count_raw": variant_count_raw,
        "variant_count_dedup": variant_count_dedup,
        "maturation_dir": str(mat_dir),
        "summary_dir": str(summary_dir) if summary_dir else None,
        "dedup_csv": str(dedup_csv) if dedup_csv and dedup_csv.is_file() else None,
        "dup_csv": str(summary_dir / "dup.csv") if summary_dir and (summary_dir / "dup.csv").is_file() else None,
        "complex_pdb": str(complex_pdb),
        "gpu_ids": gpu_ids,
        "aggregate_error": agg_err,
    }

    if agg_err and not (dedup_csv and dedup_csv.is_file()):
        return MaturationResult(
            status="failed",
            seconds=time.time() - t0,
            results=results,
            error=agg_err[-8000:],
            stage="aggregate",
        )

    return MaturationResult(
        status="ok",
        seconds=time.time() - t0,
        results=results,
        stage="done",
    )


def run_maturation_pipeline(
    *,
    work_dir: Path,
    fasta_text: str,
    params: dict,
    structure_path: Path | None = None,
    on_stage: Callable[[str], None] | None = None,
) -> MaturationResult:
    """Full pipeline: optional fold → prep → IgGM maturation → aggregate."""
    t0 = time.time()
    work_dir.mkdir(parents=True, exist_ok=True)

    binder_chain = params.get("binder_chain_id", "H")
    antigen_chain = params.get("antigen_chain_id", "A")
    cdr_mask = params.get("cdr_mask") or ["CDR-H3"]
    structure_source = params.get("structure_source", "upload")

    seqs = parse_fasta_text(fasta_text)
    origin, mask = build_maturation_fastas(
        seqs,
        binder_chain_id=binder_chain,
        antigen_chain_id=antigen_chain,
        cdr_mask=cdr_mask,
    )
    origin_path, mask_path = write_maturation_fastas(work_dir, origin, mask)

    complex_pdb = work_dir / "input" / "complex.pdb"

    try:
        if structure_source in ("boltz2", "esmfold2"):
            if on_stage:
                on_stage("fold")
            pred_cif = run_fold_for_structure(
                origin,
                work_dir,
                fold_engine=structure_source,
                fold_params=params.get("fold_params") or {},
            )
            structure_to_pdb(pred_cif, complex_pdb)
        elif structure_source == "fold_job":
            if not structure_path or not structure_path.is_file():
                raise FileNotFoundError("Parent fold structure not found")
            structure_to_pdb(structure_path, complex_pdb)
        elif structure_source == "upload":
            if not structure_path or not structure_path.is_file():
                raise FileNotFoundError("Uploaded structure not found")
            structure_to_pdb(structure_path, complex_pdb)
        else:
            raise ValueError(f"Unknown structure_source: {structure_source}")

        if on_stage:
            on_stage("prep")

        iggm_params = params.get("iggm") or params
        result = run_iggm_maturation(
            work_dir=work_dir,
            mask_fasta=mask_path,
            origin_fasta=origin_path,
            complex_pdb=complex_pdb,
            origin_seq_h=origin["H"],
            num_samples=int(iggm_params.get("num_samples", 100)),
            steps=int(iggm_params.get("steps", 10)),
            max_antigen_size=int(iggm_params.get("max_antigen_size", 384)),
            temperature=float(iggm_params.get("temperature", 1.0)),
            chunk_size=int(iggm_params.get("chunk_size", 64)),
            relax=bool(iggm_params.get("relax", False)),
            epitope=iggm_params.get("epitope"),
            gpu_count=int(iggm_params.get("gpu_count", 2)),
            gpu_ids=iggm_params.get("gpu_ids"),
            on_stage=on_stage,
        )
        if result.status == "ok" and result.results:
            try:
                mutation_meta = build_mutation_table(
                    fasta_dir=work_dir / "maturation",
                    origin_fasta=origin_path,
                    mask_fasta=mask_path,
                    out_dir=work_dir / "results" / "maturation",
                    chain_id=binder_chain,
                )
                result.results["cdr3_csv"] = mutation_meta["cdr3_csv"]
                result.results["mutation_table"] = mutation_meta
            except Exception as exc:
                result.results["mutation_table_error"] = str(exc)[:2000]
        result.seconds = time.time() - t0
        (work_dir / "result.json").write_text(
            json.dumps(asdict(result), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return result
    except Exception as exc:
        result = MaturationResult(
            status="failed",
            seconds=time.time() - t0,
            error=str(exc),
        )
        (work_dir / "result.json").write_text(
            json.dumps(asdict(result), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return result
