"""Boltz2 单次复合物预测（由 boltz2 env 调用）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_runner():
    from affinity_redesign.config import settings

    scripts = str(settings.boltz2_root / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import boltz_runner  # type: ignore

    return boltz_runner


def fold_one(
    *,
    fasta: Path,
    out_root: Path,
    job_id: str,
    use_msa_server: bool,
    recycling_steps: int,
    sampling_steps: int,
    diffusion_samples: int,
) -> dict:
    boltz_runner = _load_runner()
    seqs = boltz_runner.read_fasta(fasta)
    result = boltz_runner.fold_sequences(
        seqs,
        out_root=out_root,
        job_id=job_id,
        use_msa_server=use_msa_server,
        recycling_steps=recycling_steps,
        sampling_steps=sampling_steps,
        diffusion_samples=diffusion_samples,
        skip_if_done=True,
        write_pdb=True,
    )
    extra = {}
    metrics_path = out_root / job_id / "metrics.json"
    if metrics_path.is_file():
        extra = json.loads(metrics_path.read_text(encoding="utf-8"))
    payload = {
        "status": result.status,
        "job_id": result.job_id,
        "iptm": result.iptm,
        "ptm": result.ptm,
        "confidence_score": result.confidence_score,
        "complex_plddt": result.complex_plddt,
        "complex_iplddt": extra.get("complex_iplddt"),
        "pdockq": result.pdockq or extra.get("pdockq"),
        "pdockq2": result.pdockq2 or extra.get("pdockq2"),
        "pair_chains_iptm": extra.get("pair_chains_iptm"),
        "seconds": result.seconds,
        "pred_pdb": result.pred_pdb,
        "pred_cif": result.pred_cif,
        "error": result.error,
    }
    out_path = out_root / job_id / "fold_result.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--fasta", required=True)
    p.add_argument("--out-root", required=True)
    p.add_argument("--job-id", required=True)
    p.add_argument("--use-msa-server", action="store_true")
    p.add_argument("--recycling-steps", type=int, default=3)
    p.add_argument("--sampling-steps", type=int, default=200)
    p.add_argument("--diffusion-samples", type=int, default=1)
    args = p.parse_args()
    result = fold_one(
        fasta=Path(args.fasta),
        out_root=Path(args.out_root),
        job_id=args.job_id,
        use_msa_server=args.use_msa_server,
        recycling_steps=args.recycling_steps,
        sampling_steps=args.sampling_steps,
        diffusion_samples=args.diffusion_samples,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
