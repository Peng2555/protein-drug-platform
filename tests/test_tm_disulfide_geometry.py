"""虚拟 Cys SG 几何搜索（不跑 GPU / PyRosetta）。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tm_disulfide.constants import CA_CB_SG_ANGLE, CB_SG_BOND_LENGTH, SG_ROTATION_STEP
from tm_disulfide.geometry import (
    bond_angle,
    circular_difference,
    evaluate_pair_on_structures,
    search_sg_conformers,
    virtual_sg_positions,
)


def test_circular_difference_wraps_around_180():
    assert circular_difference(180.0, -180.0) == pytest.approx(0.0)
    assert circular_difference(-87.0, 97.0) == pytest.approx(176.0)
    assert circular_difference(10.0, -10.0) == pytest.approx(20.0)


def test_virtual_sg_matches_cys_bond_geometry():
    ca = np.array([0.0, 0.0, 1.54])
    cb = np.array([0.0, 0.0, 0.0])
    sgs = virtual_sg_positions(ca, cb)
    assert sgs.shape[0] == int(360 / SG_ROTATION_STEP)
    lengths = np.linalg.norm(sgs - cb, axis=1)
    assert np.allclose(lengths, CB_SG_BOND_LENGTH, atol=1e-6)
    angles = [bond_angle(ca, cb, sg) for sg in sgs]
    assert np.allclose(angles, CA_CB_SG_ANGLE, atol=1e-4)


def _add_atom(residue, name: str, xyz, element: str) -> None:
    import gemmi

    atom = gemmi.Atom()
    atom.name = name
    atom.element = gemmi.Element(element)
    atom.pos = gemmi.Position(float(xyz[0]), float(xyz[1]), float(xyz[2]))
    atom.occ = 1.0
    atom.b_iso = 90.0
    residue.add_atom(atom)


def _add_residue(chain, seq_index: int, cb, ca, nitrogen, carbon, oxygen) -> None:
    import gemmi

    residue = gemmi.Residue()
    residue.name = "ALA"
    residue.seqid = gemmi.SeqId(seq_index, " ")
    _add_atom(residue, "N", nitrogen, "N")
    _add_atom(residue, "CA", ca, "C")
    _add_atom(residue, "C", carbon, "C")
    _add_atom(residue, "O", oxygen, "O")
    _add_atom(residue, "CB", cb, "C")
    chain.add_residue(residue)


def _write_pair_cif(path: Path, cb2_y: float = 4.0) -> Path:
    import gemmi

    structure = gemmi.Structure()
    structure.name = path.stem
    model = gemmi.Model("1")
    chain = gemmi.Chain("A")
    _add_residue(
        chain,
        1,
        cb=(0.0, 0.0, 0.0),
        ca=(0.0, 0.0, 1.54),
        nitrogen=(1.2, 0.4, 2.1),
        carbon=(-1.1, 0.3, 2.2),
        oxygen=(-1.8, 1.1, 2.0),
    )
    _add_residue(
        chain,
        10,
        cb=(0.0, cb2_y, 0.0),
        ca=(0.0, cb2_y, 1.54),
        nitrogen=(-1.2, cb2_y + 0.4, 2.1),
        carbon=(1.1, cb2_y - 0.3, 2.2),
        oxygen=(1.8, cb2_y - 1.1, 2.0),
    )
    model.add_chain(chain)
    structure.add_model(model)
    structure.make_mmcif_document().write_file(str(path))
    return path


def test_search_finds_geometry_for_close_cb_pair(tmp_path: Path):
    path = _write_pair_cif(tmp_path / "pair.cif", cb2_y=4.0)
    import gemmi

    from tm_disulfide.geometry import extract_pair_frames

    extracted = extract_pair_frames(gemmi.read_structure(str(path)), ("A", 1), ("A", 2))
    result = search_sg_conformers(
        extracted["frames"][("A", 1)],
        extracted["frames"][("A", 2)],
        extracted["env"],
    )
    assert result["n_total"] == 72 * 72
    assert result["n_ss"] > 0
    assert result["geometry_pass"] is True
    assert result["best"]["ss"] >= 1.8
    assert result["best"]["ss"] <= 2.3
    assert result["n_clash_free"] >= 1


def test_far_cb_pair_has_no_ss_window(tmp_path: Path):
    path = _write_pair_cif(tmp_path / "far.cif", cb2_y=12.0)
    import gemmi

    from tm_disulfide.geometry import extract_pair_frames

    extracted = extract_pair_frames(gemmi.read_structure(str(path)), ("A", 1), ("A", 2))
    result = search_sg_conformers(
        extracted["frames"][("A", 1)],
        extracted["frames"][("A", 2)],
        extracted["env"],
    )
    assert result["n_ss"] == 0
    assert result["geometry_pass"] is False
    assert "no_ss_distance" in result["failure_reasons"]


def test_evaluate_pair_requires_four_of_five_models(tmp_path: Path):
    paths = []
    for i in range(5):
        y = 4.0 if i < 4 else 12.0
        paths.append(_write_pair_cif(tmp_path / f"input_model_{i}.cif", cb2_y=y))
    four = evaluate_pair_on_structures(paths, ("A", 1), ("A", 2))
    assert four["n_models_passed"] == 4
    assert four["pair_geometry_pass"] is True

    far = [_write_pair_cif(tmp_path / f"far_{i}.cif", cb2_y=12.0) for i in range(5)]
    none = evaluate_pair_on_structures(far, ("A", 1), ("A", 2))
    assert none["pair_geometry_pass"] is False


def test_native_cd38_disulfide_is_recoverable():
    job = Path("/home/pengpai/data/Company_Project/Boltz2/run/outputs/CD38__34a370b0")
    pred = job / "output" / "boltz_results_input" / "predictions" / "input"
    if not pred.is_dir():
        pytest.skip("CD38 预测目录不存在")
    from tm_disulfide.qc import discover_boltz_models

    paths = discover_boltz_models(pred)
    if len(paths) < 5:
        pytest.skip("CD38 模型不足 5 套")
    report = evaluate_pair_on_structures(paths, ("A", 22), ("A", 96))
    assert report["pair_geometry_pass"] is True
    assert report["n_models_passed"] >= 4
    assert report["models"][0]["best"]["ss"] < 2.3
