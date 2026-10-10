"""ensemble 叠合与 CA RMSF（不跑 GPU / Boltz2）。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from test_tm_disulfide_qc import _fasta, _write_cif
from tm_disulfide.ensemble import run_ensemble_alignment


def _rigid_transform(path: Path, rotation: list[list[float]], translation: list[float]) -> None:
    gemmi = pytest.importorskip("gemmi")
    structure = gemmi.read_structure(str(path))
    transform = gemmi.Transform()
    transform.mat.fromlist(rotation)
    transform.vec.fromlist(translation)
    structure[0].transform_pos_and_adp(transform)
    structure.make_mmcif_document().write_file(str(path))


def _shift_residue_atoms(path: Path, chain_id: str, seq_index: int, delta: tuple[float, float, float]) -> None:
    gemmi = pytest.importorskip("gemmi")
    from tm_disulfide.constants import THREE_TO_ONE

    structure = gemmi.read_structure(str(path))
    dx, dy, dz = delta
    for chain in structure[0]:
        if chain.name != chain_id:
            continue
        index = 0
        for res in chain:
            if THREE_TO_ONE.get(res.name) is None:
                continue
            index += 1
            if index != seq_index:
                continue
            for atom in res:
                atom.pos = gemmi.Position(atom.pos.x + dx, atom.pos.y + dy, atom.pos.z + dz)
    structure.make_mmcif_document().write_file(str(path))


def test_ensemble_alignment_removes_rigid_motion(tmp_path: Path):
    sequences = {"H": "ACSGCA", "L": "GACS"}
    folder = tmp_path / "boltz"
    folder.mkdir()
    paths = []
    for i in range(5):
        path = folder / f"input_model_{i}.cif"
        _write_cif(path, sequences)
        paths.append(path)
    _rigid_transform(paths[1], [[0, -1, 0], [1, 0, 0], [0, 0, 1]], [20.0, 5.0, 3.0])
    _rigid_transform(paths[2], [[0, 0, 1], [0, 1, 0], [-1, 0, 0]], [-8.0, 12.0, 4.0])

    report = run_ensemble_alignment(_fasta(sequences), folder, aligned_dir=tmp_path / "aligned")
    assert report["n_models"] == 5
    assert report["n_common_ca"] == 10
    assert report["aligned_paths"]
    for row in report["transforms"]:
        assert row["rmsd_after_full_ca"] < 1e-3
        assert row["rmsd_after_core"] < 1e-3
    assert max(item["ca_rmsf"] for item in report["residues"]) < 1e-3
    # 刚体变换后的模型叠合前 RMSD 应明显大于 0。
    assert report["transforms"][1]["rmsd_before_alignment"] > 1.0


def test_medoid_is_not_always_first_model(tmp_path: Path):
    sequences = {"A": "ACSGCACS"}
    folder = tmp_path / "boltz"
    folder.mkdir()
    paths = []
    for i in range(5):
        path = folder / f"input_model_{i}.cif"
        _write_cif(path, sequences)
        paths.append(path)
    _shift_residue_atoms(paths[0], "A", 1, (3.0, 0.0, 0.0))
    _shift_residue_atoms(paths[0], "A", 2, (0.0, 3.0, 0.0))
    _shift_residue_atoms(paths[0], "A", 3, (0.0, 0.0, 3.0))

    report = run_ensemble_alignment(_fasta(sequences), folder)
    assert report["medoid_index"] != 0
    assert report["mean_pairwise_rmsd"][0] == max(report["mean_pairwise_rmsd"])


def test_core_alignment_drops_highest_rmsf_fraction(tmp_path: Path):
    sequences = {"A": "ACSGCACS"}
    folder = tmp_path / "boltz"
    folder.mkdir()
    paths = []
    for i in range(5):
        path = folder / f"input_model_{i}.cif"
        _write_cif(path, sequences)
        paths.append(path)
    _shift_residue_atoms(paths[3], "A", 8, (4.0, 0.0, 0.0))
    _shift_residue_atoms(paths[4], "A", 8, (0.0, 4.0, 0.0))

    report = run_ensemble_alignment(_fasta(sequences), folder)
    assert report["n_core_ca"] == 7
    floppy = next(row for row in report["residues"] if row["sequence_index"] == 8)
    core = [row for row in report["residues"] if row["sequence_index"] != 8]
    assert floppy["in_alignment_core"] is False
    assert floppy["ca_rmsf"] > 1.0
    assert max(row["ca_rmsf"] for row in core) < 0.2
    assert all(row["in_alignment_core"] for row in core)


def test_two_chains_are_one_rigid_body(tmp_path: Path):
    sequences = {"H": "ACSGC", "L": "GAC"}
    folder = tmp_path / "boltz"
    folder.mkdir()
    paths = []
    for i in range(5):
        path = folder / f"input_model_{i}.cif"
        _write_cif(path, sequences)
        paths.append(path)
    gemmi = pytest.importorskip("gemmi")
    from tm_disulfide.constants import THREE_TO_ONE

    structure = gemmi.read_structure(str(paths[4]))
    for chain in structure[0]:
        if chain.name != "L":
            continue
        for res in chain:
            if THREE_TO_ONE.get(res.name) is None:
                continue
            for atom in res:
                atom.pos = gemmi.Position(atom.pos.x, atom.pos.y + 20.0, atom.pos.z)
    structure.make_mmcif_document().write_file(str(paths[4]))

    report = run_ensemble_alignment(_fasta(sequences), folder)
    residues = report["residues"]
    h_rows = [row for row in residues if row["structure_chain"] == "H"]
    l_rows = [row for row in residues if row["structure_chain"] == "L"]
    medoid = report["medoid_index"]
    perturbed = 4

    def _chain_centroid(rows: list[dict], model_index: int) -> np.ndarray:
        return np.mean([row["ca_xyz"][model_index] for row in rows], axis=0)

    medoid_hl = float(np.linalg.norm(_chain_centroid(h_rows, medoid) - _chain_centroid(l_rows, medoid)))
    perturbed_hl = float(
        np.linalg.norm(_chain_centroid(h_rows, perturbed) - _chain_centroid(l_rows, perturbed))
    )
    # 分链叠合会把 H、L 各自贴到 medoid，链间距离被抹平；整体刚体应保留平移造成的链间差。
    assert abs(perturbed_hl - medoid_hl) > 5.0


def test_ensemble_requires_passing_qc(tmp_path: Path):
    sequences = {"A": "ACS"}
    cif = _write_cif(tmp_path / "job_model_0.cif", {"A": "ASS"})
    with pytest.raises(ValueError, match="结构质控未通过"):
        run_ensemble_alignment(_fasta(sequences), [cif])
