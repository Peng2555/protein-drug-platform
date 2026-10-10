"""硬过滤：半胱氨酸、N-糖基化等。"""

from __future__ import annotations

from affinity_redesign.schemas import FilterConfig, MutationRecord


def _creates_nglycosylation(sequence: str, index: int, new_aa: str) -> bool:
    chars = list(sequence)
    chars[index] = new_aa
    n = len(chars)

    def is_sequon(start: int) -> bool:
        if start < 0 or start + 2 >= n:
            return False
        return chars[start] == "N" and chars[start + 1] != "P" and chars[start + 2] in {"S", "T"}

    for start in range(max(0, index - 2), min(index, n - 3) + 1):
        if is_sequon(start):
            wt = sequence[start : start + 3]
            if not (wt[0] == "N" and wt[1] != "P" and wt[2] in {"S", "T"}):
                return True
    return False


def apply_hard_filters(
    records: list[MutationRecord],
    *,
    sequences: dict[str, str],
    config: FilterConfig,
) -> list[MutationRecord]:
    kept: list[MutationRecord] = []
    for rec in records:
        seq = sequences.get(rec.chain, "")
        idx = rec.position - 1
        if not seq or idx < 0 or idx >= len(seq):
            continue
        if seq[idx] != rec.wt:
            continue
        if config.freeze_cysteine and (rec.wt == "C" or rec.mut == "C"):
            continue
        nterm = int(getattr(config, "freeze_nterm", 0) or 0)
        if nterm > 0 and rec.position <= nterm:
            continue
        # C 端：序列以 TVSS 结尾则只冻这 4 位；否则冻末尾 freeze_cterm 位
        cterm = int(getattr(config, "freeze_cterm", 0) or 0)
        if seq.upper().endswith("TVSS"):
            if rec.position > len(seq) - 4:
                continue
        elif cterm > 0 and rec.position > len(seq) - cterm:
            continue
        if getattr(config, "freeze_fr4", False) and rec.region == "FR4":
            continue
        if config.block_new_nglyc and _creates_nglycosylation(seq, idx, rec.mut):
            continue
        kept.append(rec)
    return kept
