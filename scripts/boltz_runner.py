#!/usr/bin/env python3
"""Core Boltz2 runner: FASTA / sequences -> YAML -> predict -> standardized output."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

VALID_AA = set("ACDEFGHIKLMNPQRSTVWY")

BOLTZ_BIN = Path(os.environ.get("BOLTZ_BIN", "/home/pengpai/data/envs/boltz2/bin/boltz"))
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


def read_fasta(path: Path | str) -> dict[str, str]:
    path = Path(path)
    seqs: dict[str, str] = {}
    name: str | None = None
    parts: list[str] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            if name is not None:
                seqs[name] = validate_seq("".join(parts), name, str(path))
            name = line[1:].split()[0]
            parts = []
        else:
            parts.append(line.upper())
    if name is None:
        raise ValueError(f"Empty FASTA: {path}")
    seqs[name] = validate_seq("".join(parts), name, str(path))
    return seqs


def parse_fasta_text(text: str) -> dict[str, str]:
    seqs: dict[str, str] = {}
    name: str | None = None
    parts: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            if name is not None:
                seqs[name] = validate_seq("".join(parts), name, "input")
            name = line[1:].split()[0]
            parts = []
        else:
            parts.append(line.upper())
    if name is None:
        raise ValueError("Empty FASTA text")
    seqs[name] = validate_seq("".join(parts), name, "input")
    return seqs


def validate_seq(seq: str, chain_id: str, source: str) -> str:
    bad = sorted({c for c in seq if c not in VALID_AA})
    if bad:
        raise ValueError(f"{source} chain {chain_id}: invalid letters {bad}")
    if len(seq) < 5:
        raise ValueError(f"{source} chain {chain_id}: sequence too short ({len(seq)})")
    return seq


def write_boltz_yaml(seqs: dict[str, str], path: Path) -> None:
    lines = ["version: 1", "sequences:"]
    for chain_id, seq in seqs.items():
        lines.append("  - protein:")
        lines.append(f"      id: {chain_id}")
        lines.append(f"      sequence: {seq}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_fasta(seqs: dict[str, str], path: Path) -> None:
    lines: list[str] = []
    for chain_id, seq in seqs.items():
        lines.append(f">{chain_id}")
        lines.append(seq)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def job_id_from_seqs(seqs: dict[str, str], prefix: str | None = None) -> str:
    payload = json.dumps(seqs, sort_keys=True)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:12]
    if prefix:
        safe = re.sub(r"[^\w\-]", "_", prefix)[:40]
        return f"{safe}_{digest}"
    return digest


def extract_metrics(out_dir: Path, seconds: float | None = None) -> dict:
    cif_files = sorted(out_dir.rglob("*_model_0.cif"))
    if not cif_files:
        raise FileNotFoundError(f"No *_model_0.cif under {out_dir}")
    pred_src = cif_files[0]
    pred_dst = out_dir / "pred.cif"
    shutil.copy2(pred_src, pred_dst)

    conf: dict = {}
    conf_files = sorted(out_dir.rglob("confidence_*_model_0.json"))
    if conf_files:
        conf = json.loads(conf_files[0].read_text())

    metrics = {
        "pred_cif": str(pred_dst),
        "source_cif": str(pred_src),
        "seconds": seconds,
        "confidence_score": conf.get("confidence_score"),
        "ptm": conf.get("ptm"),
        "iptm": conf.get("iptm"),
        "complex_plddt": conf.get("complex_plddt"),
        "complex_iplddt": conf.get("complex_iplddt"),
        "pair_chains_iptm": conf.get("pair_chains_iptm"),
        "chains_ptm": conf.get("chains_ptm"),
    }
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    try:
        from pdockq_runner import compute_pdockq_from_boltz_dir

        pq = compute_pdockq_from_boltz_dir(out_dir)
        if pq.pdockq is not None and pq.pdockq > 0:
            metrics["pdockq"] = pq.pdockq
            metrics["pdockq2"] = pq.pdockq2
            metrics["pdockq_interfaces"] = [
                {
                    "chain_a": i.chain_a,
                    "chain_b": i.chain_b,
                    "contact_pairs": i.contact_pairs,
                    "avg_interface_plddt": i.avg_interface_plddt,
                    "pdockq": i.pdockq,
                    "pdockq2": i.pdockq2,
                }
                for i in pq.interfaces
            ]
            (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    except Exception:
        pass

    return metrics


def cif_to_pdb(cif_path: Path, pdb_path: Path) -> None:
    try:
        from biotite.structure.io.pdbx import CIFFile, get_structure
        from biotite.structure.io.pdb import PDBFile
    except ImportError as exc:
        raise ImportError(
            "biotite required for PDB export; install in boltz2 env or set write_pdb=False"
        ) from exc

    cif = CIFFile.read(str(cif_path))
    stack = get_structure(cif, model=1, use_author_fields=True)
    pdb = PDBFile()
    pdb.set_structure(stack)
    pdb.write(str(pdb_path))


def boltz_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("BOLTZ_CACHE", "/home/pengpai/data/cache/boltz")
    env.setdefault("HF_HOME", "/home/pengpai/data/cache/huggingface")
    env.setdefault("TORCH_HOME", "/home/pengpai/data/cache/torch")
    return env


def run_boltz_predict(
    yaml_path: Path,
    out_dir: Path,
    *,
    use_msa_server: bool = True,
    recycling_steps: int = 3,
    sampling_steps: int = 200,
    diffusion_samples: int = 1,
    model: str = "boltz2",
    devices: int = 1,
    override: bool = True,
) -> subprocess.CompletedProcess:
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(BOLTZ_BIN),
        "predict",
        str(yaml_path),
        "--out_dir",
        str(out_dir),
        "--model",
        model,
        "--recycling_steps",
        str(recycling_steps),
        "--sampling_steps",
        str(sampling_steps),
        "--diffusion_samples",
        str(diffusion_samples),
        "--output_format",
        "mmcif",
        "--devices",
        str(devices),
    ]
    if use_msa_server:
        cmd.append("--use_msa_server")
    if override:
        cmd.append("--override")

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=boltz_env(),
        check=False,
    )


def fold_sequences(
    seqs: dict[str, str],
    out_root: Path | None = None,
    job_id: str | None = None,
    *,
    use_msa_server: bool = True,
    recycling_steps: int = 3,
    sampling_steps: int = 200,
    diffusion_samples: int = 1,
    skip_if_done: bool = True,
    write_pdb: bool = True,
    fasta_path: Path | None = None,
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
        fasta_out = job_dir / "input.fasta"
        yaml_out = job_dir / "input.yaml"
        write_fasta(seqs, fasta_out)
        write_boltz_yaml(seqs, yaml_out)

        proc = run_boltz_predict(
            yaml_out,
            job_dir,
            use_msa_server=use_msa_server,
            recycling_steps=recycling_steps,
            sampling_steps=sampling_steps,
            diffusion_samples=diffusion_samples,
        )
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

        metrics = extract_metrics(job_dir, seconds=elapsed)
        pred_cif = Path(metrics["pred_cif"])
        pred_pdb_path: str | None = None
        if write_pdb and pred_cif.exists():
            try:
                pdb_path = job_dir / "pred.pdb"
                cif_to_pdb(pred_cif, pdb_path)
                pred_pdb_path = str(pdb_path)
            except ImportError:
                pass

        result = FoldResult(
            job_id=job_id,
            status="ok",
            fasta=str(fasta_path or fasta_out),
            num_chains=len(seqs),
            total_length=total_len,
            chains=chains_len,
            pred_cif=str(pred_cif),
            pred_pdb=pred_pdb_path,
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
