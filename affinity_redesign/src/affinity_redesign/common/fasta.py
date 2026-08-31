"""FASTA 读写。"""

from __future__ import annotations

from pathlib import Path


def parse_fasta(text: str) -> dict[str, str]:
    seqs: dict[str, str] = {}
    cur_id: str | None = None
    chunks: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if cur_id is not None:
                seqs[cur_id] = "".join(chunks).upper().replace(" ", "")
            cur_id = line[1:].split()[0]
            chunks = []
        else:
            chunks.append(line)
    if cur_id is not None:
        seqs[cur_id] = "".join(chunks).upper().replace(" ", "")
    return seqs


def parse_fasta_file(path: Path) -> dict[str, str]:
    return parse_fasta(path.read_text(encoding="utf-8"))


def write_fasta(seqs: dict[str, str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for cid, seq in seqs.items():
        lines.append(f">{cid}")
        lines.append(seq)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
