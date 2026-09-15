"""工作流共用的简单 FASTA 读写。"""

from __future__ import annotations

from pathlib import Path


def parse_fasta(text: str) -> dict[str, str]:
    """按原工作流口径解析 FASTA，保留记录顺序并规范化序列。"""
    seqs: dict[str, str] = {}
    cur: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(">"):
            if cur is not None:
                seqs[cur] = "".join(buf).upper().replace(" ", "")
            cur = stripped[1:].split()[0]
            buf = []
        else:
            buf.append(stripped)
    if cur is not None:
        seqs[cur] = "".join(buf).upper().replace(" ", "")
    return seqs


def write_fasta(sequences: dict[str, str], path: Path) -> None:
    """以每条记录两行、文件末尾换行的固定格式写入 FASTA。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for chain_id, sequence in sequences.items():
        lines.extend((f">{chain_id}", sequence))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
