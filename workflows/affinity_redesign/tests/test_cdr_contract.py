"""亲和力改造 CDR 公共 API 契约。"""

from __future__ import annotations

import inspect

from affinity_redesign.common.cdr import (
    KABAT_CDR_HEAVY,
    KABAT_CDR_LIGHT,
    annotate_antibody_chain,
    annotate_regions,
    region_for_index,
)


def test_cdr_public_imports_constants_and_signatures():
    assert KABAT_CDR_HEAVY == {
        "CDR-H1": (31, 35),
        "CDR-H2": (50, 65),
        "CDR-H3": (95, 102),
    }
    assert KABAT_CDR_LIGHT == {
        "CDR-L1": (24, 34),
        "CDR-L2": (50, 56),
        "CDR-L3": (89, 97),
    }
    assert list(inspect.signature(annotate_antibody_chain).parameters) == [
        "sequence",
        "anarci_python",
        "hmmer_path",
    ]
    assert list(inspect.signature(annotate_regions).parameters) == ["sequence"]
    assert list(inspect.signature(region_for_index).parameters) == ["ab", "index0"]


def test_region_for_index_boundary_contract():
    annotation = {"regions": ["FR1", "CDR-H1", "FR2"]}
    assert region_for_index(annotation, 0) == "FR1"
    assert region_for_index(annotation, 1) == "CDR-H1"
    assert region_for_index(annotation, -1) == "OUT"
    assert region_for_index(annotation, 3) == "OUT"
