#!/usr/bin/env python3
"""Build IgGM mask/origin FASTA files from parent sequences and CDR selections."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from boltz_runner import parse_fasta_text, write_fasta
from app.cdr_annotation import annotate_antibody_chain

VALID_CDR_MASKS = frozenset(
    {
        "CDR-H1",
        "CDR-H2",
        "CDR-H3",
        "CDR-L1",
        "CDR-L2",
        "CDR-L3",
        "ALL_CDR",
    }
)


def normalize_iggm_seqs(
    seqs: dict[str, str],
    *,
    binder_chain_id: str = "H",
    antigen_chain_id: str = "A",
) -> dict[str, str]:
    """Map user chain IDs to IgGM convention: H (binder) + A (antigen)."""
    binder_key = binder_chain_id.strip()
    antigen_key = antigen_chain_id.strip()
    if binder_key not in seqs:
        raise ValueError(f"Binder chain {binder_key!r} not found in FASTA")
    if antigen_key not in seqs:
        raise ValueError(f"Antigen chain {antigen_key!r} not found in FASTA")
    if binder_key == antigen_key:
        raise ValueError("Binder and antigen chain IDs must differ")
    return {
        "H": seqs[binder_key].upper().replace(" ", ""),
        "A": seqs[antigen_key].upper().replace(" ", ""),
    }


def expand_cdr_mask(names: list[str]) -> set[str]:
    valid = {"CDR-H1", "CDR-H2", "CDR-H3", "CDR-L1", "CDR-L2", "CDR-L3"}
    expanded: set[str] = set()
    for raw in names:
        name = raw.strip()
        if name in ("ALL_CDR", "ALL-CDR", "all"):
            return set(valid)
        if name not in valid:
            raise ValueError(f"Unknown CDR mask: {raw!r}; choose from {sorted(valid)} or ALL_CDR")
        expanded.add(name)
    if not expanded:
        raise ValueError("At least one CDR region must be selected")
    return expanded


def mask_binder_sequence(sequence: str, cdr_names: list[str]) -> str:
    """Replace selected CDR positions with X (0-based inclusive spans from ANARCI)."""
    targets = expand_cdr_mask(cdr_names)
    ab = annotate_antibody_chain(sequence)
    if ab is None:
        raise ValueError("Binder chain is not recognized as an antibody/nanobody sequence (ANARCI)")

    chars = list(sequence)
    masked_any = False
    for span in ab["cdr_spans"]:
        if span["name"] in targets:
            masked_any = True
            for i in range(span["start"], span["end"] + 1):
                chars[i] = "X"
    if not masked_any:
        available = [s["name"] for s in ab["cdr_spans"]]
        raise ValueError(f"No CDR matched mask {sorted(targets)}; available: {available}")
    return "".join(chars)


def build_maturation_fastas(
    seqs: dict[str, str],
    *,
    binder_chain_id: str = "H",
    antigen_chain_id: str = "A",
    cdr_mask: list[str],
) -> tuple[dict[str, str], dict[str, str]]:
    """Return (origin_seqs, mask_seqs) keyed by H/A."""
    origin = normalize_iggm_seqs(seqs, binder_chain_id=binder_chain_id, antigen_chain_id=antigen_chain_id)
    masked_h = mask_binder_sequence(origin["H"], cdr_mask)
    mask = {"H": masked_h, "A": origin["A"]}
    return origin, mask


def write_maturation_fastas(
    work_dir: Path,
    origin: dict[str, str],
    mask: dict[str, str],
) -> tuple[Path, Path]:
    input_dir = work_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    origin_path = input_dir / "origin.fasta"
    mask_path = input_dir / "mask.fasta"
    write_fasta(origin, origin_path)
    write_fasta(mask, mask_path)
    return origin_path, mask_path
