"""IgG 表格表头不要求写成固定的「VH序列」。"""

from types import SimpleNamespace

from app.modules.antibody_projects.provenance import protein_and_optional_cds
from app.modules.antibody_projects.service import (
    _locate_chain_header,
    _match_version_by_protein_name,
)


def test_id_column_does_not_steal_the_sequence_column():
    matrix = [
        ["克隆编号", "重链编号", "轻链编号", "重链氨基酸序列", "轻链氨基酸序列"],
        [
            "20R864_RMBWM1AAPW4I_h1.0",
            "VH-012466B_",
            "VL-012466B_",
            "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMSWVRQAPGKGLEWVSAISGSGGSTYYADSVKGR",
            "DIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPKLLIYSASFLYSGVPSRFSGS",
        ],
    ]
    header_index, name_col, vh_col, vl_col, _seq = _locate_chain_header(matrix)
    assert header_index == 0
    assert name_col == 0
    assert vh_col == 3
    assert vl_col == 4


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


def test_well_id_is_removed_from_front_or_middle():
    body = "QVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMSWVRQ"
    leading, _cds = protein_and_optional_cds(f"-012466B_{body}")
    assert leading == body
    middle, _cds = protein_and_optional_cds(f"{body[:8]}-012466B_{body[8:]}")
    assert middle == body


def test_affinity_matches_rl_clone_code_inside_longer_names():
    target = SimpleNamespace(name="Vh1.0VKB-20R180_RLCWM1AAZ69M")
    neighbor = SimpleNamespace(name="Vh1.0VKB-20R180_RLCWM1AAZ69L")
    versions = [target, neighbor]
    assert _match_version_by_protein_name("059-20R180_RLCWM1AAZ69M_h1.0", versions) is target
    assert _match_version_by_protein_name("059-20R180_RLCWM1AAZ672_h1.0", versions) is None


def test_affinity_matches_clone_id_despite_format_prefix_and_suffix():
    ex2b = SimpleNamespace(name="Vh1$0-20R085_RNBKM1AAEX2B")
    ex22 = SimpleNamespace(name="Vh1$0-20R085_RNBKM1AAEX22")
    versions = [ex2b, ex22]
    assert _match_version_by_protein_name("004-20R085_RNBKM1AAEX2B_h1S0", versions) is ex2b
    assert _match_version_by_protein_name("008-20R232_RNBW01AAPHV9_h150", [
        SimpleNamespace(name="20R232_RNBW01AAPHV9_h150"),
    ]) is not None


def test_lone_b_inside_sequence_still_rejected():
    try:
        protein_and_optional_cds("QVQLVESGGGLVQPGGSLRLSCAASGFTFSB")
    except ValueError as exc:
        assert "B" in str(exc)
    else:
        raise AssertionError("序列中间的 B 应该报错")
