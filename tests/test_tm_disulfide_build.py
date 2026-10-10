"""显式双 Cys 建模的几何验收（不强制本机有 PyRosetta）。"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from tm_disulfide.build import (
    apply_best_attempt,
    build_pass,
    cif_to_pdb,
    evaluate_built_geometry,
    select_best_attempt,
    summarize_pair_builds,
)
from tm_disulfide.geometry import virtual_sg_positions


def _add_atom(residue, name: str, xyz, element: str) -> None:
    import gemmi

    atom = gemmi.Atom()
    atom.name = name
    atom.element = gemmi.Element(element)
    atom.pos = gemmi.Position(float(xyz[0]), float(xyz[1]), float(xyz[2]))
    atom.occ = 1.0
    atom.b_iso = 40.0
    residue.add_atom(atom)


def _add_cys(chain, seq_index: int, cb, ca, nitrogen, carbon, oxygen, sg) -> None:
    import gemmi

    residue = gemmi.Residue()
    residue.name = "CYS"
    residue.seqid = gemmi.SeqId(seq_index, " ")
    _add_atom(residue, "N", nitrogen, "N")
    _add_atom(residue, "CA", ca, "C")
    _add_atom(residue, "C", carbon, "C")
    _add_atom(residue, "O", oxygen, "O")
    _add_atom(residue, "CB", cb, "C")
    _add_atom(residue, "SG", sg, "S")
    chain.add_residue(residue)


def _write_cys_pair_pdb(path: Path) -> Path:
    import gemmi

    cb1 = np.array([0.0, 0.0, 0.0])
    ca1 = np.array([0.0, 0.0, 1.54])
    sg1 = virtual_sg_positions(ca1, cb1)[0]
    cb2 = np.array([0.0, 4.0, 0.0])
    ca2 = np.array([0.0, 4.0, 1.54])
    sgs2 = virtual_sg_positions(ca2, cb2)
    sg2 = min(sgs2, key=lambda xyz: abs(float(np.linalg.norm(xyz - sg1)) - 2.03))
    structure = gemmi.Structure()
    structure.name = "cyspair"
    model = gemmi.Model("1")
    chain = gemmi.Chain("A")
    _add_cys(chain, 1, cb1, ca1, (1.2, 0.4, 2.1), (-1.1, 0.3, 2.2), (-1.8, 1.1, 2.0), sg1)
    _add_cys(chain, 2, cb2, ca2, (-1.2, 4.4, 2.1), (1.1, 3.7, 2.2), (1.8, 2.9, 2.0), sg2)
    model.add_chain(chain)
    structure.add_model(model)
    structure.write_pdb(str(path))
    return path


def test_build_pass_requires_bonded_and_ss_window():
    geom = {
        "ss_distance": 2.05,
        "chi3_deviation": 12.0,
        "clash_count": 0,
        "cb_sg1": 1.81,
        "cb_sg2": 1.81,
    }
    pyro = {
        "error": None,
        "site1_is_cys": True,
        "site2_is_cys": True,
        "new_disulfide_bonded": True,
        "native_disulfides_preserved": True,
    }
    ok, reasons = build_pass(pyro, geom)
    assert ok is True
    assert reasons == []

    pyro["new_disulfide_bonded"] = True
    geom["ss_distance"] = 3.0
    ok, reasons = build_pass(pyro, geom)
    assert ok is False
    assert "ss_distance" in reasons

    geom["ss_distance"] = 2.34
    geom["chi3_deviation"] = 44.0
    ok, reasons = build_pass(pyro, geom)
    assert ok is True

    geom["chi3_deviation"] = 50.0
    ok, reasons = build_pass(pyro, geom)
    assert ok is False
    assert "chi3" in reasons
    geom["chi3_deviation"] = 35.0

    geom["cb_sg1"] = 2.2
    ok, reasons = build_pass(pyro, geom)
    assert ok is False
    assert "cb_sg1" in reasons


def test_evaluate_built_geometry_reads_explicit_sg(tmp_path: Path):
    pdb = _write_cys_pair_pdb(tmp_path / "pair.pdb")
    geom = evaluate_built_geometry(pdb, pdb, ("A", 1), ("A", 2))
    assert 1.7 < geom["ss_distance"] < 2.4
    assert geom["clash_count"] == 0
    assert geom["global_ca_rmsd"] == 0.0


def test_summarize_pair_builds_requires_four_of_five_models():
    pair = {"pair_id": "A:1-A:10", "site1": {"sequence_index": 1}, "site2": {"sequence_index": 10}}
    models = [{"build_pass": True} for _ in range(3)] + [{"build_pass": False} for _ in range(2)]
    summary = summarize_pair_builds(pair, models)
    assert summary["n_models_passed"] == 3
    assert summary["pair_build_pass"] is False

    models[3]["build_pass"] = True
    summary = summarize_pair_builds(pair, models)
    assert summary["n_models_passed"] == 4
    assert summary["pair_build_pass"] is True


def test_select_best_attempt_keeps_closer_fixed_geometry():
    fixed = {
        "backbone_mode": "fixedbb",
        "build_pass": False,
        "failure_reasons": ["chi3"],
        "pyrosetta": {"new_disulfide_bonded": True, "native_disulfides_preserved": True},
        "geometry": {"ss_distance": 2.31},
    }
    relax = {
        "backbone_mode": "relaxbb",
        "build_pass": False,
        "failure_reasons": ["ss_distance", "chi3"],
        "pyrosetta": {"new_disulfide_bonded": True, "native_disulfides_preserved": True},
        "geometry": {"ss_distance": 2.50},
    }
    best = select_best_attempt([fixed, relax])
    assert best is fixed

    relax["build_pass"] = True
    relax["failure_reasons"] = []
    record = {"attempts": [fixed, relax]}
    apply_best_attempt(record)
    assert record["build_pass"] is True
    assert record["selected_attempt"] == "relaxbb"


def test_native_cd38_disulfide_passes_build_window(tmp_path: Path):
    import pytest

    job = Path("/home/pengpai/data/Company_Project/Boltz2/run/outputs/CD38__34a370b0")
    cif = job / "output" / "boltz_results_input" / "predictions" / "input" / "input_model_3.cif"
    if not cif.is_file():
        pytest.skip("CD38 medoid 不存在")
    pdb = cif_to_pdb(cif, tmp_path / "native.pdb")
    geom = evaluate_built_geometry(pdb, pdb, ("A", 22), ("A", 96))
    pyro = {
        "error": None,
        "site1_is_cys": True,
        "site2_is_cys": True,
        "new_disulfide_bonded": True,
        "native_disulfides_preserved": True,
    }
    ok, reasons = build_pass(pyro, geom)
    assert 1.6 <= geom["ss_distance"] <= 2.5
    assert ok is True, reasons
