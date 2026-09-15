"""Kabat 编号、CDR 长度、tetrad。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from boltzfold_shared.io.fasta import parse_fasta
from boltzfold_shared.runtime.settings import settings
from tnp_profile.constants import (
    KABAT_CDR_H1,
    KABAT_CDR_H2,
    KABAT_CDR_H3,
    KABAT_H3_ANCHORS,
    KABAT_H3_LOOP,
    KABAT_TETRAD,
    KABAT_VICINITY,
)


def _region_for_kabat(pos: int) -> str:
    if KABAT_CDR_H1[0] <= pos <= KABAT_CDR_H1[1]:
        return "CDR-H1"
    if KABAT_CDR_H2[0] <= pos <= KABAT_CDR_H2[1]:
        return "CDR-H2"
    if KABAT_CDR_H3[0] <= pos <= KABAT_CDR_H3[1]:
        return "CDR-H3"
    if pos < KABAT_CDR_H1[0]:
        return "FR1"
    if KABAT_CDR_H1[1] < pos < KABAT_CDR_H2[0]:
        return "FR2"
    if KABAT_CDR_H2[1] < pos < KABAT_CDR_H3[0]:
        return "FR3"
    return "FR4"


def _in_range(pos: int, lo_hi: tuple[int, int]) -> bool:
    return lo_hi[0] <= pos <= lo_hi[1]


def _vicinity_loop(pos: int) -> str | None:
    for name, span in KABAT_VICINITY.items():
        if _in_range(pos, span):
            return name
    return None


def annotate_kabat(sequence: str) -> dict[str, Any]:
    """ANARCI Kabat。seq_index 为 0-based；pdb_pos = seq_index + 1。"""
    sequence = sequence.upper().replace(" ", "")
    try:
        from anarci import anarci
    except ImportError as exc:
        raise RuntimeError("需要 ANARCI 才能做 Kabat 编号") from exc

    hmmer = ""
    candidate = Path(settings.hmmer_path)
    if (candidate / "hmmscan").exists():
        hmmer = str(candidate)

    kwargs: dict[str, Any] = {"scheme": "kabat"}
    if hmmer:
        kwargs["hmmerpath"] = hmmer
    numbering_result, detail, _hit = anarci([("query", sequence)], **kwargs)
    if not numbering_result or not numbering_result[0]:
        raise ValueError("ANARCI 未能将序列识别为抗体可变区")
    block = numbering_result[0][0]
    numbering = block[0]
    query_start, query_end = int(block[1]), int(block[2])
    domain = "H"
    if detail and detail[0] and isinstance(detail[0], list) and detail[0][0]:
        ct = str(detail[0][0].get("chain_type") or "H").upper()
        if ct.startswith(("K", "L")):
            domain = "L"

    residues: list[dict[str, Any]] = []
    seq_i = query_start
    for (pos, ins), aa in numbering:
        if aa == "-":
            continue
        if not isinstance(pos, int) or seq_i > query_end:
            seq_i += 1
            continue
        ins_s = str(ins or "").strip()
        kabat_label = f"{pos}{ins_s}"
        residues.append(
            {
                "seq_index": seq_i,
                "pdb_pos": seq_i + 1,
                "kabat": pos,
                "insertion": ins_s,
                "kabat_label": kabat_label,
                "aa": aa,
                "region": _region_for_kabat(pos),
                "vicinity_loop": _vicinity_loop(pos),
                "is_h3_loop": _in_range(pos, KABAT_H3_LOOP),
                "is_h3_anchor": pos in KABAT_H3_ANCHORS,
            }
        )
        seq_i += 1

    by_index = {r["seq_index"]: r for r in residues}
    for i, aa in enumerate(sequence):
        if i not in by_index:
            residues.append(
                {
                    "seq_index": i,
                    "pdb_pos": i + 1,
                    "kabat": None,
                    "insertion": "",
                    "kabat_label": "",
                    "aa": aa,
                    "region": "OUT",
                    "vicinity_loop": None,
                    "is_h3_loop": False,
                    "is_h3_anchor": False,
                }
            )
    residues.sort(key=lambda r: r["seq_index"])

    def _span_seq(name: str, lo: int, hi: int) -> str:
        return "".join(r["aa"] for r in residues if r["kabat"] is not None and lo <= r["kabat"] <= hi)

    cdr_h1 = _span_seq("H1", *KABAT_CDR_H1)
    cdr_h2 = _span_seq("H2", *KABAT_CDR_H2)
    cdr_h3 = _span_seq("H3", *KABAT_CDR_H3)
    tetrad = []
    for pos in KABAT_TETRAD:
        hit = next((r for r in residues if r["kabat"] == pos and not r["insertion"]), None)
        if hit is None:
            hit = next((r for r in residues if r["kabat"] == pos), None)
        tetrad.append({"kabat": pos, "aa": hit["aa"] if hit else "-"})
    motif = "".join(t["aa"] for t in tetrad)
    return {
        "sequence": sequence,
        "domain": domain,
        "scheme": "kabat",
        "query_start": query_start,
        "query_end": query_end,
        "residues": residues,
        "cdr_h1": cdr_h1,
        "cdr_h2": cdr_h2,
        "cdr_h3": cdr_h3,
        "L": len(cdr_h1) + len(cdr_h2) + len(cdr_h3),
        "L3": len(cdr_h3),
        "tetrad": tetrad,
        "tetrad_motif": motif,
    }
