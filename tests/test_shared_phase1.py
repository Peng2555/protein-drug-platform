"""Runner/算法重构第 1 阶段的共享包契约。"""

from __future__ import annotations

import importlib
import sys


def test_legacy_modules_are_thin_shared_reexports():
    from affinity_redesign.common import cdr as legacy_cdr
    from antibody_workflows import fasta as legacy_fasta
    from antibody_workflows import files as legacy_files
    from antibody_workflows import structures as legacy_structures
    from boltzfold_shared.antibody import cdr
    from boltzfold_shared.io import fasta, files, structures
    from boltzfold_shared.geometry import sasa
    from hydro_redesign import sasa as legacy_sasa

    assert legacy_cdr.annotate_antibody_chain is cdr.annotate_antibody_chain
    assert legacy_cdr.region_for_index is cdr.region_for_index
    assert legacy_fasta.parse_fasta is fasta.parse_fasta
    assert legacy_files.write_csv is files.write_csv
    assert legacy_structures.export_structure_files is structures.export_structure_files
    assert legacy_sasa.residue_sasa is sasa.residue_sasa


def test_shared_cdr_builds_same_stable_regions_via_legacy_path():
    from affinity_redesign.common.cdr import region_for_index as legacy_region_for_index
    from boltzfold_shared.antibody.cdr import _build_annotation, region_for_index

    numbering = [((position, " "), "A") for position in range(1, 111)]
    annotation = _build_annotation("A" * 110, numbering, 0, 109, "H")

    assert annotation["cdr_spans"] == [
        {"name": "CDR-H1", "start": 30, "end": 34, "sequence": "AAAAA"},
        {"name": "CDR-H2", "start": 49, "end": 64, "sequence": "A" * 16},
        {"name": "CDR-H3", "start": 94, "end": 101, "sequence": "A" * 8},
    ]
    assert [legacy_region_for_index(annotation, i) for i in range(110)] == [
        region_for_index(annotation, i) for i in range(110)
    ]
    assert region_for_index(annotation, 30) == "CDR-H1"
    assert region_for_index(annotation, 35) == "FR2"


def test_algorithm_imports_do_not_load_affinity_config():
    for name in list(sys.modules):
        if name.startswith(("hydro_redesign", "cic_profile", "tnp_profile", "affinity_redesign.config")):
            sys.modules.pop(name, None)

    importlib.import_module("hydro_redesign.workflow")
    importlib.import_module("cic_profile.workflow")
    importlib.import_module("tnp_profile.workflow")

    assert "affinity_redesign.config" not in sys.modules


def test_tnp_hmmer_uses_shared_runtime_settings(monkeypatch):
    import tnp_profile.numbering as numbering
    from boltzfold_shared.runtime.settings import settings

    assert numbering.settings is settings
