"""Shared parsing and upload helpers for antibody analysis services."""

from __future__ import annotations

import re
from collections.abc import Collection
from pathlib import Path

from fastapi import HTTPException, UploadFile

ALLOWED_STRUCTURE_SUFFIXES = frozenset({".pdb", ".cif", ".mmcif"})
_NON_AA = re.compile(r"[^A-Za-z]")


def parse_vhh_records(
    fasta_text: str,
    *,
    min_length: int = 70,
    empty_error: str = "FASTA 无效：未解析到任何链",
    plain_too_short_error: str = "FASTA 序列过短，需要完整 VHH 可变区",
    records_too_short_template: str = "序列过短（需完整 VHH）：{ids}",
) -> list[tuple[str, str]]:
    """Parse one or more VHH records while preserving duplicate IDs deterministically."""
    text = (fasta_text or "").replace("\r", "").strip()
    if not text:
        raise HTTPException(400, empty_error)
    if ">" not in text:
        sequence = _NON_AA.sub("", text).upper()
        if len(sequence) < min_length:
            raise HTTPException(400, plain_too_short_error)
        return [("H", sequence)]

    records: list[tuple[str, str]] = []
    current = "seq1"
    buffer: list[str] = []
    seen: dict[str, int] = {}
    for line in text.split("\n"):
        value = line.strip()
        if not value:
            continue
        if value.startswith(">"):
            if buffer:
                sequence = _NON_AA.sub("", "".join(buffer)).upper()
                if sequence:
                    records.append((current, sequence))
            raw = value[1:].split()[0] or "seq"
            occurrence = seen.get(raw, 0) + 1
            seen[raw] = occurrence
            current = raw if occurrence == 1 else f"{raw}_{occurrence}"
            buffer = []
        else:
            buffer.append(value)
    if buffer:
        sequence = _NON_AA.sub("", "".join(buffer)).upper()
        if sequence:
            records.append((current, sequence))

    if not records:
        raise HTTPException(400, empty_error)
    too_short = [record_id for record_id, sequence in records if len(sequence) < min_length]
    if too_short:
        raise HTTPException(400, records_too_short_template.format(ids=", ".join(too_short[:8])))
    return records


def parse_fasta_chain_lengths(
    fasta_text: str,
    *,
    allowed_chain_ids: Collection[str],
    extra_chains_error_template: str,
    min_total_length: int,
    too_short_error: str,
    empty_error: str = "FASTA 无效：未解析到任何链",
    normalize_single_chain_to_h: bool = True,
) -> dict[str, int]:
    """Parse FASTA chain lengths with service-specific validation messages."""
    chains: dict[str, int] = {}
    current: str | None = None
    buffer: list[str] = []
    for line in (fasta_text or "").replace("\r", "").split("\n"):
        value = line.strip()
        if not value:
            continue
        if value.startswith(">"):
            if current is not None:
                chains[current] = len("".join(buffer))
            current = value[1:].split()[0] or "seq"
            buffer = []
        else:
            buffer.append(re.sub(r"\s+", "", value))
    if current is not None:
        chains[current] = len("".join(buffer))
    if not chains:
        raise HTTPException(400, empty_error)
    if normalize_single_chain_to_h and "H" not in chains and len(chains) == 1:
        chains = {"H": next(iter(chains.values()))}

    extra = [chain_id for chain_id in chains if chain_id not in allowed_chain_ids]
    if extra:
        raise HTTPException(400, extra_chains_error_template.format(ids=", ".join(extra)))
    if sum(chains.values()) < min_total_length:
        raise HTTPException(400, too_short_error)
    return chains


async def save_structure_upload(
    upload: UploadFile,
    destination: Path,
    *,
    allowed_suffixes: Collection[str] = ALLOWED_STRUCTURE_SUFFIXES,
    invalid_suffix_error: str = "结构需为 .pdb / .cif / .mmcif",
    min_bytes: int = 80,
    too_small_error: str = "上传的结构文件太小或为空",
    default_filename: str = "ab.pdb",
    normalize_mmcif_suffix: bool = True,
) -> Path:
    """Validate and persist an uploaded structure using configurable API semantics."""
    suffix = Path(upload.filename or default_filename).suffix.lower()
    if suffix not in allowed_suffixes:
        raise HTTPException(400, invalid_suffix_error)
    if normalize_mmcif_suffix and suffix == ".mmcif":
        destination = destination.with_suffix(".cif")
    content = await upload.read()
    if len(content) < min_bytes:
        raise HTTPException(400, too_small_error)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return destination
