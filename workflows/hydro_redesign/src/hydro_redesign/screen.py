"""筛选短名单。

序列门：同一位点只留谷氨酰胺，只要框架区，不含 CDR，不带电。
结构门：复折后折叠置信度、原斑 SAP、结合面三者都通过才进入可下载 FASTA。
标题只写突变：单点 H_W47Q，多点用斜线连接。
"""

from __future__ import annotations

from typing import Any

from hydro_redesign.constants import (
    SCREEN_CHAIN_PLDDT_MIN,
    SCREEN_PLDDT_DROP_MAX,
    SCREEN_PLDDT_MIN,
    SCREEN_SAP_DROP_MIN,
)

SCREENED_FASTA = "screened_sequences.fasta"


def mutation_header(chain: str, wt: str, kabat: str, mut: str) -> str:
    return f"{chain}_{wt}{kabat}{mut}"


def combo_header(labels: list[str]) -> str:
    return "/".join(label for label in labels if label)


def select_screened_sites(mutations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """复折之前的序列筛选：每个框架区位点只留 Q。"""
    chosen: dict[tuple[str, int], dict[str, Any]] = {}
    for row in mutations:
        if str(row.get("mut") or "") != "Q":
            continue
        if row.get("cdr_risk"):
            continue
        if not str(row.get("region") or "").startswith("FR"):
            continue
        if float(row.get("hydro_delta") or 0.0) <= 0:
            continue
        if not row.get("patch_id"):
            continue
        try:
            pos = int(row["position"])
        except (TypeError, ValueError):
            continue
        chain = str(row.get("chain") or "")
        if not chain:
            continue
        chosen[(chain, pos)] = row
    return sorted(
        chosen.values(),
        key=lambda row: (-float(row.get("delta_patch") or 0.0), str(row.get("chain")), int(row["position"])),
    )


def fold_gate(sites: list[dict[str, Any]], chain_mean: float) -> bool:
    if float(chain_mean) < SCREEN_CHAIN_PLDDT_MIN:
        return False
    if not sites:
        return False
    for site in sites:
        value = site.get("plddt")
        drop = site.get("drop")
        if value is None or drop is None:
            return False
        if float(value) < SCREEN_PLDDT_MIN or float(drop) > SCREEN_PLDDT_DROP_MAX:
            return False
    return True


def sap_gate(wildtype_sum: float, mutant_sum: float, new_patches: list[Any]) -> bool:
    if new_patches:
        return False
    return float(wildtype_sum) - float(mutant_sum) >= SCREEN_SAP_DROP_MIN


def accept_verified(row: dict[str, Any]) -> bool:
    """折叠、疏水斑、结合面都通过。"""
    return bool(row.get("fold_ok") and row.get("sap_ok") and row.get("binding_ok"))


def render_screened_fasta(entries: list[tuple[str, str]]) -> str:
    """entries 为 (标题, 序列)。标题里只放突变情况。"""
    lines: list[str] = []
    for header, sequence in entries:
        text = "".join(str(sequence).split())
        if not header or not text:
            continue
        lines.append(f">{header}")
        lines.append(text)
    return ("\n".join(lines) + "\n") if lines else ""
