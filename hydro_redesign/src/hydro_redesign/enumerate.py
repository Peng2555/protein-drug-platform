"""表面疏水位点 × 亲水氨基酸枚举。"""

from __future__ import annotations

from typing import Any

from hydro_redesign.constants import (
    FREEZE_CTERM,
    FREEZE_NTERM,
    HYDROPHILIC_CHARGED,
    HYDROPHILIC_DEFAULT,
    KYTE_DOOLITTLE,
    WETLAB_TOP_N,
)


def _creates_nglyc(sequence: str, index0: int, new_aa: str) -> bool:
    chars = list(sequence)
    chars[index0] = new_aa
    n = len(chars)

    def sequon(seq: list[str], start: int) -> bool:
        if start < 0 or start + 2 >= n:
            return False
        return seq[start] == "N" and seq[start + 1] != "P" and seq[start + 2] in {"S", "T"}

    for start in range(max(0, index0 - 2), min(index0, n - 3) + 1):
        if sequon(chars, start) and not sequon(list(sequence), start):
            return True
    return False


def enumerate_mutations(
    residues: list[dict[str, Any]],
    sequences: dict[str, str],
    regions: dict[tuple[str, int], str],
    *,
    allow_cdr: bool = False,
    allow_charged: bool = False,
    freeze_nterm: int = FREEZE_NTERM,
    freeze_cterm: int = FREEZE_CTERM,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    alphabet = list(HYDROPHILIC_DEFAULT)
    if allow_charged:
        alphabet.extend(HYDROPHILIC_CHARGED)

    seq_len = {cid: len(seq) for cid, seq in sequences.items()}
    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for row in residues:
        chain = row["chain"]
        pos = int(row["position"])
        aa = row["aa"]
        seq = sequences.get(chain, "")
        region = regions.get((chain, pos), "FR")
        is_cdr = str(region).startswith("CDR")
        nlen = seq_len.get(chain, 0)

        reason = None
        if not row.get("hydrophobic") or not row.get("surface") or not row.get("patch_id"):
            continue
        if aa == "C":
            reason = "cysteine"
        elif pos <= freeze_nterm or (nlen and pos > nlen - freeze_cterm):
            reason = "terminus"
        elif is_cdr and not allow_cdr:
            reason = "cdr_frozen"
        if reason:
            skipped.append({**row, "region": region, "skip_reason": reason})
            continue
        if not seq or pos < 1 or pos > len(seq):
            skipped.append({**row, "region": region, "skip_reason": "seq_mismatch"})
            continue
        if seq[pos - 1] != aa:
            # 结构编号与 FASTA 不完全对齐时仍尝试，但记下
            pass

        for mut in alphabet:
            if mut == aa:
                continue
            hydro_delta = round(KYTE_DOOLITTLE.get(aa, 0.0) - KYTE_DOOLITTLE.get(mut, 0.0), 3)
            if hydro_delta <= 0:
                continue
            if mut == "C":
                continue
            if seq and _creates_nglyc(seq, pos - 1, mut):
                skipped.append(
                    {
                        "chain": chain,
                        "position": pos,
                        "wt": aa,
                        "mut": mut,
                        "region": region,
                        "skip_reason": "nglycosylation",
                    }
                )
                continue
            delta_patch = round(float(row.get("hydro_sasa") or 0.0), 3)
            candidates.append(
                {
                    "chain": chain,
                    "position": pos,
                    "wt": aa,
                    "mut": mut,
                    "label": f"{chain}_{aa}{pos}{mut}",
                    "region": region,
                    "rsa": row.get("rsa"),
                    "sasa": row.get("sasa"),
                    "hydro_sasa": row.get("hydro_sasa"),
                    "patch_id": row.get("patch_id"),
                    "hydro_delta": hydro_delta,
                    "delta_patch": delta_patch,
                    "cdr_risk": bool(is_cdr),
                }
            )

    candidates.sort(
        key=lambda r: (-float(r["delta_patch"]), -float(r["hydro_delta"]), r["chain"], r["position"], r["mut"])
    )
    for i, row in enumerate(candidates, start=1):
        row["rank"] = i
        row["wetlab"] = i <= WETLAB_TOP_N and not row["cdr_risk"] and str(row["region"]).startswith("FR")
    return candidates, skipped
