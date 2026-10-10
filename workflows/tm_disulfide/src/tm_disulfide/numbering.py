"""单链 Kabat 编号；插入码保留为字符串。"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from boltzfold_shared.runtime.settings import settings
from tm_disulfide.constants import KABAT_CDR_HEAVY, KABAT_CDR_LIGHT

_HELPER = r"""
import json, sys
from pathlib import Path
from anarci import anarci
seq = sys.stdin.read().strip()
hmmer = sys.argv[1]
hp = hmmer if Path(hmmer, "hmmscan").exists() else ""
kwargs = {"scheme": "kabat"}
if hp:
    kwargs["hmmerpath"] = hp
nr, detail, _ = anarci([("query", seq)], **kwargs)
if not nr or not nr[0]:
    print("null")
    raise SystemExit(0)
numbering, qs, qe = nr[0][0]
ct = "H"
if detail and detail[0] and isinstance(detail[0], list) and detail[0][0]:
    ct = str(detail[0][0].get("chain_type") or "H")
rows = []
idx = int(qs)
for (pos, ins), aa in numbering:
    if aa == "-":
        continue
    rows.append({"seq_index": idx, "pos": pos, "ins": ins, "aa": aa})
    idx += 1
print(json.dumps({"chain_type": ct, "query_start": int(qs), "query_end": int(qe), "rows": rows}))
"""


def _domain_from_chain_type(chain_type: str | None) -> str:
    ct = str(chain_type or "H").upper()
    return "L" if ct.startswith(("K", "L")) else "H"


def kabat_region(pos: int, domain: str) -> str:
    """按 Kabat 整数位划分 CDR/FR；31A 的 pos=31，仍属 CDR-H1。"""
    defs = KABAT_CDR_LIGHT if domain == "L" else KABAT_CDR_HEAVY
    for name, (lo, hi) in defs.items():
        if lo <= pos <= hi:
            return name
    ordered = sorted(defs.items(), key=lambda item: item[1][0])
    if pos < ordered[0][1][0]:
        return "FR1"
    if ordered[0][1][1] < pos < ordered[1][1][0]:
        return "FR2"
    if ordered[1][1][1] < pos < ordered[2][1][0]:
        return "FR3"
    return "FR4"


def format_kabat_number(pos: int, ins: str | None) -> str:
    insertion = str(ins or "").strip()
    return f"{pos}{insertion}" if insertion else str(pos)


def _anarci_inprocess(sequence: str) -> dict[str, Any] | None:
    from anarci import anarci

    hmmer = ""
    candidate = Path(settings.hmmer_path)
    if (candidate / "hmmscan").exists():
        hmmer = str(candidate)
    kwargs: dict[str, Any] = {"scheme": "kabat"}
    if hmmer:
        kwargs["hmmerpath"] = hmmer
    numbering_result, detail, _hit = anarci([("query", sequence)], **kwargs)
    if not numbering_result or not numbering_result[0]:
        return None
    numbering, query_start, query_end = numbering_result[0][0]
    chain_type = "H"
    if detail and detail[0] and isinstance(detail[0], list) and detail[0][0]:
        chain_type = str(detail[0][0].get("chain_type") or "H")
    rows = []
    seq_i = int(query_start)
    for (pos, ins), aa in numbering:
        if aa == "-":
            continue
        rows.append({"seq_index": seq_i, "pos": pos, "ins": ins, "aa": aa})
        seq_i += 1
    return {
        "chain_type": chain_type,
        "query_start": int(query_start),
        "query_end": int(query_end),
        "rows": rows,
    }


def _anarci_subprocess(sequence: str) -> dict[str, Any] | None:
    hmmer = settings.hmmer_path
    py = settings.anarci_python
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
        handle.write(_HELPER)
        helper = handle.name
    try:
        proc = subprocess.run(
            [py, helper, hmmer],
            input=sequence,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"ANARCI 失败: {(proc.stderr or proc.stdout)[-2000:]}")
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        if not lines or lines[-1] == "null":
            return None
        return json.loads(lines[-1])
    finally:
        Path(helper).unlink(missing_ok=True)


def number_kabat_chain(sequence: str) -> dict[str, Any]:
    """对一条 FASTA 链做 Kabat 编号。编不上的位置 kabat_number 为空、region=OUT。"""
    sequence = sequence.upper().replace(" ", "")
    raw: dict[str, Any] | None = None
    try:
        raw = _anarci_inprocess(sequence)
    except ImportError:
        raw = _anarci_subprocess(sequence)
    domain = _domain_from_chain_type((raw or {}).get("chain_type"))
    by_index: dict[int, dict[str, Any]] = {}
    if raw:
        for item in raw["rows"]:
            pos = item["pos"]
            if not isinstance(pos, int):
                continue
            seq_index = int(item["seq_index"]) + 1
            by_index[seq_index] = {
                "kabat_number": format_kabat_number(pos, item.get("ins")),
                "kabat_pos": pos,
                "kabat_region": kabat_region(pos, domain),
            }
    residues = []
    for offset, aa in enumerate(sequence, start=1):
        hit = by_index.get(offset)
        region = hit["kabat_region"] if hit else "OUT"
        residues.append(
            {
                "sequence_index": offset,
                "amino_acid": aa,
                "kabat_number": hit["kabat_number"] if hit else "",
                "kabat_region": region,
                "is_cdr": region.startswith("CDR"),
                "domain": domain if hit else "",
            }
        )
    return {
        "sequence": sequence,
        "domain": domain if raw else "",
        "scheme": "kabat",
        "numbered": bool(raw),
        "residues": residues,
    }
