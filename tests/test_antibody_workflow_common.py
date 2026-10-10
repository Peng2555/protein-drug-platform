"""抗体算法工作流公共 helper 的隔离回归测试。"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for source_root in (
    ROOT / "workflows" / "affinity_redesign" / "src",
    ROOT / "workflows" / "hydro_redesign" / "src",
    ROOT / "workflows" / "tnp_profile" / "src",
):
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))

from antibody_workflows import (
    copy_structure_input,
    export_structure_files,
    fold_antibody,
    parse_fasta,
    to_cif,
    write_csv,
    write_fasta,
)


def test_fasta_parser_and_writer_preserve_original_format(tmp_path: Path):
    text = ">H note\nac d\nEF\n\n>L\n gg \n"
    sequences = parse_fasta(text)
    assert sequences == {"H": "ACDEF", "L": "GG"}

    output = tmp_path / "nested" / "sequences.fasta"
    write_fasta(sequences, output)
    assert output.read_text(encoding="utf-8") == ">H\nACDEF\n>L\nGG\n"

    from hydro_redesign.sequences import parse_fasta as hydro_parse
    from tnp_profile.numbering import parse_fasta as tnp_parse

    assert hydro_parse is parse_fasta
    assert tnp_parse is parse_fasta


def test_csv_writer_keeps_columns_ignores_extras_and_fills_missing(tmp_path: Path):
    output = tmp_path / "nested" / "rows.csv"
    write_csv(
        output,
        [{"chain": "H", "score": 1.25, "ignored": "x"}, {"chain": "L"}],
        ["chain", "score"],
    )

    with output.open(encoding="utf-8", newline="") as handle:
        assert list(csv.DictReader(handle)) == [
            {"chain": "H", "score": "1.25"},
            {"chain": "L", "score": ""},
        ]


def test_structure_input_copy_and_cif_fallback_match_original(tmp_path: Path):
    source = tmp_path / "upload.MMCIF"
    source.write_bytes(b"not a valid structure")

    copied = copy_structure_input(source, tmp_path / "fold")
    assert copied == tmp_path / "fold" / "input.mmcif"
    assert copied.read_bytes() == source.read_bytes()

    cif_path = tmp_path / "exports" / "pred.cif"
    pdb_path = tmp_path / "exports" / "pred.pdb"
    export_structure_files(copied, cif_path, pdb_path)
    assert cif_path.read_bytes() == source.read_bytes()
    assert not pdb_path.exists()

    with pytest.raises(Exception):
        to_cif(copied, tmp_path / "strict.cif")


def test_structure_conversion_writes_cif_and_pdb_copy(tmp_path: Path):
    pytest.importorskip("gemmi")
    source = tmp_path / "input.pdb"
    source.write_text(
        "ATOM      1  CA  ALA H   1       0.000   0.000   0.000  1.00 20.00           C\n"
        "END\n",
        encoding="utf-8",
    )
    cif_path = tmp_path / "exports" / "pred.cif"
    pdb_path = tmp_path / "exports" / "pred.pdb"

    export_structure_files(source, cif_path, pdb_path)

    assert cif_path.read_text(encoding="utf-8").startswith("data_")
    assert pdb_path.read_bytes() == source.read_bytes()


def test_fold_antibody_uses_fixed_parameters_and_validates_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from affinity_redesign.tracks import boltz2

    fasta = tmp_path / "input.fasta"
    fasta.write_text(">H\nAAAA\n", encoding="utf-8")
    prediction = tmp_path / "prediction.pdb"
    prediction.write_text("END\n", encoding="utf-8")
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_fold(*args, **kwargs):
        calls.append((args, kwargs))
        return {"status": "ok", "pred_pdb": str(prediction)}

    monkeypatch.setattr(boltz2, "fold_complex", fake_fold)
    assert fold_antibody(fasta, tmp_path / "fold", "WT") == prediction
    assert calls == [
        (
            (fasta, tmp_path / "fold", "WT"),
            {
                "use_msa_server": True,
                "recycling_steps": 3,
                "sampling_steps": 200,
                "diffusion_samples": 3,
            },
        )
    ]

    monkeypatch.setattr(boltz2, "fold_complex", lambda *args, **kwargs: {"status": "failed", "error": "boom"})
    with pytest.raises(RuntimeError, match="boom"):
        fold_antibody(fasta, tmp_path / "fold")

    monkeypatch.setattr(boltz2, "fold_complex", lambda *args, **kwargs: {"status": "ok"})
    with pytest.raises(RuntimeError, match="未产出"):
        fold_antibody(fasta, tmp_path / "fold")
