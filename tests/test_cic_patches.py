"""CIC 斑聚类（不跑 GPU）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workflows" / "cic_profile" / "src"))
sys.path.insert(0, str(ROOT / "workflows" / "hydro_redesign" / "src"))


def _pdb_extended(seq: str, chain: str = "H") -> str:
    lines = ["HEADER    CIC TEST"]
    serial = 1
    name3 = {
        "A": "ALA",
        "R": "ARG",
        "D": "ASP",
        "K": "LYS",
        "I": "ILE",
        "S": "SER",
        "G": "GLY",
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
        for aname, dx, dy, dz, elem in atoms:
            lines.append(
                f"ATOM  {serial:5d}  {aname:<3s} {res} {chain}{i:4d}    "
                f"{x + dx:8.3f}{dy:8.3f}{dz:8.3f}  1.00 20.00           {elem:>2s}"
            )
            serial += 1
    lines.append("END")
    return "\n".join(lines) + "\n"


def test_cic_charge_and_hydro_patches(tmp_path: Path):
    pytest.importorskip("gemmi")
    from cic_profile.patches import cluster_cic_patches
    from cic_profile.protonation import effective_charge

    assert effective_charge("K", 7.0) > 0.9
    assert effective_charge("D", 7.0) < -0.9
    assert effective_charge("H", 7.0) < 0.3
    assert effective_charge("H", 5.5) > 0.5

    seq = "SSSSKKKKKKKKSSSSIIIIIIII"
    pdb = tmp_path / "ab.pdb"
    pdb.write_text(_pdb_extended(seq), encoding="utf-8")
    residues, patches = cluster_cic_patches(pdb, ph=7.0)
    kinds = {p["kind"] for p in patches}
    assert "positive" in kinds
    assert "hydrophobic" in kinds
    pos = [p for p in patches if p["kind"] == "positive"]
    hyd = [p for p in patches if p["kind"] == "hydrophobic"]
    assert pos and pos[0]["n_residues"] >= 1
    assert hyd and hyd[0]["n_residues"] >= 1
    assert any(r.get("patch_id") for r in residues)
