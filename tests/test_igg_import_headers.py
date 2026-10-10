"""IgG 表格表头不要求写成固定的「VH序列」。"""

from app.modules.antibody_projects.provenance import protein_and_optional_cds
from app.modules.antibody_projects.service import _locate_chain_header


def test_title_row_then_amino_acid_columns():
    matrix = [
        ["20R864 RM 25clones"],
        ["克隆编号", "VH氨基酸序列", "VL氨基酸序列"],
        ["c1", "EVQLVESGGGLVQPGGSLRLSCAASG", "DIQMTQSPSSLSASVGDRVTITCRAS"],
    ]
    header_index, name_col, vh_col, vl_col, _seq = _locate_chain_header(matrix)
    assert header_index == 1
    assert name_col == 0
    assert vh_col == 1
    assert vl_col == 2


def test_trailing_well_id_is_removed_from_sequence():
    protein, cds = protein_and_optional_cds("QVQLVESGGGLVQPGGSLRLSCAASG-012466B_")
    assert protein == "QVQLVESGGGLVQPGGSLRLSCAASG"
    assert cds is None
