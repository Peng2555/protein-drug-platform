"""Kappa 轻链必须用 CDR-L 区间，不能当成重链。"""

from __future__ import annotations

import pytest

KAPPA = (
    "DIVMTQSPDSLAVSLGERATINCKSSQSILFSSNNKNYLAWYQQKPGQPPKLLIYWASTRES"
    "GVPDRFSGSGSGTDFTLTISSLQAEDVAVYYCQQYYSTPPTFGQGTKVEIK"
)
HEAVY = (
    "EVQLVESGGGLVQPGGSLRLSCAASGFSVSSKFMNWVRQAPGKGLEWVSVIYSGGSTSYADSVKGR"
    "FTISRDNSKNTLYLQMNSLRAEDTAVYYCAKGGRWYGMDVWGQGTTVTVSS"
)


def test_kappa_uses_light_cdr_ranges():
    pytest.importorskip("anarci")
    from app.cdr_annotation import annotate_antibody_chain

    light = annotate_antibody_chain(KAPPA)
    heavy = annotate_antibody_chain(HEAVY)
    assert light is not None and light["domain"] == "L"
    assert heavy is not None and heavy["domain"] == "H"
    lnames = {s["name"] for s in light["cdr_spans"]}
    hnames = {s["name"] for s in heavy["cdr_spans"]}
    assert lnames == {"CDR-L1", "CDR-L2", "CDR-L3"}
    assert hnames == {"CDR-H1", "CDR-H2", "CDR-H3"}
    l2 = next(s for s in light["cdr_spans"] if s["name"] == "CDR-L2")
    assert "WASTRES" in l2["sequence"]
    assert "GVPD" not in l2["sequence"]
