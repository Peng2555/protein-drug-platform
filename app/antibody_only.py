"""Antibody-only batch: many VHH or H+L antibodies, no antigen."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

from fastapi import HTTPException

from app.config import settings
from app.vhh_panel import _sanitize_batch_name, _sanitize_id

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "scripts"))
from boltz_runner import validate_seq

_AA = set("ACDEFGHIKLMNPQRSTVWY")
_ROLE_SUFFIX = re.compile(
    r"^(?P<base>.+?)(?:[_/\-|.]|chain)(?P<role>heavy|light|h|l)$",
    re.I,
)
_ID_HEADERS = {"id", "vhh_id", "name", "antibody_id", "ab_id", "抗体id"}
_HEAVY_HEADERS = {
    "heavy",
    "heavy_sequence",
    "heavy_seq",
    "h",
    "sequence",
    "seq",
    "序列",
    "重链",
    "重链序列",
}
_LIGHT_HEADERS = {"light", "light_sequence", "light_seq", "l", "轻链", "轻链序列"}


@dataclass
class AntibodySpec:
    id: str
    heavy: str
    light: str | None = None


def _looks_like_sequence(raw: str) -> bool:
    seq = re.sub(r"[\s\d]", "", raw.upper())
    return len(seq) >= 5 and all(ch in _AA for ch in seq)


def _norm_seq(raw: str) -> str:
    return re.sub(r"\s+", "", raw).upper()


def _header_key(raw: str) -> str:
    return raw.strip().lower().replace(" ", "_")


def _classify_fasta_header(hid: str) -> tuple[str, str | None]:
    """Return (base_id, role) where role is H, L, or None (VHH / unlabeled)."""
    u = hid.strip()
    if not u:
        raise HTTPException(400, "FASTA 头为空")
    ul = u.upper()
    if ul in {"H", "HEAVY"}:
        return "", "H"
    if ul in {"L", "LIGHT"}:
        return "", "L"
    m = _ROLE_SUFFIX.match(u)
    if m:
        role = m.group("role").upper()
        base = m.group("base").rstrip("_-./|")
        if not base:
            raise HTTPException(400, f"无法从 FASTA 头解析抗体 ID: {hid!r}")
        if role in {"HEAVY", "H"}:
            return base, "H"
        if role in {"LIGHT", "L"}:
            return base, "L"
    return u, None


def _parse_fasta_records(text: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    cur_id: str | None = None
    parts: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            if cur_id:
                seq = "".join(parts).upper()
                if len(seq) >= 5:
                    rows.append((cur_id, seq))
            cur_id = line[1:].split()[0].strip()
            parts = []
        elif cur_id:
            parts.append(re.sub(r"\s+", "", line))
    if cur_id:
        seq = "".join(parts).upper()
        if len(seq) >= 5:
            rows.append((cur_id, seq))
    return rows


def parse_antibody_fasta(text: str) -> list[AntibodySpec]:
    records = _parse_fasta_records(text)
    if not records:
        raise HTTPException(400, "抗体 FASTA 为空")

    grouped: dict[str, dict[str, str]] = {}
    unlabeled: list[tuple[str, str]] = []
    generic_h: list[str] = []
    generic_l: list[str] = []

    for hid, seq in records:
        base, role = _classify_fasta_header(hid)
        if base == "" and role == "H":
            generic_h.append(seq)
            continue
        if base == "" and role == "L":
            generic_l.append(seq)
            continue
        if role is None:
            unlabeled.append((hid, seq))
            continue
        slot = grouped.setdefault(base, {})
        if role in slot:
            raise HTTPException(400, f"抗体 {base} 的{role}链重复")
        slot[role] = seq

    antibodies: list[AntibodySpec] = []

    if generic_h or generic_l:
        if len(generic_h) == 1 and len(generic_l) == 1:
            antibodies.append(AntibodySpec(id="Ab", heavy=generic_h[0], light=generic_l[0]))
        elif generic_l and not generic_h:
            raise HTTPException(400, "FASTA 中有轻链 L，但缺少配对重链 H")
        elif generic_l and len(generic_h) != len(generic_l):
            raise HTTPException(400, "通用链头 >H / >L 数量不匹配，请改用 Ab1_H / Ab1_L")
        elif generic_l:
            for i, (h, l) in enumerate(zip(generic_h, generic_l), start=1):
                antibodies.append(AntibodySpec(id=f"Ab{i}", heavy=h, light=l))
        else:
            for i, seq in enumerate(generic_h, start=1):
                antibodies.append(AntibodySpec(id="H" if len(generic_h) == 1 else f"H{i}", heavy=seq))

    for hid, seq in unlabeled:
        antibodies.append(AntibodySpec(id=hid, heavy=seq))

    for base, slot in grouped.items():
        if "L" in slot and "H" not in slot:
            raise HTTPException(400, f"抗体 {base} 只有轻链，缺少重链（可用 {base}_H）")
        antibodies.append(
            AntibodySpec(id=base, heavy=slot["H"], light=slot.get("L")),
        )

    if not antibodies:
        raise HTTPException(400, "未解析到有效抗体序列")
    ids = [ab.id for ab in antibodies]
    dup = next((x for i, x in enumerate(ids) if x in ids[:i]), None)
    if dup:
        raise HTTPException(400, f"抗体 ID 重复: {dup}")
    return antibodies


def _split_csv_line(line: str) -> list[str]:
    if "\t" in line:
        return [p.strip() for p in line.split("\t")]
    try:
        return [p.strip() for p in next(csv.reader([line]))]
    except csv.Error:
        if ";" in line and line.count(";") >= line.count(","):
            return [p.strip() for p in line.split(";")]
        return [p.strip() for p in line.split(",")]


def _looks_like_header(parts: list[str]) -> bool:
    keys = {_header_key(p) for p in parts}
    return bool(keys & (_ID_HEADERS | _HEAVY_HEADERS | _LIGHT_HEADERS | {"序列"}))


def parse_antibody_csv(text: str) -> list[AntibodySpec]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise HTTPException(400, "抗体 CSV 为空")

    first = _split_csv_line(lines[0])
    start = 0
    id_i, heavy_i, light_i = 0, 1, None
    if _looks_like_header(first):
        start = 1
        keys = [_header_key(p) for p in first]
        id_i = next((i for i, k in enumerate(keys) if k in _ID_HEADERS), 0)
        heavy_i = next((i for i, k in enumerate(keys) if k in _HEAVY_HEADERS), 1)
        light_i = next((i for i, k in enumerate(keys) if k in _LIGHT_HEADERS), None)
        if heavy_i == id_i:
            heavy_i = 1 if len(first) > 1 else 1
    elif len(first) >= 3:
        light_i = 2

    rows: list[AntibodySpec] = []
    auto_idx = 1
    for line in lines[start:]:
        parts = _split_csv_line(line)
        if not parts:
            continue
        if len(parts) == 1 and _looks_like_sequence(parts[0]):
            hid = f"Ab_{auto_idx:03d}"
            auto_idx += 1
            rows.append(AntibodySpec(id=hid, heavy=_norm_seq(parts[0])))
            continue
        hid = (parts[id_i] if id_i < len(parts) else "").strip().strip('"')
        if not hid:
            hid = f"Ab_{auto_idx:03d}"
            auto_idx += 1
        heavy_raw = parts[heavy_i] if heavy_i < len(parts) else ""
        light_raw = ""
        if light_i is not None and light_i < len(parts):
            light_raw = parts[light_i]
        elif light_i is None and len(parts) >= 3 and _looks_like_sequence(parts[2]):
            light_raw = parts[2]
        heavy = _norm_seq(heavy_raw.strip().strip('"'))
        light = _norm_seq(light_raw.strip().strip('"')) if light_raw.strip() else None
        if not _looks_like_sequence(heavy):
            continue
        if light and not _looks_like_sequence(light):
            raise HTTPException(400, f"{hid} 的轻链不是有效氨基酸序列")
        rows.append(AntibodySpec(id=hid, heavy=heavy, light=light))

    if not rows:
        raise HTTPException(400, "CSV 为空或格式无效，需表头 id,heavy[,light]")
    return rows


def parse_antibody_text(text: str) -> tuple[list[AntibodySpec], str]:
    text = text.lstrip("\ufeff").strip()
    if not text:
        return [], "csv"
    if text.lstrip().startswith(">"):
        return parse_antibody_fasta(text), "fasta"
    return parse_antibody_csv(text), "csv"


def format_antibody_display(rows: list[AntibodySpec], fmt: str) -> str:
    if not rows:
        return ""
    if fmt == "fasta":
        lines: list[str] = []
        for ab in rows:
            if ab.light:
                lines.append(f">{ab.id}_H\n{ab.heavy}")
                lines.append(f">{ab.id}_L\n{ab.light}")
            else:
                lines.append(f">{ab.id}\n{ab.heavy}")
        return "\n".join(lines) + "\n"
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "heavy", "light"])
    for ab in rows:
        writer.writerow([ab.id, ab.heavy, ab.light or ""])
    return buf.getvalue()


def build_antibody_fasta(ab: AntibodySpec, heavy_chain_id: str, light_chain_id: str) -> str:
    h_id = _sanitize_id(heavy_chain_id, "重链链 ID")
    try:
        h = validate_seq(ab.heavy.upper(), h_id, "heavy")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not ab.light:
        return f">{h_id}\n{h}\n"
    l_id = _sanitize_id(light_chain_id, "轻链链 ID")
    if h_id == l_id:
        raise HTTPException(400, "重链与轻链链 ID 不能相同")
    try:
        light = validate_seq(ab.light.upper(), l_id, "light")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return f">{h_id}\n{h}\n>{l_id}\n{light}\n"


def prepare_antibody_only_jobs(
    *,
    batch_name: str | None,
    antibodies: list[AntibodySpec],
    heavy_chain_id: str = "H",
    light_chain_id: str = "L",
) -> tuple[str, list[tuple[str, str, str]], int]:
    """Returns (batch_name, [(job_name, antibody_id, fasta), ...], skipped_dupes)."""
    if not antibodies:
        raise HTTPException(400, "请至少提供一条抗体序列")
    if len(antibodies) > settings.max_vhh_panel_size:
        raise HTTPException(400, f"抗体数量超过上限 {settings.max_vhh_panel_size}")

    batch = _sanitize_batch_name(batch_name or "antibody_batch")
    h_id = _sanitize_id(heavy_chain_id, "重链链 ID")
    l_id = _sanitize_id(light_chain_id, "轻链链 ID")

    seen_ids: set[str] = set()
    seen_seqs: set[tuple[str, str]] = set()
    jobs: list[tuple[str, str, str]] = []
    skipped = 0

    for ab in antibodies:
        hid = _sanitize_id(ab.id, "抗体")
        if hid in seen_ids:
            raise HTTPException(400, f"抗体 ID 重复: {hid}")
        seen_ids.add(hid)

        heavy = ab.heavy.strip().upper().replace(" ", "")
        light = ab.light.strip().upper().replace(" ", "") if ab.light else ""
        key = (heavy, light)
        if key in seen_seqs:
            skipped += 1
            continue
        seen_seqs.add(key)

        spec = AntibodySpec(id=hid, heavy=heavy, light=light or None)
        fasta = build_antibody_fasta(spec, h_id, l_id)
        total_len = len(heavy) + len(light)
        if total_len > settings.max_total_sequence_length:
            raise HTTPException(
                400,
                f"{hid} 总长度 {total_len} 超过上限 {settings.max_total_sequence_length}",
            )
        job_name = f"{batch}_{hid}"[:128]
        jobs.append((job_name, hid, fasta))

    if not jobs:
        raise HTTPException(400, "去重后没有可提交的抗体")
    return batch, jobs, skipped
