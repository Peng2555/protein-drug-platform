"""已完成疏水斑标签：顺序位才换成 Kabat，已是 Kabat 的不再换算。"""

from app.common.kabat_results import relabel_patch_rows


def test_relabel_keeps_existing_kabat_and_converts_sequential():
    residues = [
        {"chain": "H", "position": "89", "aa": "D", "kabat": "86"},
        {"chain": "H", "position": "92", "aa": "V", "kabat": "89"},
        {"chain": "H", "position": "33", "aa": "Y", "kabat": "33"},
    ]
    patches = [{"residues": ["H:V89", "H:Y33", "H:V92", "H:Y100C"]}]
    relabel_patch_rows(patches, residues)
    assert patches[0]["residues"] == ["H:V89", "H:Y33", "H:V89", "H:Y100C"]
