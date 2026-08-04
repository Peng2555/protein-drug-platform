#!/usr/bin/env python3
"""Boltz2 structure prediction from FASTA — give sequences, get structures.

Examples:
  # VHH + antigen (multi-chain FASTA)
  python fold_fasta.py -i complex.fasta -o outputs/

  # Fab + antigen
  python fold_fasta.py -i fab_ag.fasta --name my_job

  # inline sequences (no file needed)
  python fold_fasta.py --seq H:EVQLVES... --seq A:KVFGRCEL...

  # batch directory
  python fold_fasta.py --batch-dir inputs/ -o outputs/

  # paste FASTA from stdin
  cat complex.fasta | python fold_fasta.py --stdin -o outputs/
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from boltz_runner import (
    DEFAULT_OUT_ROOT,
    fold_fasta,
    fold_sequences,
    job_id_from_seqs,
    parse_fasta_text,
    read_fasta,
)


def parse_seq_arg(s: str) -> tuple[str, str]:
    if ":" not in s:
        raise argparse.ArgumentTypeError(f"Expected CHAIN:SEQUENCE, got {s!r}")
    chain, seq = s.split(":", 1)
    chain = chain.strip()
    seq = seq.strip().upper()
    if not chain:
        raise argparse.ArgumentTypeError("Chain ID cannot be empty")
    return chain, seq


def main() -> None:
    p = argparse.ArgumentParser(description="Boltz2: FASTA/sequences -> structure")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("-i", "--input", type=Path, help="Input FASTA file")
    src.add_argument("--batch-dir", type=Path, help="Directory of *.fasta files")
    src.add_argument("--manifest", type=Path, help="CSV: case_id,fasta_path")
    src.add_argument("--stdin", action="store_true", help="Read FASTA from stdin")
    src.add_argument(
        "--seq",
        action="append",
        type=parse_seq_arg,
        metavar="CHAIN:SEQ",
        help="Inline chain sequence, repeatable (e.g. H:EVQL... A:KVF...)",
    )

    p.add_argument("-o", "--output", type=Path, default=DEFAULT_OUT_ROOT, help="Output root dir")
    p.add_argument("--name", type=str, default=None, help="Job name / ID prefix")
    p.add_argument("--no-msa", action="store_true", help="Disable MSA server (single-sequence mode)")
    p.add_argument("--recycling-steps", type=int, default=3)
    p.add_argument("--sampling-steps", type=int, default=200)
    p.add_argument("--diffusion-samples", type=int, default=1)
    p.add_argument("--force", action="store_true", help="Re-run even if output exists")
    args = p.parse_args()

    kwargs = dict(
        use_msa_server=not args.no_msa,
        recycling_steps=args.recycling_steps,
        sampling_steps=args.sampling_steps,
        diffusion_samples=args.diffusion_samples,
        skip_if_done=not args.force,
    )

    results: list[dict] = []

    if args.input:
        jid = args.name or args.input.stem
        r = fold_fasta(args.input, out_root=args.output, job_id=jid, **kwargs)
        results.append(r.__dict__)
        _print_result(r)

    elif args.stdin:
        text = sys.stdin.read()
        seqs = parse_fasta_text(text)
        jid = args.name or job_id_from_seqs(seqs, prefix="stdin")
        r = fold_sequences(seqs, out_root=args.output, job_id=jid, **kwargs)
        results.append(r.__dict__)
        _print_result(r)

    elif args.seq:
        seqs = dict(args.seq)
        jid = args.name or job_id_from_seqs(seqs, prefix="inline")
        r = fold_sequences(seqs, out_root=args.output, job_id=jid, **kwargs)
        results.append(r.__dict__)
        _print_result(r)

    elif args.batch_dir:
        fastas = sorted(args.batch_dir.glob("*.fasta"))
        if not fastas:
            sys.exit(f"No *.fasta in {args.batch_dir}")
        for fasta in fastas:
            print(f"\n=== {fasta.name} ===")
            r = fold_fasta(fasta, out_root=args.output, job_id=fasta.stem, **kwargs)
            results.append(r.__dict__)
            _print_result(r)

    elif args.manifest:
        with open(args.manifest, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                case_id = row["case_id"].strip()
                fasta = Path(row["fasta_path"].strip())
                print(f"\n=== {case_id} ===")
                r = fold_fasta(fasta, out_root=args.output, job_id=case_id, **kwargs)
                results.append(r.__dict__)
                _print_result(r)

    summary_path = args.output / "summary.json"
    args.output.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSummary: {summary_path}")

    if any(r.get("status") == "failed" for r in results):
        sys.exit(1)


def _print_result(r) -> None:
    if r.status == "ok":
        print(
            f"  OK  job={r.job_id}  ipTM={r.iptm:.3f}  pTM={r.ptm:.3f}  "
            f"pLDDT={r.complex_plddt:.3f}  {r.seconds:.0f}s"
        )
        print(f"      {r.pred_cif}")
    else:
        print(f"  FAIL job={r.job_id}  {r.error[:200] if r.error else 'unknown'}")


if __name__ == "__main__":
    main()
