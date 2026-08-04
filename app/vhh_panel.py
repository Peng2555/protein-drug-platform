"""VHH panel: one target antigen × many heavy chains → H+A fold jobs."""

from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi import HTTPException

from app.config import settings

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "scripts"))
from boltz_runner import parse_fasta_text, validate_seq


def _sanitize_id(raw: str, field: str) -> str:
    s = raw.strip()
    if not s:
        raise HTTPException(400, f"{field} ID 不能为空")
    if not re.match(r"^[\w\-\.$]+$", s):
        raise HTTPException(400, f"{field} ID 含非法字符（允许字母数字、_ - . $）: {raw!r}")
    return s[:64]


def _sanitize_batch_name(raw: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", raw.strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return (s or "vhh_panel")[:128]


@dataclass
class TargetSpec:
    name: str
    chain_id: str
    sequence: str


@dataclass
class HeavyChainSpec:
    id: str
    sequence: str


def parse_heavy_chain_fasta(text: str) -> list[HeavyChainSpec]:
    seqs = parse_fasta_text(text)
    if not seqs:
        raise HTTPException(400, "重链 FASTA 为空")
    return [HeavyChainSpec(id=_sanitize_id(cid, "重链"), sequence=seq) for cid, seq in seqs.items()]


def parse_heavy_chain_csv(text: str) -> list[HeavyChainSpec]:
    from app.csv_decode import parse_heavy_chain_csv_lenient

    parsed = parse_heavy_chain_csv_lenient(text)
    if not parsed:
        raise HTTPException(400, "CSV 为空或格式无效，需表头 vhh_id,sequence")

    rows: list[HeavyChainSpec] = []
    for i, (hid_raw, seq) in enumerate(parsed, start=1):
        hid = _sanitize_id(hid_raw, "重链")
        validate_seq(seq, hid, f"CSV line {i}")
        rows.append(HeavyChainSpec(id=hid, sequence=seq))
    return rows


def build_ha_fasta(heavy_chain_id: str, heavy_seq: str, target: TargetSpec) -> str:
    h = validate_seq(heavy_seq.upper(), heavy_chain_id, "heavy")
    a = validate_seq(target.sequence.upper(), target.chain_id, "target")
    return f">{heavy_chain_id}\n{h}\n>{target.chain_id}\n{a}\n"


def prepare_panel_jobs(
    *,
    batch_name: str | None,
    target_name: str,
    target_chain_id: str,
    target_sequence: str,
    heavy_chain_id: str,
    heavy_chains: list[HeavyChainSpec],
) -> tuple[str, TargetSpec, list[tuple[str, str, str]], int]:
    """Returns (batch_name, target, [(job_name, heavy_id, fasta_text), ...], skipped_dupes)."""
    if not heavy_chains:
        raise HTTPException(400, "请至少提供一条重链序列")

    if len(heavy_chains) > settings.max_vhh_panel_size:
        raise HTTPException(400, f"重链数量超过上限 {settings.max_vhh_panel_size}")

    target = TargetSpec(
        name=_sanitize_batch_name(target_name),
        chain_id=_sanitize_id(target_chain_id, "靶点链"),
        sequence=target_sequence.strip().upper().replace(" ", ""),
    )
    validate_seq(target.sequence, target.chain_id, "target")

    hc_id = _sanitize_id(heavy_chain_id, "重链链 ID")
    batch = _sanitize_batch_name(batch_name or f"{target.name}_VHH_panel")

    seen_ids: set[str] = set()
    seen_seqs: set[str] = set()
    jobs: list[tuple[str, str, str]] = []
    skipped_dupes = 0

    for hc in heavy_chains:
        hid = _sanitize_id(hc.id, "重链")
        if hid in seen_ids:
            raise HTTPException(400, f"重链 ID 重复: {hid}")
        seen_ids.add(hid)

        seq = hc.sequence.strip().upper().replace(" ", "")
        if seq in seen_seqs:
            skipped_dupes += 1
            continue
        seen_seqs.add(seq)

        fasta = build_ha_fasta(hc_id, seq, target)
        total_len = len(seq) + len(target.sequence)
        if total_len > settings.max_total_sequence_length:
            raise HTTPException(400, f"{hid} 复合物总长度 {total_len} 超过上限 {settings.max_total_sequence_length}")

        job_name = f"{target.name}_{hid}"[:128]
        jobs.append((job_name, hid, fasta))

    if not jobs:
        raise HTTPException(400, "去重后没有可提交的重链")

    return batch, target, jobs, skipped_dupes
