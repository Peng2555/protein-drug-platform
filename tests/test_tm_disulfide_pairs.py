"""残基对 CA/CB 距离粗筛（不跑 GPU / Boltz2）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from tm_disulfide.constants import MINIMUM_SEQUENCE_SEPARATION
from tm_disulfide.pairs import facing_metrics, screen_pairs, sequence_separation


def _site(chain: str, index: int, aa: str = "A") -> dict:
    return {
        "structure_chain": chain,
        "sequence_index": index,
        "amino_acid": aa,
        "kabat_number": str(index),
    }


def _write_two_chain_cif(
    path: Path,
    *,
    l_y: float = 4.0,
    omit_cb: tuple[str, int] | None = None,
    facing: bool = True,
) -> Path:
    gemmi = pytest.importorskip("gemmi")
    structure = gemmi.Structure()
    structure.name = path.stem
    model = gemmi.Model("1")
    for chain_id, y0 in (("H", 0.0), ("L", l_y)):
        chain = gemmi.Chain(chain_id)
        for i, aa in enumerate("AAAAA", start=1):
            residue = gemmi.Residue()
            residue.name = "ALA"
            residue.seqid = gemmi.SeqId(i, " ")
            x = (i - 1) * 3.8
            if facing:
                cb_dy = 1.2 if chain_id == "H" else -1.2
            else:
                cb_dy = -1.2
            atoms = [
                ("N", 0.0, 0.0, 0.0, "N"),
                ("CA", 1.5, 0.0, 0.0, "C"),
                ("C", 2.5, 1.2, 0.0, "C"),
                ("O", 3.5, 1.2, 0.0, "O"),
                ("CB", 1.5, cb_dy, 0.0, "C"),
            ]
            for name, dx, dy, dz, elem in atoms:
                if omit_cb == (chain_id, i) and name == "CB":
                    continue
                atom = gemmi.Atom()
                atom.name = name
                atom.element = gemmi.Element(elem)
                atom.pos = gemmi.Position(x + dx, y0 + dy, dz)
                atom.occ = 1.0
                atom.b_iso = 90.0
                residue.add_atom(atom)
            chain.add_residue(residue)
        model.add_chain(chain)
    structure.add_model(model)
    structure.make_mmcif_document().write_file(str(path))
    return path


def test_sequence_separation_same_chain_only():
    a = _site("H", 5)
    b = _site("H", 16)
    c = _site("L", 16)
    assert sequence_separation(a, b) == 11
    assert sequence_separation(a, c) is None
    assert sequence_separation(a, a) == 0


def test_screen_pairs_counts_and_filters(tmp_path: Path):
    paths = []
    for i in range(5):
        paths.append(_write_two_chain_cif(tmp_path / f"input_model_{i}.cif"))
    eligible = [_site("H", i) for i in (1, 2, 5)] + [_site("L", 1), _site("L", 5)]
    n = len(eligible)
    report = screen_pairs(paths, eligible)
    assert report["n_eligible"] == n
    assert report["n_combinations"] == n * (n - 1) // 2
    assert report["n_close_sequence"] >= 1
    ids = [row["pair_id"] for row in report["pairs"]]
    assert len(ids) == len(set(ids))
    assert all("H:2-H:1" not in pair_id for pair_id in ids)
    inter = next(row for row in report["pairs"] if row["pair_id"] == "H:1-L:1")
    assert inter["sequence_separation"] is None
    assert inter["n_models_passed"] == 5
    assert inter["ca"]["mean"] < 7.0
    assert inter["cb"]["mean"] < 6.0
    assert inter["facing"]["ca_cb_dot"]["mean"] <= 0.0
    assert all(m["toward_angle_1"] <= 90.0 and m["toward_angle_2"] <= 90.0 for m in inter["models"])
    same_far = [row for row in report["pairs"] if row["pair_id"] == "H:1-H:5"]
    assert same_far == []
    for row in report["pairs"]:
        s1, s2 = row["site1"], row["site2"]
        assert (s1["structure_chain"], s1["sequence_index"]) < (s2["structure_chain"], s2["sequence_index"])
        assert len(row["models"]) == 5
        assert all(m["ca"] == m["ca"] and m["cb"] == m["cb"] for m in row["models"])


def test_screen_pairs_requires_four_of_five(tmp_path: Path):
    paths = []
    for i in range(5):
        y = 4.0 if i < 4 else 7.5
        paths.append(_write_two_chain_cif(tmp_path / f"input_model_{i}.cif", l_y=y))
    eligible = [_site("H", 1), _site("L", 1)]
    four = screen_pairs(paths, eligible)
    assert four["n_passed"] == 1
    assert four["pairs"][0]["n_models_passed"] == 4

    paths3 = []
    for i in range(5):
        y = 4.0 if i < 3 else 7.5
        paths3.append(_write_two_chain_cif(tmp_path / f"far_{i}.cif", l_y=y))
    three = screen_pairs(paths3, eligible)
    assert three["n_combinations"] == 1
    assert three["n_passed"] == 0

    outlier = []
    for i in range(5):
        y = 4.0 if i < 4 else 20.0
        outlier.append(_write_two_chain_cif(tmp_path / f"out_{i}.cif", l_y=y))
    assert screen_pairs(outlier, eligible)["n_passed"] == 0


def test_screen_pairs_rejects_missing_cb(tmp_path: Path):
    paths = [
        _write_two_chain_cif(tmp_path / "input_model_0.cif"),
        _write_two_chain_cif(tmp_path / "input_model_1.cif"),
        _write_two_chain_cif(tmp_path / "input_model_2.cif", omit_cb=("L", 1)),
        _write_two_chain_cif(tmp_path / "input_model_3.cif"),
        _write_two_chain_cif(tmp_path / "input_model_4.cif"),
    ]
    with pytest.raises(ValueError, match="缺 CB"):
        screen_pairs(paths, [_site("H", 1), _site("L", 1)])


def test_screen_pairs_rejects_parallel_sidechains(tmp_path: Path):
    paths = [_write_two_chain_cif(tmp_path / f"input_model_{i}.cif", facing=False) for i in range(5)]
    report = screen_pairs(paths, [_site("H", 1), _site("L", 1)])
    assert report["n_passed"] == 0


def test_facing_metrics_opposite_versus_parallel():
    import numpy as np

    ca1 = np.array([0.0, 0.0, 0.0])
    cb1 = np.array([0.0, 1.0, 0.0])
    ca2 = np.array([0.0, 4.0, 0.0])
    cb2_face = np.array([0.0, 3.0, 0.0])
    cb2_same = np.array([0.0, 5.0, 0.0])
    good = facing_metrics(ca1, cb1, ca2, cb2_face)
    assert good["pass"] is True
    assert good["toward_angle_1"] < 5.0
    assert good["toward_angle_2"] < 5.0
    assert good["ca_cb_dot"] < 0.0
    bad = facing_metrics(ca1, cb1, ca2, cb2_same)
    assert bad["pass"] is False
    assert "cb_not_toward" in bad["reasons"] or "cb_not_antiparallel" in bad["reasons"]


def test_minimum_sequence_separation_is_configured():
    assert MINIMUM_SEQUENCE_SEPARATION == 8
