"""Decode uploaded CSV / TXT / Excel files with common Chinese encodings."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from xml.etree import ElementTree as ET

from fastapi import HTTPException

_XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_AA = set("ACDEFGHIKLMNPQRSTVWY")


def _strip_bom(text: str) -> str:
    return text.lstrip("\ufeff")


def _looks_like_sequence(raw: str) -> bool:
    seq = re.sub(r"[\s\d]", "", raw.upper())
    if len(seq) < 5:
        return False
    return all(ch in _AA for ch in seq)


def _text_quality(text: str) -> float:
    if not text.strip():
        return 0.0
    length = max(len(text), 1)
    bad = text.count("\ufffd")
    ctrl = sum(1 for ch in text if ord(ch) < 32 and ch not in "\t\n\r")
    printable = sum(1 for ch in text if ch.isprintable() or ch in "\t\n\r")
    score = printable / length - bad * 0.25 - ctrl * 0.05
    if any(sep in text for sep in (",", "\t", ";")):
        score += 0.1
    first = text.splitlines()[0] if text.splitlines() else ""
    if re.search(r"vhh|sequence|id|重链|序列", first, re.I):
        score += 0.15
    if text.lstrip().startswith(">"):
        score += 0.2
    if re.search(r"[A-Za-z]{10,}", text):
        score += 0.08
    # Penalize mojibake from latin-1 misread of GBK
    if re.search(r"[\u0080-\u009f]", text):
        score -= 0.2
    return score


def _looks_utf16le(data: bytes) -> bool:
    if len(data) < 4:
        return False
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return True
    sample = data[: min(len(data), 512)]
    if len(sample) < 4:
        return False
    odd_zeros = sum(1 for i in range(1, len(sample), 2) if sample[i] == 0)
    return odd_zeros / max(len(sample) // 2, 1) > 0.6


def _looks_like_gbk(data: bytes) -> bool:
    pairs = 0
    i = 0
    while i < len(data) - 1:
        b1, b2 = data[i], data[i + 1]
        if 0x81 <= b1 <= 0xFE and 0x40 <= b2 <= 0xFE:
            pairs += 1
            i += 2
        else:
            i += 1
    return pairs >= 2


def _col_to_index(col: str) -> int:
    idx = 0
    for ch in col.upper():
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def _xlsx_to_csv_text(data: bytes) -> str:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise HTTPException(400, "文件不是有效的 Excel 工作簿") from exc

    shared: list[str] = []
    if "xl/sharedStrings.xml" in zf.namelist():
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        for si in root.findall(f"{_XLSX_NS}si"):
            parts = [node.text or "" for node in si.iter(f"{_XLSX_NS}t")]
            shared.append("".join(parts))

    sheet_names = sorted(n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
    if not sheet_names:
        raise HTTPException(400, "Excel 文件中没有工作表")

    root = ET.fromstring(zf.read(sheet_names[0]))
    rows: dict[int, dict[int, str]] = {}
    for row in root.findall(f".//{_XLSX_NS}row"):
        for cell in row.findall(f"{_XLSX_NS}c"):
            ref = cell.get("r") or ""
            letters = "".join(ch for ch in ref if ch.isalpha())
            digits = "".join(ch for ch in ref if ch.isdigit())
            if not letters or not digits:
                continue
            row_idx = int(digits)
            col_idx = _col_to_index(letters)
            value_node = cell.find(f"{_XLSX_NS}v")
            if value_node is None or value_node.text is None:
                value = ""
            elif cell.get("t") == "s":
                value = shared[int(value_node.text)]
            else:
                value = value_node.text
            rows.setdefault(row_idx, {})[col_idx] = value

    if not rows:
        raise HTTPException(400, "Excel 工作表为空")

    lines: list[str] = []
    for row_idx in sorted(rows):
        cols = rows[row_idx]
        max_col = max(cols) if cols else 0
        lines.append(",".join(cols.get(i, "") for i in range(max_col + 1)))
    return "\n".join(lines)


def decode_upload_bytes(data: bytes, filename: str = "") -> tuple[str, str]:
    if not data:
        raise HTTPException(400, "文件为空")

    if len(data) >= 4 and data[:4] == b"\xd0\xcf\x11\xe0":
        raise HTTPException(400, "检测到旧版 Excel (.xls)，请在 Excel 中另存为 .xlsx 或 CSV/TXT")

    ext = (filename.rsplit(".", 1)[-1].lower() if "." in filename else "")
    if ext in {"xlsx", "xlsm"} or (len(data) >= 2 and data[:2] == b"PK"):
        return _strip_bom(_xlsx_to_csv_text(data)), "Excel (.xlsx)"

    if data[:3] == b"\xef\xbb\xbf":
        text = _strip_bom(data[3:].decode("utf-8"))
        return text, "UTF-8 BOM"

    if data[:2] == b"\xff\xfe":
        return _strip_bom(data[2:].decode("utf-16-le")), "UTF-16 LE"
    if data[:2] == b"\xfe\xff":
        return _strip_bom(data[2:].decode("utf-16-be")), "UTF-16 BE"

    candidates: list[tuple[str, str]] = []
    if _looks_utf16le(data):
        try:
            candidates.append(("UTF-16 LE", _strip_bom(data.decode("utf-16-le"))))
        except UnicodeDecodeError:
            pass

    encodings = ["utf-8", "gb18030", "gbk", "gb2312", "cp936"]
    if _looks_like_gbk(data):
        encodings = ["gb18030", "gbk", "cp936", "gb2312", "utf-8"]

    for enc in encodings:
        try:
            candidates.append((enc.upper(), _strip_bom(data.decode(enc))))
        except UnicodeDecodeError:
            continue

    if not candidates:
        raise HTTPException(400, "无法识别文件编码，请用记事本另存为 UTF-8 TXT")

    best_enc, best_text = max(candidates, key=lambda item: _text_quality(item[1]))
    if _text_quality(best_text) < 0.4:
        raise HTTPException(
            400,
            "文件内容无法识别为文本。请确认：\n"
            "1) 不是 Excel 工作簿误改名为 .csv/.txt\n"
            "2) 用记事本/Excel 另存为 UTF-8 或 CSV",
        )
    return best_text, best_enc


def _split_csv_line(line: str) -> list[str]:
    if "\t" in line:
        return [p.strip() for p in line.split("\t")]
    try:
        return next(csv.reader([line]))
    except csv.Error:
        if ";" in line and line.count(";") >= line.count(","):
            return [p.strip() for p in line.split(";")]
        if "|" in line:
            return [p.strip() for p in line.split("|")]
        return [p.strip() for p in line.split(",")]


def _parse_fasta_text(text: str) -> list[tuple[str, str]]:
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


def _parse_line_to_row(line: str, auto_idx: int) -> tuple[tuple[str, str] | None, int]:
    parts = _split_csv_line(line)
    if len(parts) >= 2:
        hid = parts[0].strip().strip('"')
        seq = (parts[1] if len(parts) == 2 else ",".join(parts[1:])).strip().strip('"')
        seq = re.sub(r"\s+", "", seq).upper()
        if hid and _looks_like_sequence(seq):
            return (hid, seq), auto_idx
        return None, auto_idx

    ws = re.match(r"^(\S+)\s+([ACDEFGHIKLMNPQRSTVWY\s]+)$", line, re.I)
    if ws:
        hid = ws.group(1).strip()
        seq = re.sub(r"\s+", "", ws.group(2)).upper()
        if hid and _looks_like_sequence(seq):
            return (hid, seq), auto_idx

    if _looks_like_sequence(line):
        hid = f"VHH_{auto_idx:03d}"
        return (hid, re.sub(r"\s+", "", line).upper()), auto_idx + 1

    return None, auto_idx


def parse_heavy_chain_text(text: str) -> tuple[list[tuple[str, str]], str]:
    """Parse CSV/TXT/TSV/FASTA. Returns (rows, format 'csv'|'fasta')."""
    text = _strip_bom(text.strip())
    if not text:
        return [], "csv"

    if text.lstrip().startswith(">"):
        return _parse_fasta_text(text), "fasta"

    lines = [ln for ln in text.splitlines() if ln.strip()]
    start = 0
    header = lines[0].lower().replace(" ", "")
    if any(k in header for k in ("vhh_id", "sequence", "重链", "序列")) or header.startswith(("id,", "id;", "id\t")):
        start = 1

    rows: list[tuple[str, str]] = []
    auto_idx = 1
    for line in lines[start:]:
        row, auto_idx = _parse_line_to_row(line, auto_idx)
        if row:
            rows.append(row)
    return rows, "csv"


def parse_heavy_chain_csv_lenient(text: str) -> list[tuple[str, str]]:
    rows, _fmt = parse_heavy_chain_text(text)
    return rows


def format_heavy_chain_display(rows: list[tuple[str, str]], fmt: str) -> str:
    if not rows:
        return ""
    if fmt == "fasta":
        return "\n".join(f">{hid}\n{seq}" for hid, seq in rows) + "\n"
    lines = ["vhh_id,sequence"]
    lines.extend(f"{hid},{seq}" for hid, seq in rows)
    return "\n".join(lines)
