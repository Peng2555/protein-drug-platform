"""Boltz2 input parsing, validation, serialization, and job metadata."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

VALID_AA = set("ACDEFGHIKLMNPQRSTVWY")
# Boltz2 truncates chain names to 4 chars internally; longer IDs cause silent preprocess failure.
BOLTZ_MAX_CHAIN_ID_LEN = 4


def read_fasta(path: Path | str) -> dict[str, str]:
    path = Path(path)
    seqs: dict[str, str] = {}
    name: str | None = None
    parts: list[str] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            if name is not None:
                seqs[name] = validate_seq("".join(parts), name, str(path))
            name = line[1:].split()[0]
            parts = []
        else:
            parts.append(line.upper())
    if name is None:
        raise ValueError(f"Empty FASTA: {path}")
    seqs[name] = validate_seq("".join(parts), name, str(path))
    return seqs


def parse_fasta_text(text: str) -> dict[str, str]:
    seqs: dict[str, str] = {}
    name: str | None = None
    parts: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            if name is not None:
                seqs[name] = validate_seq("".join(parts), name, "input")
            name = line[1:].split()[0]
            parts = []
        else:
            parts.append(line.upper())
    if name is None:
        raise ValueError("Empty FASTA text")
    seqs[name] = validate_seq("".join(parts), name, "input")
    return seqs


def validate_seq(seq: str, chain_id: str, source: str) -> str:
    bad = sorted({c for c in seq if c not in VALID_AA})
    if bad:
        raise ValueError(f"{source} chain {chain_id}: invalid letters {bad}")
    if len(seq) < 5:
        raise ValueError(f"{source} chain {chain_id}: sequence too short ({len(seq)})")
    return seq


def validate_boltz_chain_ids(seqs: dict[str, str]) -> None:
    """Boltz2 requires chain IDs ≤4 characters (internal truncation breaks MSA mapping)."""
    too_long = sorted(cid for cid in seqs if len(cid) > BOLTZ_MAX_CHAIN_ID_LEN)
    if too_long:
        examples = ", ".join(f">{cid}" for cid in too_long[:3])
        raise ValueError(
            f"Boltz2 链 ID 不能超过 {BOLTZ_MAX_CHAIN_ID_LEN} 个字符，"
            f"当前过长: {too_long}。"
            f"请将 FASTA 头改为短 ID（如 >A、>H），例如把 {examples} 改为 ≤4 字符的唯一 ID。"
        )
    truncated = [cid[:BOLTZ_MAX_CHAIN_ID_LEN] for cid in seqs]
    if len(truncated) != len(set(truncated)):
        dupes = sorted({t for t in truncated if truncated.count(t) > 1})
        raise ValueError(
            f"Boltz2 链 ID 在前 {BOLTZ_MAX_CHAIN_ID_LEN} 个字符内必须唯一（Boltz 会截断长 ID），"
            f"冲突: {dupes}"
        )


def write_boltz_yaml(seqs: dict[str, str], path: Path) -> None:
    lines = ["version: 1", "sequences:"]
    for chain_id, seq in seqs.items():
        lines.append("  - protein:")
        lines.append(f"      id: {chain_id}")
        lines.append(f"      sequence: {seq}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _yaml_quote(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _format_chain_ids(ids: list[str]) -> str:
    if len(ids) == 1:
        return ids[0]
    return "[" + ", ".join(ids) + "]"


def build_boltz_yaml_text(
    components: list[dict],
    *,
    constraints: list[dict] | None = None,
    affinity_binder: str | None = None,
) -> str:
    """Build Boltz input YAML from structured components (protein/dna/rna/ligand)."""
    lines = ["version: 1", "sequences:"]
    for comp in components:
        entity = comp["entity"]
        ids = list(comp["ids"])
        lines.append(f"  - {entity}:")
        lines.append(f"      id: {_format_chain_ids(ids)}")
        if entity == "ligand":
            if comp.get("smiles"):
                lines.append(f"      smiles: {_yaml_quote(str(comp['smiles']).strip())}")
            elif comp.get("ccd"):
                lines.append(f"      ccd: {str(comp['ccd']).strip()}")
            else:
                raise ValueError("ligand requires smiles or ccd")
        else:
            seq = str(comp.get("sequence") or "").replace(" ", "").replace("\n", "").upper()
            lines.append(f"      sequence: {seq}")
            if comp.get("cyclic"):
                lines.append("      cyclic: true")
            mods = comp.get("modifications") or []
            if mods:
                lines.append("      modifications:")
                for mod in mods:
                    lines.append(f"        - position: {int(mod['position'])}")
                    lines.append(f"          ccd: {str(mod['ccd']).strip()}")

    if constraints:
        lines.append("constraints:")
        for c in constraints:
            ctype = c.get("type")
            if ctype == "pocket":
                lines.append("  - pocket:")
                lines.append(f"      binder: {c['binder']}")
                contact_parts = []
                for ch, res in c["contacts"]:
                    contact_parts.append(f"[{ch}, {int(res)}]")
                lines.append(f"      contacts: [ {', '.join(contact_parts)} ]")
                if c.get("max_distance") is not None:
                    lines.append(f"      max_distance: {float(c['max_distance'])}")
                if c.get("force"):
                    lines.append("      force: true")
            elif ctype == "contact":
                t1 = c["token1"]
                t2 = c["token2"]
                lines.append("  - contact:")
                lines.append(f"      token1: [{t1[0]}, {int(t1[1])}]")
                lines.append(f"      token2: [{t2[0]}, {int(t2[1])}]")
                if c.get("max_distance") is not None:
                    lines.append(f"      max_distance: {float(c['max_distance'])}")
                if c.get("force"):
                    lines.append("      force: true")
            else:
                raise ValueError(f"unsupported constraint type: {ctype}")

    if affinity_binder:
        lines.append("properties:")
        lines.append("  - affinity:")
        lines.append(f"      binder: {affinity_binder}")

    return "\n".join(lines) + "\n"


def write_boltz_complex_yaml(
    path: Path,
    components: list[dict],
    *,
    constraints: list[dict] | None = None,
    affinity_binder: str | None = None,
) -> str:
    text = build_boltz_yaml_text(
        components,
        constraints=constraints,
        affinity_binder=affinity_binder,
    )
    path.write_text(text, encoding="utf-8")
    return text


def polymer_seqs_from_components(components: list[dict]) -> dict[str, str]:
    """Expand copies into chain_id -> sequence for polymers only (for hashing / display)."""
    out: dict[str, str] = {}
    for comp in components:
        if comp.get("entity") == "ligand":
            continue
        seq = str(comp.get("sequence") or "").replace(" ", "").replace("\n", "").upper()
        for cid in comp["ids"]:
            out[str(cid)] = seq
    return out


def chains_meta_from_components(components: list[dict]) -> dict[str, int]:
    meta: dict[str, int] = {}
    for comp in components:
        if comp.get("entity") == "ligand":
            token = (comp.get("smiles") or comp.get("ccd") or "").strip()
            for cid in comp["ids"]:
                meta[str(cid)] = max(1, len(token))
        else:
            seq = str(comp.get("sequence") or "").replace(" ", "").replace("\n", "")
            for cid in comp["ids"]:
                meta[str(cid)] = len(seq)
    return meta


def write_fasta(seqs: dict[str, str], path: Path) -> None:
    lines: list[str] = []
    for chain_id, seq in seqs.items():
        lines.append(f">{chain_id}")
        lines.append(seq)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def job_id_from_seqs(seqs: dict[str, str], prefix: str | None = None) -> str:
    payload = json.dumps(seqs, sort_keys=True)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:12]
    if prefix:
        safe = re.sub(r"[^\w\-]", "_", prefix)[:40]
        return f"{safe}_{digest}"
    return digest
