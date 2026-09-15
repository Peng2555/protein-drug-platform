"""TNP 公式（Kabat 口径）单元测试，不跑 GPU。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workflows" / "tnp_profile" / "src"))
sys.path.insert(0, str(ROOT / "workflows" / "hydro_redesign" / "src"))


def _pdb_extended(seq: str, chain: str = "H") -> str:
    lines = ["HEADER    TNP TEST"]
    serial = 1
    name3 = {
        "A": "ALA",
        "R": "ARG",
        "D": "ASP",
        "K": "LYS",
        "I": "ILE",
        "S": "SER",
        "G": "GLY",
        "E": "GLU",
        "F": "PHE",
        "Y": "TYR",
        "W": "TRP",
        "L": "LEU",
        "V": "VAL",
        "C": "CYS",
        "N": "ASN",
        "Q": "GLN",
        "H": "HIS",
        "M": "MET",
        "P": "PRO",
        "T": "THR",
    }
    for i, aa in enumerate(seq, start=1):
        x = (i - 1) * 3.8
        res = name3.get(aa, "ALA")
        atoms = [
            ("N", 0.0, 0.0, 0.0, "N"),
            ("CA", 1.5, 0.0, 0.0, "C"),
            ("C", 2.5, 1.2, 0.0, "C"),
            ("O", 3.5, 1.2, 0.0, "O"),
        ]
        if aa != "G":
            atoms.append(("CB", 1.5, -1.2, 1.1, "C"))
        if aa == "K":
            atoms.append(("NZ", 1.5, -2.4, 2.2, "N"))
        if aa == "D":
            atoms.append(("OD1", 1.5, -2.4, 2.2, "O"))
        for aname, dx, dy, dz, elem in atoms:
            lines.append(
                f"ATOM  {serial:5d}  {aname:<3s} {res} {chain}{i:4d}    "
                f"{x + dx:8.3f}{dy:8.3f}{dz:8.3f}  1.00 20.00           {elem:>2s}"
            )
            serial += 1
    lines.append("END")
    return "\n".join(lines) + "\n"


def test_kabat_length_and_tetrad():
    pytest = __import__("pytest")
    from pathlib import Path

    hmmer = Path("/home/pengpai/data/envs/IgGM/bin/hmmscan")
    if not hmmer.is_file():
        pytest.skip("hmmscan 不可用")
    from tnp_profile.numbering import annotate_kabat

    seq = (
        "QVQLVESGGGLVQAGGSLRLSCAASGFTFSSYAMGWFRQAPGKEREFVAAISWSGGSTYYADSVKGRF"
        "TISRDNAKNTVYLQMNSLKPEDTAVYYCAADSSRRYDYWGQGTQVTVSS"
    )
    ann = annotate_kabat(seq)
    assert ann["L"] > 10
    assert ann["L3"] >= 3
    assert len(ann["tetrad_motif"]) == 4
    assert ann["scheme"] == "kabat"

    from tnp_profile.hydrophobicity import scaled_hydrophobicity

    assert abs(scaled_hydrophobicity("R") - 1.0) < 1e-6
    assert abs(scaled_hydrophobicity("I") - 2.0) < 1e-6
    mid = scaled_hydrophobicity("G")
    assert 1.0 < mid < 2.0


def test_two_sided_and_ppc_flags():
    from tnp_profile.flags import assign_flag, cut_from_values

    spec = cut_from_values([10, 11, 12, 13, 14, 20, 21, 22, 23, 24], two_sided=True, integer=True)
    assert assign_flag("L", 16, spec) == "green"
    assert assign_flag("L", spec["red_lt"] - 1, spec) == "red"
    assert assign_flag("L", spec["red_gt"] + 1, spec) == "red"
    assert assign_flag("L", spec["red_gt"], spec) == "amber"
    assert assign_flag("L", spec["min"], spec) == "amber"
    ppc = cut_from_values([0.0, 0.01, 0.02, 0.1, 0.2, 0.3, 0.4, 0.9, 1.0, 1.2], two_sided=False)
    assert assign_flag("PPC", 0.05, ppc) == "green"
    assert assign_flag("PPC", ppc["red_gt"] + 0.1, ppc) == "red"
    assert assign_flag("C", 1.0, None) == "pending"
    assert assign_flag("C", 1.0, {"calibrated": False}) == "pending"


def test_tnp_integer_padding_matches_official_l():
    """官网 L：min=20 max=38 → 红 <20 或 >39，黄 20–24 与 37–39。"""
    from tnp_profile.flags import assign_flag, cut_from_values

    vals = [20] * 2 + [24] * 2 + [30] * 6 + [37] * 2 + [38] * 2
    spec = cut_from_values(vals, two_sided=True, integer=True)
    assert spec["red_lt"] == 20
    assert spec["red_gt"] == 39
    assert assign_flag("L", 19, spec) == "red"
    assert assign_flag("L", 20, spec) == "amber"
    assert assign_flag("L", 39, spec) == "amber"
    assert assign_flag("L", 40, spec) == "red"
    assert assign_flag("L", 30, spec) == "green"


def test_compactness_rho(tmp_path: Path):
    import pytest

    pytest.importorskip("gemmi")
    from tnp_profile.compactness import compactness_rho, compactness_score
    from tnp_profile.structure import load_residues

    seq = "A" * 110
    pdb = tmp_path / "nb.pdb"
    pdb.write_text(_pdb_extended(seq), encoding="utf-8")
    residues = load_residues(pdb)
    # pdb_pos 95-102 loop, 92/93/103/104 anchors
    anns = []
    for i in range(1, 111):
        anns.append(
            {
                "pdb_pos": i,
                "is_h3_loop": 95 <= i <= 102,
                "is_h3_anchor": i in (92, 93, 103, 104),
                "kabat": i,
                "insertion": "",
            }
        )
    rho = compactness_rho(residues, anns)
    assert rho is not None and rho > 0
    c = compactness_score(8, rho)
    assert c is not None and c > 0


def test_psh_pairs_same_class(tmp_path: Path):
    import pytest

    pytest.importorskip("gemmi")
    from tnp_profile.patches import patch_scores
    from tnp_profile.structure import load_residues

    seq = "I" * 40
    pdb = tmp_path / "nb.pdb"
    pdb.write_text(_pdb_extended(seq), encoding="utf-8")
    struct = load_residues(pdb)
    anns = {
        "residues": [
            {
                "seq_index": i,
                "pdb_pos": i + 1,
                "aa": "I",
                "kabat": 31 + i,
                "kabat_label": str(31 + i),
                "region": "CDR-H1",
                "vicinity_loop": "H1",
            }
            for i in range(40)
        ]
    }
    out = patch_scores(pdb, struct, anns, seq)
    assert out["PSH"] > 0
    assert out["PPC"] == 0
    assert out["n_vicinity"] >= 2


def test_parse_vhh_records_multi():
    sys.path.insert(0, str(ROOT))
    from app.modules.tnp_profile.service import parse_vhh_records

    seq = "Q" * 80
    rows = parse_vhh_records(f">a\n{seq}\n>b\n{seq}\n")
    assert [hid for hid, _ in rows] == ["a", "b"]
    assert all(len(s) == 80 for _, s in rows)
    one = parse_vhh_records(seq)
    assert one == [("H", seq)]
    mixed = parse_vhh_records(f"{seq}\n>b\n{seq}\n")
    assert [hid for hid, _ in mixed] == ["seq1", "b"]
