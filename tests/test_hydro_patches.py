"""疏水斑与突变枚举（不跑 GPU / Boltz2）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hydro_redesign" / "src"))


def _pdb_extended(seq: str, chain: str = "H") -> str:
    """沿 x 轴拉直的简骨架，保证表面 RSA 较高。"""
    lines = ["HEADER    HYDRO TEST"]
    serial = 1
    for i, aa in enumerate(seq, start=1):
        x = (i - 1) * 3.8
        name3 = {
            "A": "ALA",
            "S": "SER",
            "I": "ILE",
            "L": "LEU",
            "V": "VAL",
            "F": "PHE",
            "T": "THR",
            "N": "ASN",
            "Q": "GLN",
            "G": "GLY",
        }.get(aa, "ALA")
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
                f"ATOM  {serial:5d}  {aname:<3s} {name3} {chain}{i:4d}    "
                f"{x + dx:8.3f}{dy:8.3f}{dz:8.3f}  1.00 20.00           {elem:>2s}"
            )
            serial += 1
    lines.append("END")
    return "\n".join(lines) + "\n"


def test_cluster_and_enumerate(tmp_path: Path):
    gemmi = pytest.importorskip("gemmi")
    from hydro_redesign.enumerate import enumerate_mutations
    from hydro_redesign.patches import cluster_patches

    seq = "SSSSIIIIIIIIISSS"
    pdb = tmp_path / "ab.pdb"
    pdb.write_text(_pdb_extended(seq), encoding="utf-8")
    st = gemmi.read_structure(str(pdb))
    assert len(list(st[0][0])) == len(seq)

    residues, patches = cluster_patches(pdb)
    hydro_surf = [r for r in residues if r["hydrophobic"] and r["surface"] and r["patch_id"]]
    assert hydro_surf, "线性疏水段应被标为表面斑"
    assert patches
    assert all(p["n_residues"] >= 1 for p in patches)

    sequences = {"H": seq}
    regions = {( "H", i + 1): "FR" for i in range(len(seq))}
    muts, skipped = enumerate_mutations(residues, sequences, regions)
    assert muts, f"应枚举出亲水突变，skipped={skipped[:5]}"
    assert muts[0]["delta_patch"] >= muts[-1]["delta_patch"]
    assert all(m["hydro_delta"] > 0 for m in muts)
    assert all(m["mut"] in "STNQA" for m in muts)
    assert all(m["wt"] == "I" for m in muts)
    # N/C 端各 4 位冻结：Ile 从 5 起
    assert all(int(m["position"]) >= 5 for m in muts)
    wet = [m for m in muts if m["wetlab"]]
    assert wet
    assert wet[0]["rank"] == 1


def test_build_mutant_sequences_fasta():
    from hydro_redesign.sequences import (
        apply_mutation,
        build_mutant_sequences_fasta,
        select_top20_rows,
    )

    seqs = {"H": "AAAAVAAAAA", "L": "GGGGGG"}
    rows = [
        {"rank": 1, "label": "H_V5N", "chain": "H", "position": 5, "wt": "V", "mut": "N", "wetlab": True},
        {"rank": 2, "label": "H_V5Q", "chain": "H", "position": 5, "wt": "V", "mut": "Q", "wetlab": True},
    ]
    mut = apply_mutation(seqs, "H", 5, "V", "N")
    assert mut["H"] == "AAAANAAAAA"
    assert mut["L"] == "GGGGGG"
    text = build_mutant_sequences_fasta(seqs, rows)
    assert ">WT chain=H" in text
    assert ">H_V5N" in text
    assert "AAAANAAAAA" in text.replace("\n", "")
    top = select_top20_rows(rows * 3, rows[:1])
    assert len(top) == 1
    assert top[0]["label"] == "H_V5N"
