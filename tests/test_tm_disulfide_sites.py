"""可设计位点掩码（不跑 GPU / Boltz2）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from test_tm_disulfide_qc import _fasta, _write_cif
from tm_disulfide.numbering import format_kabat_number, kabat_region, number_kabat_chain
from tm_disulfide.sites import exclusion_reasons, normalize_plddt, run_site_mask

VHH = (
    "QVQLVESGGGLVQAGGSLRLSCAASGFTFSSYAMGWFRQAPGKEREFVAAISWSGGSTYYADSVKGRF"
    "TISRDNAKNTVYLQMNSLKPEDTAVYYCAADSSRRYDYWGQGTQVTVSS"
)

ONE_TO_THREE = {
    "A": "ALA", "C": "CYS", "D": "ASP", "E": "GLU", "F": "PHE", "G": "GLY",
    "H": "HIS", "I": "ILE", "K": "LYS", "L": "LEU", "M": "MET", "N": "ASN",
    "P": "PRO", "Q": "GLN", "R": "ARG", "S": "SER", "T": "THR", "V": "VAL",
    "W": "TRP", "Y": "TYR",
}


def test_kabat_region_uses_integer_position_including_insertions():
    assert kabat_region(31, "H") == "CDR-H1"
    assert kabat_region(36, "H") == "FR2"
    assert kabat_region(50, "H") == "CDR-H2"
    assert kabat_region(95, "H") == "CDR-H3"
    assert kabat_region(102, "H") == "CDR-H3"
    assert kabat_region(103, "H") == "FR4"
    assert kabat_region(24, "L") == "CDR-L1"
    assert format_kabat_number(31, "A") == "31A"
    assert format_kabat_number(100, "C") == "100C"
    assert format_kabat_number(22, " ") == "22"


def test_exclusion_reasons_keep_multiple_and_skip_glycine_missing_cb():
    gly = exclusion_reasons(
        amino_acid="G",
        kabat_number="16",
        is_cdr=False,
        present_in_all_models=True,
        has_ca_in_all_models=True,
        has_cb_in_all_models=False,
        minimum_confidence=90.0,
        ca_rmsf=0.1,
    )
    assert gly == ["glycine"]

    cdr_cys = exclusion_reasons(
        amino_acid="C",
        kabat_number="95",
        is_cdr=True,
        present_in_all_models=True,
        has_ca_in_all_models=True,
        has_cb_in_all_models=True,
        minimum_confidence=50.0,
        ca_rmsf=2.0,
    )
    assert cdr_cys == ["kabat_cdr", "native_cysteine", "low_confidence", "high_rmsf"]

    ok = exclusion_reasons(
        amino_acid="S",
        kabat_number="23",
        is_cdr=False,
        present_in_all_models=True,
        has_ca_in_all_models=True,
        has_cb_in_all_models=True,
        minimum_confidence=80.0,
        ca_rmsf=1.0,
    )
    assert ok == []


def test_normalize_plddt_accepts_unit_interval_and_percent():
    assert normalize_plddt(0.8) == 80.0
    assert normalize_plddt(81.2) == 81.2
    assert normalize_plddt(None) is None


def test_site_mask_short_peptide_is_all_unmapped(tmp_path: Path):
    sequences = {"A": "ACSGCACS"}
    folder = tmp_path / "boltz"
    folder.mkdir()
    for i in range(3):
        _write_cif(folder / f"input_model_{i}.cif", sequences)

    table = run_site_mask(_fasta(sequences), folder)
    assert table["n_residues"] == 8
    assert table["n_eligible"] == 0
    assert [row["sequence_index"] for row in table["residues"]] == list(range(1, 9))
    for row in table["residues"]:
        assert row["eligible_for_design"] is False
        assert "no_kabat_mapping" in row["exclusion_reasons"]
        assert row["eligible_for_design"] == (not row["exclusion_reasons"])
        if row["amino_acid"] == "G":
            assert "glycine" in row["exclusion_reasons"]
            assert "missing_cb" not in row["exclusion_reasons"]
        if row["amino_acid"] == "C":
            assert "native_cysteine" in row["exclusion_reasons"]


def test_kabat_numbering_vhh_insertions_and_cdr():
    hmmer = Path("/home/pengpai/data/envs/IgGM/bin/hmmscan")
    if not hmmer.is_file():
        pytest.skip("hmmscan 不可用")
    try:
        numbered = number_kabat_chain(VHH)
    except Exception as exc:
        pytest.skip(f"ANARCI 不可用: {exc}")
    if not numbered["numbered"]:
        pytest.skip("ANARCI 未能编号")

    rows = numbered["residues"]
    assert len(rows) == len(VHH)
    assert all(row["sequence_index"] == i for i, row in enumerate(rows, start=1))
    assert any(row["kabat_number"].endswith(("A", "B", "C")) for row in rows)
    cdr = [row for row in rows if row["is_cdr"]]
    fr = [row for row in rows if row["kabat_region"].startswith("FR")]
    assert cdr and fr
    assert all(row["kabat_region"].startswith("CDR") for row in cdr)
    cys = [row for row in rows if row["amino_acid"] == "C"]
    assert cys
    assert all(row["kabat_number"] for row in rows if row["kabat_region"] != "OUT")


def test_site_mask_vhh_excludes_cdr_cys_gly_pro(tmp_path: Path, monkeypatch):
    hmmer = Path("/home/pengpai/data/envs/IgGM/bin/hmmscan")
    if not hmmer.is_file():
        pytest.skip("hmmscan 不可用")
    try:
        numbered = number_kabat_chain(VHH)
    except Exception as exc:
        pytest.skip(f"ANARCI 不可用: {exc}")
    if not numbered["numbered"]:
        pytest.skip("ANARCI 未能编号")

    import test_tm_disulfide_qc as qc_test

    monkeypatch.setattr(qc_test, "ONE_TO_THREE", {**qc_test.ONE_TO_THREE, **ONE_TO_THREE}, raising=False)
    sequences = {"A": VHH}
    folder = tmp_path / "boltz"
    folder.mkdir()
    for i in range(3):
        _write_cif(folder / f"input_model_{i}.cif", sequences)
    table = run_site_mask(_fasta(sequences), folder)
    rows = table["residues"]
    assert len(rows) == len(VHH)
    assert len({(r["structure_chain"], r["sequence_index"]) for r in rows}) == len(rows)
    for row in rows:
        assert row["eligible_for_design"] == (not row["exclusion_reasons"])
        if row["is_cdr"]:
            assert row["eligible_for_design"] is False
            assert "kabat_cdr" in row["exclusion_reasons"]
        if row["is_native_cys"]:
            assert "native_cysteine" in row["exclusion_reasons"]
        if row["is_glycine"]:
            assert "glycine" in row["exclusion_reasons"]
            assert "missing_cb" not in row["exclusion_reasons"]
        if row["is_proline"]:
            assert "proline" in row["exclusion_reasons"]
        if not row["has_cb_in_all_models"] and row["amino_acid"] != "G":
            assert "missing_cb" in row["exclusion_reasons"]
    assert table["n_eligible"] == len(table["eligible_positions"])
    assert table["n_eligible"] > 0
    assert all(pos["structure_chain"] == "A" for pos in table["eligible_positions"])
