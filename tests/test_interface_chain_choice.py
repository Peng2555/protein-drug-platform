"""结合界面应分析抗体与靶点，抗体残基使用 Kabat 编号。"""

from app.modules.fold.interface import _apply_kabat_numbers, _merge_antibody_target_interface


def test_primary_interface_is_antibody_against_target():
    roles = {
        "H": {"role": "antibody", "is_antibody": True},
        "L": {"role": "antibody", "is_antibody": True},
        "A": {"role": "target", "is_antibody": False},
    }
    interfaces = [
        {
            "chain_a": "H",
            "chain_b": "L",
            "contact_pairs": 40,
            "pdockq": 0.8,
            "residues_a": [{"chain_id": "H", "seq_num": 1, "resname": "TYR"}],
            "residues_b": [{"chain_id": "L", "seq_num": 2, "resname": "SER"}],
        },
        {
            "chain_a": "H",
            "chain_b": "A",
            "contact_pairs": 12,
            "pdockq": 0.4,
            "residues_a": [{"chain_id": "H", "seq_num": 50, "resname": "TRP"}],
            "residues_b": [{"chain_id": "A", "seq_num": 10, "resname": "GLU"}],
        },
        {
            "chain_a": "L",
            "chain_b": "A",
            "contact_pairs": 8,
            "pdockq": 0.3,
            "residues_a": [{"chain_id": "L", "seq_num": 30, "resname": "ASN"}],
            "residues_b": [{"chain_id": "A", "seq_num": 11, "resname": "LYS"}],
        },
    ]
    primary = _merge_antibody_target_interface(interfaces, roles, ["H", "L"], ["A"])
    assert primary is not None
    assert primary["label_a"] == "靶点 A"
    assert primary["label_b"] == "抗体 H+L"
    assert primary["contact_pairs"] == 20
    assert {item["chain_id"] for item in primary["residues_a"]} == {"A"}
    assert {item["chain_id"] for item in primary["residues_b"]} == {"H", "L"}


def test_antibody_interface_numbers_use_kabat():
    primary = {
        "residues_a": [{"chain_id": "C", "seq_num": 80, "resname": "LEU"}],
        "residues_b": [{"chain_id": "A", "seq_num": 106, "resname": "TYR"}],
        "interactions": [
            {"chain_a": "C", "resnum_a": 177, "chain_b": "A", "resnum_b": 52},
        ],
    }
    _apply_kabat_numbers(primary, {("A", 106): "100C", ("A", 52): "52"})
    assert "kabat" not in primary["residues_a"][0]
    assert primary["residues_b"][0]["kabat"] == "100C"
    assert "kabat_a" not in primary["interactions"][0]
    assert primary["interactions"][0]["kabat_b"] == "52"
