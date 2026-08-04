"""Kabat CDR annotation via ANARCI (scheme='kabat')."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from boltz_runner import parse_fasta_text

# Kabat CDR ranges (inclusive)
KABAT_CDR_HEAVY = {
    "CDR-H1": (31, 35),
    "CDR-H2": (50, 65),
    "CDR-H3": (95, 102),
}
KABAT_CDR_LIGHT = {
    "CDR-L1": (24, 34),
    "CDR-L2": (50, 56),
    "CDR-L3": (89, 97),
}

HMMER_PATH = os.environ.get(
    "HMMER_PATH",
    "/home/pengpai/data/envs/IgGM/bin",
)


def _cdr_defs(domain: str) -> dict[str, tuple[int, int]]:
    return KABAT_CDR_LIGHT if domain == "L" else KABAT_CDR_HEAVY


def _format_kabat(pos: int, ins: str) -> str:
    ins = (ins or " ").strip()
    return f"{pos}{ins}" if ins else str(pos)


def annotate_antibody_chain(sequence: str) -> dict | None:
    """Return CDR spans on sequential indices, or None if not an antibody domain."""
    try:
        from anarci import anarci
    except ImportError:
        return None

    if len(sequence) < 80 or len(sequence) > 350:
        return None

    hmmer = HMMER_PATH if Path(HMMER_PATH, "hmmscan").exists() else ""
    try:
        numbering_result, detail, _hit = anarci(
            [("query", sequence)],
            scheme="kabat",
            hmmerpath=hmmer,
        )
    except Exception:
        return None

    if not numbering_result or not numbering_result[0]:
        return None

    block = numbering_result[0][0]
    numbering = block[0]

    domain = "H"
    if detail and detail[0] and isinstance(detail[0], list) and detail[0][0]:
        chain_type = detail[0][0].get("chain_type", "H")
        domain = "L" if str(chain_type).upper().startswith("L") else "H"

    cdr_defs = _cdr_defs(domain)
    seq_index = 0
    index_to_cdr: dict[int, str] = {}

    for (pos, ins), aa in numbering:
        if aa == "-":
            continue
        if isinstance(pos, int):
            for name, (lo, hi) in cdr_defs.items():
                if lo <= pos <= hi:
                    index_to_cdr[seq_index] = name
                    break
        seq_index += 1

    if not index_to_cdr:
        return None

    # Build merged CDR spans
    spans: list[dict] = []
    for name, (lo, hi) in cdr_defs.items():
        indices = [
            i
            for i in range(len(sequence))
            if index_to_cdr.get(i) == name
        ]
        if not indices:
            continue
        start, end = indices[0], indices[-1]
        kabat_positions = []
        seq_i = 0
        for (pos, ins), aa in numbering:
            if aa == "-":
                continue
            if isinstance(pos, int) and lo <= pos <= hi and start <= seq_i <= end:
                kabat_positions.append(_format_kabat(pos, ins))
            seq_i += 1
        spans.append(
            {
                "name": name,
                "start": start,
                "end": end,
                "kabat_range": f"{kabat_positions[0]}–{kabat_positions[-1]}" if kabat_positions else "",
                "sequence": sequence[start : end + 1],
            }
        )

    return {
        "domain": domain,
        "scheme": "kabat",
        "numbered_length": seq_index,
        "cdr_spans": spans,
        "kabat_labels": _kabat_labels_from_numbering(sequence, numbering),
    }


def _kabat_labels_from_numbering(sequence: str, numbering: list) -> list[str]:
    """Per-residue Kabat label (sequential fallback when unnumbered)."""
    labels = [str(i + 1) for i in range(len(sequence))]
    seq_index = 0
    for (pos, ins), aa in numbering:
        if aa == "-":
            continue
        if seq_index < len(labels) and isinstance(pos, int):
            labels[seq_index] = _format_kabat(pos, ins)
        seq_index += 1
    return labels


def build_residue_list(sequence: str, ab: dict | None) -> list[dict]:
    kabat = ab.get("kabat_labels") if ab else None
    residues = []
    for i, aa in enumerate(sequence):
        seq_pos = i + 1
        kabat_label = kabat[i] if kabat and i < len(kabat) else str(seq_pos)
        residues.append({
            "index": seq_pos,
            "aa": aa,
            "kabat": kabat_label,
        })
    return residues


def build_chain_display(sequence: str, cdr_spans: list[dict] | None) -> list[dict]:
    """Split sequence into colored segments for UI."""
    if not cdr_spans:
        return [{"type": "fw", "text": sequence}]

    cdr_by_start = {s["start"]: s for s in sorted(cdr_spans, key=lambda x: x["start"])}
    segments: list[dict] = []
    i = 0
    n = len(sequence)
    while i < n:
        if i in cdr_by_start:
            sp = cdr_by_start[i]
            end = sp["end"] + 1
            segments.append({"type": "cdr", "name": sp["name"], "text": sequence[i:end]})
            i = end
        else:
            j = i + 1
            while j < n and j not in cdr_by_start:
                j += 1
            segments.append({"type": "fw", "text": sequence[i:j]})
            i = j
    return segments


def annotate_fasta(fasta_text: str) -> list[dict]:
    seqs = parse_fasta_text(fasta_text)
    chains: list[dict] = []
    for chain_id, sequence in seqs.items():
        ab = annotate_antibody_chain(sequence)
        entry = {
            "chain_id": chain_id,
            "length": len(sequence),
            "sequence": sequence,
            "is_antibody": ab is not None,
            "domain": ab["domain"] if ab else None,
            "scheme": ab["scheme"] if ab else None,
            "cdr_spans": ab["cdr_spans"] if ab else [],
            "segments": build_chain_display(sequence, ab["cdr_spans"] if ab else None),
            "residues": build_residue_list(sequence, ab),
        }
        chains.append(entry)
    return chains
