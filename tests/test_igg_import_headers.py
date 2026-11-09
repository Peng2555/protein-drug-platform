"""IgG 表格表头不要求写成固定的「VH序列」。"""

from types import SimpleNamespace

from app.modules.antibody_projects.provenance import protein_and_optional_cds
from app.modules.antibody_projects.service import (
    _locate_chain_header,
    _locate_physchem_sheet,
    _match_version_by_protein_name,
    _parse_physchem_number,
    _physchem_measurements,
    _read_physchem_rows,
)
from app.schemas.antibody_project import PhyschemImportItem


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


def test_physchem_sheet_reads_sample_and_metric_columns():
    located = _locate_physchem_sheet([
        ("理化", [
            ["样品", "SEC单体%", "HIC保留时间", "Tm", "pI"],
            ["059-20R180_RLCWM1AAZ69M_h1.0", "96.2", "8.4", "68.1", "8.7"],
        ]),
    ])
    assert located is not None
    _name, _matrix, header_index, sample_col, metrics = located
    assert header_index == 0
    assert sample_col == 0
    assert metrics == {"SEC_monomer": 1, "HIC_RT": 2, "Tm1": 3, "pI": 4}


def test_physchem_protein_column_and_wrapped_clone_id():
    protein = "20R101_RL\nBWM2AAC\nJCX_h1.0P\n260910S011"
    names, rows = _read_physchem_rows([
        ("HIC", [
            ["No.", "Protein", "HIC(1)\n(min)", "Conclusion", "Risk"],
            ["1", protein, "13.705", "Aggregation", ""],
        ]),
    ])
    assert names == ["HIC"]
    assert len(rows) == 1
    assert rows[0]["loading_sample_id"] == "20R101_RLBWM2AACJCX_h1.0P260910S011"
    assert rows[0]["values"]["hic_rt"] == 13.705
    assert rows[0]["values"]["sec_monomer"] is None
    version = SimpleNamespace(name="Vh1.0-20R101_RLBWM2AACJCX")
    assert _match_version_by_protein_name(rows[0]["protein_key"], [version]) is version


def test_physchem_sheets_merge_by_clone_code():
    protein = "20R101_RLBWM2AACJCX_h1.0P260910S011"
    names, rows = _read_physchem_rows([
        ("HIC", [
            ["Protein", "HIC(1) (min)"],
            [protein, "13.705"],
        ]),
        ("SEC", [
            ["Protein", "SEC单体%"],
            ["20R101_RLBWM2AACJCX_h1.0", "96.2"],
        ]),
        ("Tm", [
            ["蛋白", "Tm", "pI"],
            [protein, "68.1", "8.4"],
        ]),
    ])
    assert names == ["HIC", "SEC", "Tm"]
    assert len(rows) == 1
    assert rows[0]["values"]["sec_monomer"] == 96.2
    assert rows[0]["values"]["hic_rt"] == 13.705
    assert rows[0]["values"]["tm1"] == 68.1
    assert rows[0]["values"]["pi"] == 8.4
    assert rows[0]["values"]["tm2"] is None
    assert rows[0]["values"]["tagg"] is None


def test_partial_tm_row_is_enough_to_import():
    assert _parse_physchem_number("61.95°C") == 61.95
    assert _parse_physchem_number("NA") is None
    item = PhyschemImportItem(
        excel_row=3,
        version_id="version-1",
        loading_sample_id="20R232_RNBWM1AAPHWC_h1S0",
        tm1=61.95,
        tm2=69.28,
        tagg=65.25,
    )
    names = [row.metric_name for row in _physchem_measurements(item)]
    assert names == ["Tm1", "Tm2", "Tagg"]
    empty = PhyschemImportItem(
        excel_row=4,
        version_id="version-1",
        loading_sample_id="blank",
    )
    assert _physchem_measurements(empty) == []


def test_tm_subheader_keeps_tm1_tm2_and_tagg():
    protein = "20R232_R\nNBWM1A\nAPHWC_h\n1S0(P2609\n20801)"
    _names, rows = _read_physchem_rows([
        ("Tm", [
            ["No.", "Protein", "Tm", "", "", "Conclusion", "Risk"],
            ["", "", "Tm1", "Tm2", "Tagg 266", "", ""],
            ["1", protein, "61.95", "69.28", "65.25", "NA", ""],
        ]),
    ])
    assert len(rows) == 1
    assert rows[0]["values"]["tm1"] == 61.95
    assert rows[0]["values"]["tm2"] == 69.28
    assert rows[0]["values"]["tagg"] == 65.25


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
