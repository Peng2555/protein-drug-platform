"""筛选短名单。

序列门：同一位点只留谷氨酰胺，只要框架区，不含 CDR，不带电。
结构门：复折后折叠置信度、原斑 SAP、结合面三者都通过才进入可下载 FASTA。
标题只写突变：单点 H_W47Q，多点用斜线连接。
"""

from __future__ import annotations

from typing import Any

from pathlib import Path

from hydro_redesign.constants import (
    SCREEN_CHAIN_PLDDT_MIN,
    SCREEN_MAX_SITES_PER_PATCH,
    SCREEN_PLDDT_DROP_MAX,
    SCREEN_PLDDT_MIN,
    SCREEN_SAP_DROP_MIN,
    SAP_PATCH_CUTOFF,
)
from hydro_redesign.sequences import apply_mutation

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


def combo_label(sites: list[dict[str, Any]]) -> str:
    ordered = sorted(sites, key=lambda row: (str(row.get("chain")), int(row["position"])))
    return combo_header(
        [
            mutation_header(
                str(row["chain"]),
                str(row["wt"]),
                str(row.get("kabat") or row["position"]),
                str(row["mut"]),
            )
            for row in ordered
        ]
    )


def combo_job_id(label: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in label).strip("_.")
    return (safe or "combo")[:80]


def build_patch_combos(
    sites: list[dict[str, Any]],
    *,
    max_sites: int = SCREEN_MAX_SITES_PER_PATCH,
) -> list[list[dict[str, Any]]]:
    """同一斑内枚举单点和多点。每个斑只取 SAP 最高的若干框架区位点。"""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in sites:
        patch_id = str(row.get("patch_id") or "")
        if patch_id:
            grouped.setdefault(patch_id, []).append(row)

    combos: list[list[dict[str, Any]]] = []
    for members in grouped.values():
        ranked = sorted(members, key=lambda row: -float(row.get("delta_patch") or 0.0))
        chosen = ranked[: max(1, int(max_sites))]
        chosen.sort(key=lambda row: (str(row.get("chain")), int(row["position"])))
        width = len(chosen)
        for mask in range(1, 1 << width):
            group = [chosen[index] for index in range(width) if mask & (1 << index)]
            combos.append(group)
    combos.sort(
        key=lambda group: (
            -sum(float(row.get("delta_patch") or 0.0) for row in group),
            len(group),
            combo_label(group),
        )
    )
    return combos


def apply_combo(seqs: dict[str, str], sites: list[dict[str, Any]]) -> dict[str, str]:
    updated = dict(seqs)
    for row in sorted(sites, key=lambda item: (str(item.get("chain")), int(item["position"]))):
        updated = apply_mutation(
            updated,
            str(row["chain"]),
            int(row["position"]),
            str(row.get("wt") or ""),
            str(row["mut"]),
        )
    return updated


def _sequon_starts(sequence: str) -> set[int]:
    found: set[int] = set()
    for index in range(len(sequence) - 2):
        if sequence[index] == "N" and sequence[index + 1] != "P" and sequence[index + 2] in {"S", "T"}:
            found.add(index)
    return found


def introduces_sequon(before: str, after: str) -> bool:
    return bool(_sequon_starts(after) - _sequon_starts(before))


def residue_plddt(structure_path: Path) -> dict[tuple[str, int], float]:
    scores: dict[tuple[str, int], float] = {}
    for line in Path(structure_path).read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("ATOM") or line[12:16].strip() != "CA":
            continue
        chain = line[21].strip() or "A"
        scores[(chain, int(line[22:26]))] = float(line[60:66])
    return scores


def chain_plddt_mean(scores: dict[tuple[str, int], float]) -> float:
    if not scores:
        return 0.0
    return sum(scores.values()) / len(scores)


def plddt_drop(wildtype: float | None, mutant: float | None) -> float | None:
    """晶体 B 因子不拿来和 Boltz2 的 pLDDT 相减。"""
    if mutant is None:
        return None
    if wildtype is None or not 40.0 <= wildtype <= 100.0:
        return 0.0
    return wildtype - mutant


def patch_sap(residues: list[dict[str, Any]], positions: list[tuple[str, int]]) -> float:
    index = {(str(row["chain"]), int(row["position"])): float(row.get("sap") or 0.0) for row in residues}
    return sum(index.get(position, 0.0) for position in positions)


def patch_member_positions(residues: list[dict[str, Any]], patch_id: str) -> list[tuple[str, int]]:
    return [
        (str(row["chain"]), int(row["position"]))
        for row in residues
        if str(row.get("patch_id") or "") == patch_id
    ]


def novel_patches(
    mutant_patches: list[dict[str, Any]],
    wildtype_positions: set[tuple[str, int]],
) -> list[dict[str, Any]]:
    """与野生型任何疏水斑都没有重合、且 SAP ≥ 0.5 的斑算新斑。"""
    found: list[dict[str, Any]] = []
    for patch in mutant_patches:
        if float(patch.get("score") or 0.0) < SAP_PATCH_CUTOFF:
            continue
        positions: list[tuple[str, int]] = []
        for item in patch.get("residues") or []:
            text = str(item)
            if ":" not in text:
                continue
            chain, rest = text.split(":", 1)
            digits = "".join(ch for ch in rest if ch.isdigit())
            if digits:
                positions.append((chain, int(digits)))
        if positions and all(position not in wildtype_positions for position in positions):
            found.append(patch)
    return found


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
