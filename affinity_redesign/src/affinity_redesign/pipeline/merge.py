"""PLM 与结构轨合并为 tier A/B/C。"""

from __future__ import annotations

import csv
from pathlib import Path

from affinity_redesign.schemas import MergeConfig, MutationRecord


def load_plm_top_csv(path: Path) -> list[MutationRecord]:
    rows: list[MutationRecord] = []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            mean = r.get("mean_dll") or ""
            rows.append(
                MutationRecord(
                    chain=r["chain"],
                    position=int(r["position"]),
                    wt=r["wt"],
                    mut=r["mut"],
                    region=r.get("region") or "",
                    plm_score=float(mean) if mean != "" else None,
                    label=r.get("label") or "",
                )
            )
    return rows


def load_structure_top_csv(path: Path) -> list[MutationRecord]:
    rows: list[MutationRecord] = []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            dll = r.get("dll") or ""
            rows.append(
                MutationRecord(
                    chain=r["chain"],
                    position=int(r["position"]),
                    wt=r["wt"],
                    mut=r["mut"],
                    region=r.get("region") or "",
                    structure_score=float(dll) if dll != "" else None,
                    label=r.get("label") or "",
                )
            )
    return rows


def _apply_quota(
    rows: list[MutationRecord],
    quota: int | str | None,
    *,
    score_attr: str,
) -> list[MutationRecord]:
    ordered = sorted(
        rows,
        key=lambda r: (-(getattr(r, score_attr) if getattr(r, score_attr) is not None else float("-inf")), r.position, r.mut),
    )
    if quota is None or quota == "all":
        return ordered
    return ordered[: int(quota)]


def merge_tracks(
    plm_records: list[MutationRecord],
    structure_records: list[MutationRecord],
    config: MergeConfig,
    out_dir: Path,
) -> dict[str, list[MutationRecord]]:
    out_dir.mkdir(parents=True, exist_ok=True)

    def key(r: MutationRecord) -> tuple[str, int, str]:
        return (r.chain, r.position, r.mut)

    plm_map = {key(r): r for r in plm_records}
    struct_map = {key(r): r for r in structure_records}

    tier_a: list[MutationRecord] = []
    tier_b: list[MutationRecord] = []
    tier_c: list[MutationRecord] = []

    for k, r in struct_map.items():
        if k in plm_map:
            tier_a.append(
                r.model_copy(
                    update={
                        "tier": "A",
                        "plm_score": plm_map[k].plm_score,
                        "region": r.region or plm_map[k].region,
                    }
                )
            )
        else:
            tier_b.append(r.model_copy(update={"tier": "B"}))

    for k, r in plm_map.items():
        if k not in struct_map:
            tier_c.append(r.model_copy(update={"tier": "C"}))

    quotas = config.tier_quotas
    tiers = {
        "A": _apply_quota(tier_a, quotas.get("A", "all"), score_attr="structure_score"),
        "B": _apply_quota(tier_b, quotas.get("B", "all"), score_attr="structure_score"),
        "C": _apply_quota(tier_c, quotas.get("C", "all"), score_attr="plm_score"),
    }

    fieldnames = [
        "chain",
        "position",
        "wt",
        "mut",
        "region",
        "tier",
        "plm_score",
        "structure_score",
        "label",
    ]
    for tier_name, rows in tiers.items():
        path = out_dir / f"tier_{tier_name}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for row in rows:
                w.writerow(
                    {
                        "chain": row.chain,
                        "position": row.position,
                        "wt": row.wt,
                        "mut": row.mut,
                        "region": row.region,
                        "tier": row.tier,
                        "plm_score": "" if row.plm_score is None else row.plm_score,
                        "structure_score": "" if row.structure_score is None else row.structure_score,
                        "label": row.label,
                    }
                )

    return tiers
