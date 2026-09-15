"""Kabat CDR/FR 注释（ANARCI）。"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from boltzfold_shared.runtime.settings import settings

KABAT_CDR_HEAVY = {"CDR-H1": (31, 35), "CDR-H2": (50, 65), "CDR-H3": (95, 102)}
KABAT_CDR_LIGHT = {"CDR-L1": (24, 34), "CDR-L2": (50, 56), "CDR-L3": (89, 97)}


def _domain_from_anarci_chain_type(chain_type: str | None) -> str:
    ct = str(chain_type or "H").upper()
    return "L" if ct.startswith(("K", "L")) else "H"


def _cdr_defs(domain: str) -> dict[str, tuple[int, int]]:
    return KABAT_CDR_LIGHT if domain == "L" else KABAT_CDR_HEAVY


def _build_annotation(
    sequence: str, numbering: list, query_start: int, query_end: int, domain: str
) -> dict:
    cdr_defs = _cdr_defs(domain)
    index_to_kabat: dict[int, int] = {}
    seq_i = query_start
    for (pos, _ins), aa in numbering:
        if aa == "-":
            continue
        if isinstance(pos, int) and seq_i <= query_end:
            index_to_kabat[seq_i] = pos
        seq_i += 1
    spans = []
    for name, (lo, hi) in cdr_defs.items():
        indices = [i for i, pos in index_to_kabat.items() if lo <= pos <= hi]
        if indices:
            start, end = min(indices), max(indices)
            spans.append({"name": name, "start": start, "end": end, "sequence": sequence[start:end + 1]})
    cdr_sorted = sorted(cdr_defs.items(), key=lambda item: item[1][0])
    regions = []
    for i in range(len(sequence)):
        if i not in index_to_kabat:
            regions.append("OUT")
            continue
        pos = index_to_kabat[i]
        region = next((name for name, (lo, hi) in cdr_defs.items() if lo <= pos <= hi), None)
        if region is None:
            if pos < cdr_sorted[0][1][0]:
                region = "FR1"
            elif cdr_sorted[0][1][1] < pos < cdr_sorted[1][1][0]:
                region = "FR2"
            elif cdr_sorted[1][1][1] < pos < cdr_sorted[2][1][0]:
                region = "FR3"
            else:
                region = "FR4"
        regions.append(region)
    return {
        "domain": domain, "scheme": "kabat", "query_start": query_start,
        "query_end": query_end, "cdr_spans": spans, "regions": regions, "is_antibody": True,
    }


def _annotate_inprocess(sequence: str, hmmer_path: str) -> dict | None:
    from anarci import anarci

    if len(sequence) < 70 or len(sequence) > 400:
        return None
    hmmer = hmmer_path if Path(hmmer_path, "hmmscan").exists() else ""
    try:
        numbering_result, detail, _hit = anarci(
            [("query", sequence)], scheme="kabat", hmmerpath=hmmer
        )
    except Exception:
        return None
    if not numbering_result or not numbering_result[0]:
        return None
    numbering, query_start, query_end = numbering_result[0][0]
    domain = "H"
    if detail and detail[0] and isinstance(detail[0], list) and detail[0][0]:
        domain = _domain_from_anarci_chain_type(detail[0][0].get("chain_type", "H"))
    return _build_annotation(sequence, numbering, int(query_start), int(query_end), domain)


_HELPER = r"""
import json, sys
from pathlib import Path
from anarci import anarci
seq, hmmer = sys.argv[1], sys.argv[2]
defs_h = {"CDR-H1": (31,35), "CDR-H2": (50,65), "CDR-H3": (95,102)}
defs_l = {"CDR-L1": (24,34), "CDR-L2": (50,56), "CDR-L3": (89,97)}
hp = hmmer if Path(hmmer, "hmmscan").exists() else ""
nr, detail, _ = anarci([("query", seq)], scheme="kabat", hmmerpath=hp)
if not nr or not nr[0]:
 print("null"); raise SystemExit(0)
numbering, qs, qe = nr[0][0]
ct = detail[0][0].get("chain_type", "H") if detail and detail[0] and detail[0][0] else "H"
domain = "L" if str(ct).upper().startswith(("K","L")) else "H"
defs = defs_l if domain == "L" else defs_h
mapping = {}; idx = int(qs)
for (pos, _ins), aa in numbering:
 if aa == "-": continue
 if isinstance(pos, int) and idx <= int(qe): mapping[idx] = pos
 idx += 1
spans = []
for name, (lo, hi) in defs.items():
 hits = [i for i,p in mapping.items() if lo <= p <= hi]
 if hits:
  start,end=min(hits),max(hits); spans.append({"name":name,"start":start,"end":end,"sequence":seq[start:end+1]})
ordered=sorted(defs.items(), key=lambda item:item[1][0]); regions=[]
for i in range(len(seq)):
 if i not in mapping: regions.append("OUT"); continue
 pos=mapping[i]; region=next((n for n,(lo,hi) in defs.items() if lo <= pos <= hi),None)
 if region is None:
  region = "FR1" if pos < ordered[0][1][0] else ("FR2" if ordered[0][1][1] < pos < ordered[1][1][0] else ("FR3" if ordered[1][1][1] < pos < ordered[2][1][0] else "FR4"))
 regions.append(region)
print(json.dumps({"domain":domain,"scheme":"kabat","query_start":int(qs),"query_end":int(qe),"cdr_spans":spans,"regions":regions,"is_antibody":True}))
"""


def annotate_antibody_chain(
    sequence: str,
    *,
    anarci_python: str | None = None,
    hmmer_path: str | None = None,
) -> dict | None:
    """注释单链；不能识别为抗体/VHH 时返回 None。"""
    hmmer = hmmer_path or settings.hmmer_path
    try:
        return _annotate_inprocess(sequence, hmmer)
    except ImportError:
        pass
    py = anarci_python or settings.anarci_python
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
        handle.write(_HELPER)
        helper = handle.name
    try:
        proc = subprocess.run([py, helper, sequence, hmmer], capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"ANARCI 失败: {(proc.stderr or proc.stdout)[-2000:]}")
        out = proc.stdout.strip().splitlines()[-1]
        return None if out == "null" else json.loads(out)
    finally:
        Path(helper).unlink(missing_ok=True)


def region_for_index(ab: dict, index0: int) -> str:
    regions = ab.get("regions") or []
    return regions[index0] if 0 <= index0 < len(regions) else "OUT"


def annotate_regions(sequence: str) -> list[dict]:
    ab = annotate_antibody_chain(sequence)
    return [{"name": "FULL", "start": 0, "end": len(sequence) - 1}] if ab is None else ab["cdr_spans"]
