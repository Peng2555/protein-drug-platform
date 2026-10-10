"""可设计位点掩码：每个残基能否进入后续 Cys 配对搜索。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from boltzfold_shared.io.fasta import parse_fasta
from tm_disulfide.constants import (
    EXCLUDE_CDR,
    EXCLUDE_GLYCINE,
    EXCLUDE_PROLINE,
    MAXIMUM_CA_RMSF,
    MINIMUM_CONFIDENCE,
    THREE_TO_ONE,
)
from tm_disulfide.ensemble import run_ensemble_alignment
from tm_disulfide.numbering import number_kabat_chain
from tm_disulfide.qc import _pick_atom


def normalize_plddt(value: float | None) -> float | None:
    """CIF B 因子或 0–1 的 pLDDT 都换成 0–100。"""
    if value is None:
        return None
    score = float(value)
    if 0.0 <= score <= 1.0:
        return score * 100.0
    return score


def exclusion_reasons(
    *,
    amino_acid: str,
    kabat_number: str,
    is_cdr: bool,
    present_in_all_models: bool,
    has_ca_in_all_models: bool,
    has_cb_in_all_models: bool,
    minimum_confidence: float | None,
    ca_rmsf: float | None,
) -> list[str]:
    """硬排除原因；Gly 只走 glycine，不因没有 CB 再记 missing_cb。"""
    reasons: list[str] = []
    if EXCLUDE_CDR and is_cdr:
        reasons.append("kabat_cdr")
    if amino_acid == "C":
        reasons.append("native_cysteine")
    if EXCLUDE_GLYCINE and amino_acid == "G":
        reasons.append("glycine")
    if EXCLUDE_PROLINE and amino_acid == "P":
        reasons.append("proline")
    if not kabat_number:
        reasons.append("no_kabat_mapping")
    if not present_in_all_models:
        reasons.append("missing_residue")
    if not has_ca_in_all_models:
        reasons.append("missing_ca")
    if amino_acid != "G" and not has_cb_in_all_models:
        reasons.append("missing_cb")
    if minimum_confidence is None:
        reasons.append("missing_confidence")
    elif minimum_confidence < MINIMUM_CONFIDENCE:
        reasons.append("low_confidence")
    if ca_rmsf is not None and ca_rmsf > MAXIMUM_CA_RMSF:
        reasons.append("high_rmsf")
    return reasons


def _extract_atom_flags(structure) -> dict[tuple[str, int], dict[str, Any]]:
    table: dict[tuple[str, int], dict[str, Any]] = {}
    for chain in structure[0]:
        seq_index = 0
        for res in chain:
            aa = THREE_TO_ONE.get(res.name)
            if aa is None:
                continue
            seq_index += 1
            ca = _pick_atom(res, "CA")
            cb = _pick_atom(res, "CB")
            plddt = None
            if ca is not None:
                try:
                    plddt = normalize_plddt(float(ca.b_iso))
                except (TypeError, ValueError):
                    plddt = None
            table[(chain.name, seq_index)] = {
                "amino_acid": aa,
                "has_ca": ca is not None,
                "has_cb": cb is not None,
                "plddt": plddt,
            }
    return table


def run_site_mask(
    fasta_text: str,
    structure_paths: list[Path] | Path,
    *,
    ensemble: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """在 ensemble 叠合之后，给出每个残基能否突变为 Cys。"""
    import gemmi

    fasta = parse_fasta(fasta_text)
    if not fasta:
        raise ValueError("FASTA 无效")
    report = ensemble or run_ensemble_alignment(fasta_text, structure_paths)
    paths = [Path(p) for p in report.get("structure_paths") or []]
    if not paths:
        if isinstance(structure_paths, Path):
            raise ValueError("没有结构路径")
        paths = [Path(p) for p in structure_paths]
    atom_tables = [_extract_atom_flags(gemmi.read_structure(str(path))) for path in paths]
    rmsf_by_key = {
        (row["structure_chain"], row["sequence_index"]): row for row in report["residues"]
    }
    numbering_by_chain = {chain: number_kabat_chain(seq) for chain, seq in fasta.items()}

    rows: list[dict[str, Any]] = []
    for chain, seq in fasta.items():
        numbered = numbering_by_chain[chain]["residues"]
        for item in numbered:
            key = (chain, item["sequence_index"])
            flags = [table.get(key) for table in atom_tables]
            present = all(flag is not None for flag in flags) and bool(flags)
            has_ca = present and all(flag["has_ca"] for flag in flags)  # type: ignore[index]
            has_cb = present and all(flag["has_cb"] for flag in flags)  # type: ignore[index]
            scores = [flag["plddt"] for flag in flags if flag and flag["plddt"] is not None]
            if not present or len(scores) < len(atom_tables):
                min_conf = None
            else:
                min_conf = min(scores)
            ensemble_row = rmsf_by_key.get(key)
            rmsf = None if ensemble_row is None else float(ensemble_row["ca_rmsf"])
            max_disp = None if ensemble_row is None else float(ensemble_row["max_displacement"])
            reasons = exclusion_reasons(
                amino_acid=item["amino_acid"],
                kabat_number=item["kabat_number"],
                is_cdr=bool(item["is_cdr"]),
                present_in_all_models=present,
                has_ca_in_all_models=has_ca,
                has_cb_in_all_models=has_cb,
                minimum_confidence=min_conf,
                ca_rmsf=rmsf,
            )
            eligible = not reasons
            rows.append(
                {
                    "structure_chain": chain,
                    "sequence_index": item["sequence_index"],
                    "amino_acid": item["amino_acid"],
                    "kabat_number": item["kabat_number"],
                    "kabat_region": item["kabat_region"],
                    "is_cdr": bool(item["is_cdr"]),
                    "is_native_cys": item["amino_acid"] == "C",
                    "is_glycine": item["amino_acid"] == "G",
                    "is_proline": item["amino_acid"] == "P",
                    "present_in_all_models": present,
                    "has_ca_in_all_models": has_ca,
                    "has_cb_in_all_models": has_cb,
                    "minimum_confidence": None if min_conf is None else round(float(min_conf), 2),
                    "ca_rmsf": rmsf,
                    "maximum_ca_displacement": max_disp,
                    "eligible_for_design": eligible,
                    "exclusion_reasons": reasons,
                    "exclusion_reason_text": ";".join(reasons),
                }
            )

    keys = [(row["structure_chain"], row["sequence_index"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("位点表出现重复的 (chain, sequence_index)")

    eligible_positions = [
        {"structure_chain": row["structure_chain"], "sequence_index": row["sequence_index"]}
        for row in rows
        if row["eligible_for_design"]
    ]
    return {
        "n_residues": len(rows),
        "n_eligible": len(eligible_positions),
        "thresholds": {
            "minimum_confidence": MINIMUM_CONFIDENCE,
            "maximum_ca_rmsf": MAXIMUM_CA_RMSF,
            "exclude_glycine": EXCLUDE_GLYCINE,
            "exclude_proline": EXCLUDE_PROLINE,
            "exclude_cdr": EXCLUDE_CDR,
        },
        "numbering": {
            chain: {"domain": data["domain"], "numbered": data["numbered"]}
            for chain, data in numbering_by_chain.items()
        },
        "residues": rows,
        "eligible_positions": eligible_positions,
        "structure_paths": [str(path) for path in paths],
    }
