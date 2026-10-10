"""Boltz2 多模型结构质控（不跑 GPU / Boltz2）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from tm_disulfide.qc import discover_boltz_models, run_structure_qc

ONE_TO_THREE = {
    "A": "ALA",
    "C": "CYS",
    "G": "GLY",
    "S": "SER",
}


def _write_cif(
    path: Path,
    sequences: dict[str, str],
    *,
    omit: dict[tuple[str, int, str], str] | None = None,
    icode: dict[tuple[str, int], str] | None = None,
    sg_shift: dict[tuple[str, int], tuple[float, float, float]] | None = None,
) -> Path:
    gemmi = pytest.importorskip("gemmi")
    omit = omit or {}
    icode = icode or {}
    sg_shift = sg_shift or {}
    structure = gemmi.Structure()
    structure.name = path.stem
    model = gemmi.Model("1")
    x_origin = 0.0
    for chain_id, seq in sequences.items():
        chain = gemmi.Chain(chain_id)
        for i, aa in enumerate(seq, start=1):
            residue = gemmi.Residue()
            residue.name = ONE_TO_THREE[aa]
            residue.seqid = gemmi.SeqId(i, icode.get((chain_id, i), " "))
            x = x_origin + (i - 1) * 3.8
            y0 = 1.2 if i % 3 == 1 else 0.0
            z0 = 1.2 if i % 3 == 2 else 0.0
            atoms = [
                ("N", 0.0, 0.0, 0.0, "N"),
                ("CA", 1.5, 0.0, 0.0, "C"),
                ("C", 2.5, 1.2, 0.0, "C"),
                ("O", 3.5, 1.2, 0.0, "O"),
            ]
            if aa != "G":
                atoms.append(("CB", 1.5, -1.2, 1.1, "C"))
            if aa == "C":
                dx, dy, dz = sg_shift.get((chain_id, i), (1.5, -2.4, 1.1))
                atoms.append(("SG", dx, dy, dz, "S"))
            for name, dx, dy, dz, elem in atoms:
                if omit.get((chain_id, i, name)):
                    continue
                atom = gemmi.Atom()
                atom.name = name
                atom.element = gemmi.Element(elem)
                atom.pos = gemmi.Position(x + dx, y0 + dy, z0 + dz)
                atom.occ = 1.0
                atom.b_iso = 80.0
                residue.add_atom(atom)
            chain.add_residue(residue)
        model.add_chain(chain)
        x_origin += len(seq) * 3.8 + 10.0
    structure.add_model(model)
    structure.make_mmcif_document().write_file(str(path))
    return path


def _fasta(sequences: dict[str, str]) -> str:
    return "".join(f">{cid}\n{seq}\n" for cid, seq in sequences.items())


def test_qc_accepts_five_matching_boltz_models(tmp_path: Path):
    sequences = {"H": "ACSGC", "L": "GAC"}
    folder = tmp_path / "boltz"
    folder.mkdir()
    paths = []
    for i in range(5):
        path = folder / f"input_model_{i}.cif"
        # 把 H2 / H5 的 SG 拉到约 2 Å，模拟已有链内二硫键。
        _write_cif(
            path,
            sequences,
            sg_shift={
                ("H", 2): (1.5, -2.4, 1.1),
                ("H", 5): (-9.9, -0.4, 1.1),
            },
        )
        paths.append(path)
    (folder / "pred_model_0.cif").write_text("data_pred\n", encoding="utf-8")

    found = discover_boltz_models(folder)
    assert [p.name for p in found] == [p.name for p in paths]

    report = run_structure_qc(_fasta(sequences), folder)
    assert report["ok"] is True
    assert report["n_models"] == 5
    assert report["errors"] == []
    assert report["fasta"] == sequences
    assert [row["sequence_index"] for row in report["residue_mapping"] if row["structure_chain"] == "H"] == [
        1,
        2,
        3,
        4,
        5,
    ]
    assert report["residue_mapping"][0]["amino_acid"] == "A"
    cys = report["cysteines"][0]
    assert [site["sequence_index"] for site in cys["sites"] if site["structure_chain"] == "H"] == [2, 5]
    intra = next(p for p in cys["sg_pairs"] if p["i"] == 2 and p["j"] == 5 and p["chain_i"] == "H")
    assert intra["likely_disulfide"] is True
    assert 1.6 <= intra["sg_distance"] <= 2.5


def test_qc_fails_when_sequence_differs(tmp_path: Path):
    good = {"A": "ACS"}
    cif = _write_cif(tmp_path / "job_model_0.cif", {"A": "ASS"})
    report = run_structure_qc(_fasta(good), [cif])
    assert report["ok"] is False
    assert any("序列与 FASTA 不一致" in msg for msg in report["errors"])


def test_qc_fails_when_backbone_or_sg_missing(tmp_path: Path):
    sequences = {"A": "ACG"}
    missing_n = _write_cif(tmp_path / "job_model_0.cif", sequences, omit={("A", 1, "N"): True})
    missing_sg = _write_cif(tmp_path / "job_model_1.cif", sequences, omit={("A", 2, "SG"): True})
    report = run_structure_qc(_fasta(sequences), [missing_n, missing_sg])
    assert report["ok"] is False
    joined = "\n".join(report["errors"])
    assert "缺原子 N" in joined
    assert "缺原子 SG" in joined


def test_qc_fails_on_insertion_code(tmp_path: Path):
    sequences = {"A": "AC"}
    cif = _write_cif(tmp_path / "job_model_0.cif", sequences, icode={("A", 2): "A"})
    report = run_structure_qc(_fasta(sequences), [cif])
    assert report["ok"] is False
    assert any("插入码" in msg for msg in report["errors"])


def test_qc_rejects_empty_fasta_or_missing_models(tmp_path: Path):
    with pytest.raises(ValueError, match="FASTA"):
        run_structure_qc("", [])
    with pytest.raises(ValueError, match="结构文件"):
        run_structure_qc(">A\nAC\n", tmp_path)
