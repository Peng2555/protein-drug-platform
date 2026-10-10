"""给已完成任务补 Kabat 编号和突变序列，不要求重跑。"""

from __future__ import annotations

import re
from pathlib import Path

from app.common.cdr_annotation import annotate_fasta

_PATCH_LABEL = re.compile(r"^([^:]+):([A-Z])(\d+)$")


def load_job_fasta(job) -> str:
    """优先用工作目录里的序列文件，链 ID 与结构一致。"""
    work = getattr(job, "work_dir", None)
    if work:
        fasta = Path(work) / "input" / "sequences.fasta"
        if fasta.is_file():
            text = fasta.read_text(encoding="utf-8")
            if text.strip():
                return text
    return str(getattr(job, "fasta_text", None) or "")


def annotate_job_chains(job) -> list[dict]:
    text = load_job_fasta(job)
    if not text.strip():
        return []
    return annotate_fasta(text)


def _kabat_index(chains: list[dict]) -> tuple[dict[tuple[str, int], str], dict[str, str]]:
    labels: dict[tuple[str, int], str] = {}
    sequences: dict[str, str] = {}
    for chain in chains:
        chain_id = str(chain.get("chain_id") or "")
        sequence = str(chain.get("sequence") or "")
        if chain_id:
            sequences[chain_id] = sequence
        for residue in chain.get("residues") or []:
            try:
                index = int(residue.get("index"))
            except (TypeError, ValueError):
                continue
            kabat = str(residue.get("kabat") or "").strip()
            if chain_id and kabat:
                labels[(chain_id, index)] = kabat
    return labels, sequences


def _position(row: dict) -> int | None:
    try:
        return int(float(row.get("position")))
    except (TypeError, ValueError):
        return None


def apply_kabat_rows(rows: list[dict], chains: list[dict], *, with_sequence: bool = False) -> None:
    labels, sequences = _kabat_index(chains)
    for row in rows:
        chain = str(row.get("chain") or "")
        pos = _position(row)
        if pos is None:
            continue
        kabat = str(row.get("kabat") or "").strip() or labels.get((chain, pos), "")
        if kabat:
            row["kabat"] = kabat
        if not with_sequence:
            continue
        mut = str(row.get("mut") or "")
        wt = str(row.get("wt") or "")
        seq = sequences.get(chain, "")
        if mut and seq and 1 <= pos <= len(seq) and not str(row.get("sequence") or "").strip():
            if not wt or seq[pos - 1] == wt:
                row["sequence"] = seq[: pos - 1] + mut + seq[pos:]
        if kabat and wt and mut and chain:
            row["label"] = f"{chain}_{wt}{kabat}{mut}"


def relabel_patch_rows(patches: list[dict], residues: list[dict]) -> None:
    """只把「顺序位」标签改成 Kabat。氨基酸对不上时说明已经是 Kabat，不再换算。"""
    by_pos: dict[tuple[str, int], tuple[str, str]] = {}
    for row in residues:
        pos = _position(row)
        kabat = str(row.get("kabat") or "").strip()
        aa = str(row.get("aa") or "").strip()
        if pos is None or not kabat or not aa:
            continue
        by_pos[(str(row.get("chain") or ""), pos)] = (aa, kabat)
    for patch in patches:
        raw = patch.get("residues")
        if isinstance(raw, list):
            parts = [str(item) for item in raw]
        else:
            text = str(raw or "")
            parts = [item.strip() for item in text.split(";") if item.strip()] if text else []
        labels = []
        for item in parts:
            match = _PATCH_LABEL.match(item)
            if not match:
                labels.append(item)
                continue
            chain, aa, pos_s = match.group(1), match.group(2), match.group(3)
            hit = by_pos.get((chain, int(pos_s)))
            if hit and hit[0] == aa:
                labels.append(f"{chain}:{aa}{hit[1]}")
            else:
                labels.append(item)
        patch["residues"] = labels
