"""全可变区单点枚举与 CSV I/O。"""

from __future__ import annotations

import csv
from pathlib import Path

from affinity_redesign.common.cdr import annotate_antibody_chain, region_for_index
from affinity_redesign.common.filters import apply_hard_filters
from affinity_redesign.schemas import FilterConfig, MutationRecord

STANDARD_AA = list("ACDEFGHIKLMNPQRSTVWY")

CANDIDATE_FIELDS = [
    "chain",
    "position",
    "wt",
    "mut",
    "region",
    "label",
    "domain",
]


def enumerate_single_point_mutations(
    chain_id: str,
    sequence: str,
    *,
    scan_regions: list[str] | None = None,
) -> list[MutationRecord]:
    """枚举可变区（ANARCI 编号域）内全部单点；跳过 OUT。"""
    ab = annotate_antibody_chain(sequence)
    if ab is None:
        raise ValueError(f"链 {chain_id} 无法被 ANARCI 识别为抗体/纳米抗体可变区")

    allow = set(scan_regions or ["FR", "CDR"])
    records: list[MutationRecord] = []
    qs, qe = ab["query_start"], ab["query_end"]
    for i in range(qs, qe + 1):
        region = region_for_index(ab, i)
        if region == "OUT":
            continue
        is_cdr = region.startswith("CDR")
        is_fr = region.startswith("FR")
        if is_cdr and "CDR" not in allow:
            continue
        if is_fr and "FR" not in allow:
            continue
        wt = sequence[i]
        for mut in STANDARD_AA:
            if mut == wt:
                continue
            records.append(
                MutationRecord(
                    chain=chain_id,
                    position=i + 1,  # 1-based
                    wt=wt,
                    mut=mut,
                    region=region,
                    label=f"{wt}{i + 1}{mut}",
                )
            )
    # attach domain via region already; store domain on first record via side channel not needed
    return records


def write_candidates_csv(records: list[MutationRecord], path: Path, *, domains: dict[str, str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    domains = domains or {}
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CANDIDATE_FIELDS)
        w.writeheader()
        for r in records:
            w.writerow(
                {
                    "chain": r.chain,
                    "position": r.position,
                    "wt": r.wt,
                    "mut": r.mut,
                    "region": r.region,
                    "label": r.label,
                    "domain": domains.get(r.chain, ""),
                }
            )


def read_candidates_csv(path: Path) -> list[MutationRecord]:
    rows: list[MutationRecord] = []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            rows.append(
                MutationRecord(
                    chain=row["chain"],
                    position=int(row["position"]),
                    wt=row["wt"],
                    mut=row["mut"],
                    region=row.get("region") or "",
                    label=row.get("label") or "",
                )
            )
    return rows


def build_candidates_for_campaign(
    sequences: dict[str, str],
    binder_chains: list[str],
    *,
    scan_regions: list[str] | None = None,
    filters: FilterConfig | None = None,
) -> tuple[list[MutationRecord], list[MutationRecord], dict[str, dict]]:
    """返回 (raw, filtered, annotations_by_chain)。"""
    filters = filters or FilterConfig()
    raw: list[MutationRecord] = []
    annotations: dict[str, dict] = {}
    domains: dict[str, str] = {}
    for cid in binder_chains:
        if cid not in sequences:
            raise ValueError(f"缺少 binder 链序列: {cid}")
        ab = annotate_antibody_chain(sequences[cid])
        if ab is None:
            raise ValueError(f"链 {cid} ANARCI 注释失败")
        annotations[cid] = {
            "domain": ab["domain"],
            "query_start": ab["query_start"],
            "query_end": ab["query_end"],
            "cdr_spans": ab["cdr_spans"],
            "length": len(sequences[cid]),
        }
        domains[cid] = ab["domain"]
        raw.extend(
            enumerate_single_point_mutations(
                cid,
                sequences[cid],
                scan_regions=scan_regions,
            )
        )
    filtered = apply_hard_filters(raw, sequences=sequences, config=filters)
    return raw, filtered, annotations
