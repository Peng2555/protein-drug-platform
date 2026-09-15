"""由 WT FASTA + 突变表生成突变体蛋白序列。"""

from __future__ import annotations

from typing import Any

from boltzfold_shared.io.fasta import parse_fasta

ALL_MUTANT_FASTA = "all_mutant_sequences.fasta"
TOP20_MUTANT_FASTA = "top20_mutant_sequences.fasta"


def apply_mutation(seqs: dict[str, str], chain: str, pos1: int, wt: str, mut: str) -> dict[str, str]:
    if chain not in seqs:
        raise KeyError(f"序列中没有链 {chain}")
    s = seqs[chain]
    i = pos1 - 1
    if i < 0 or i >= len(s):
        raise ValueError(f"{chain}{pos1} 超出序列长度 {len(s)}")
    if wt and s[i] != wt:
        raise ValueError(f"{chain}{pos1}: FASTA 为 {s[i]}，候选表为 {wt}")
    out = dict(seqs)
    out[chain] = s[:i] + mut + s[i + 1 :]
    return out


def _wrap_seq(seq: str, width: int = 60) -> str:
    seq = seq.replace(" ", "").strip()
    if not seq:
        return ""
    return "\n".join(seq[i : i + width] for i in range(0, len(seq), width))


def build_mutant_sequences_fasta(
    seqs: dict[str, str],
    rows: list[dict[str, Any]],
    *,
    include_wt: bool = True,
) -> str:
    """导出抗体链突变体 FASTA；多链时每个突变写全部分子链。"""
    chain_order = [c for c in ("H", "L") if c in seqs] or list(seqs.keys())
    lines: list[str] = []
    if include_wt:
        for cid in chain_order:
            lines.append(f">WT chain={cid} role=wild-type")
            lines.append(_wrap_seq(seqs[cid]))
    for row in rows:
        chain = str(row.get("chain") or "").strip()
        wt = str(row.get("wt") or "").strip()
        mut = str(row.get("mut") or "").strip()
        label = str(row.get("label") or "").strip() or f"{chain}_{wt}{row.get('position')}{mut}"
        try:
            pos = int(row.get("position"))
        except (TypeError, ValueError):
            continue
        if not chain or not mut:
            continue
        try:
            mut_seqs = apply_mutation(seqs, chain, pos, wt, mut)
        except (KeyError, ValueError):
            continue
        rank = row.get("rank", "")
        mut_tag = f"{chain}:{wt}{pos}{mut}"
        for cid in chain_order:
            if cid not in mut_seqs:
                continue
            role = "mutated" if cid == chain else "unchanged"
            header = f">{label} rank={rank} chain={cid} mutation={mut_tag} role={role}"
            lines.append(header)
            lines.append(_wrap_seq(mut_seqs[cid]))
    return "\n".join(lines) + ("\n" if lines else "")


def select_top20_rows(mutations: list[dict[str, Any]], wetlab: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """推荐前 20：优先湿实验短名单，否则按 rank 取前 20。"""
    if wetlab:
        return list(wetlab)[:20]
    return list(mutations)[:20]
