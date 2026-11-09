"""疏水斑与突变枚举（不跑 GPU / Boltz2）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workflows" / "hydro_redesign" / "src"))


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
            "K": "LYS",
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
    assert all("sap" in r for r in residues)
    ile = next(r for r in residues if r["aa"] == "I" and r["position"] == 9)
    assert ile["sap"] >= 0.5
    assert ile["patch_id"]
    assert all(r["aa"] == "I" for r in residues if r.get("patch_id"))

    sequences = {"H": seq}
    regions = {( "H", i + 1): "FR" for i in range(len(seq))}
    muts, skipped = enumerate_mutations(residues, sequences, regions)
    assert muts, f"应枚举出亲水突变，skipped={skipped[:5]}"
    assert muts[0]["delta_patch"] >= muts[-1]["delta_patch"]
    assert all(m["hydro_delta"] > 0 for m in muts)
    assert all(m["mut"] in "STNQ" for m in muts)
    assert all(m["mut"] != "A" for m in muts)
    assert all(m["wt"] == "I" for m in muts)
    # N/C 端各 4 位冻结：Ile 从 5 起
    assert all(int(m["position"]) >= 5 for m in muts)
    wet = [m for m in muts if m["wetlab"]]
    assert wet
    assert wet[0]["rank"] == 1


def test_enumerate_uses_kabat_and_writes_sequence():
    from hydro_redesign.enumerate import enumerate_mutations

    residues = [
        {
            "chain": "H",
            "position": 9,
            "aa": "I",
            "patch_id": "P1",
            "phi": 1.2,
            "sap": 0.8,
            "rsa": 0.4,
            "sasa": 20,
        }
    ]
    seq = "SSSSIIIIIIIIISSS"
    muts, skipped = enumerate_mutations(
        residues,
        {"H": seq},
        {("H", 9): "FR"},
        kabats={("H", 9): "31A"},
    )
    assert not skipped
    assert muts
    assert muts[0]["kabat"] == "31A"
    assert muts[0]["label"].startswith("H_I31A")
    assert muts[0]["sequence"][8] == muts[0]["mut"]
    assert muts[0]["sequence"][:8] == seq[:8]


def test_sap_scale_and_hydrophilic_cancellation(tmp_path: Path):
    pytest.importorskip("gemmi")
    from hydro_redesign.constants import BLACK_MOULD_GLY0
    from hydro_redesign.patches import cluster_patches

    assert BLACK_MOULD_GLY0["G"] == 0.0
    assert BLACK_MOULD_GLY0["W"] > 0
    assert BLACK_MOULD_GLY0["Y"] > 0
    assert BLACK_MOULD_GLY0["K"] < 0

    ile_pdb = tmp_path / "ile.pdb"
    lys_pdb = tmp_path / "lys.pdb"
    ser_pdb = tmp_path / "ser.pdb"
    ile_pdb.write_text(_pdb_extended("IIIIIII"), encoding="utf-8")
    lys_pdb.write_text(_pdb_extended("IIIKIII"), encoding="utf-8")
    ser_pdb.write_text(_pdb_extended("SSSSSSS"), encoding="utf-8")

    ile_res, ile_patches = cluster_patches(ile_pdb)
    lys_res, _ = cluster_patches(lys_pdb)
    ser_res, ser_patches = cluster_patches(ser_pdb)

    ile_mid = next(r for r in ile_res if r["position"] == 4)
    lys_mid = next(r for r in lys_res if r["position"] == 4)
    assert ile_mid["aa"] == "I"
    assert lys_mid["aa"] == "K"
    assert ile_mid["sap"] > lys_mid["sap"]
    assert ile_patches
    assert not ser_patches
    assert all(float(r["sap"]) < 0.15 for r in ser_res)


def test_engineerable_patch_skips_gly_and_requires_surface(tmp_path: Path):
    pytest.importorskip("gemmi")
    from hydro_redesign.patches import cluster_patches

    pdb = tmp_path / "mix.pdb"
    pdb.write_text(_pdb_extended("IIIGIII"), encoding="utf-8")
    residues, patches = cluster_patches(pdb)
    gly = next(r for r in residues if r["aa"] == "G")
    assert gly["phi"] == 0
    assert gly["patch_id"] is None
    assert patches
    assert all(r["aa"] == "I" for r in residues if r.get("patch_id"))


def test_sap_ensemble_average(tmp_path: Path):
    pytest.importorskip("gemmi")
    from hydro_redesign.patches import cluster_patches
    from hydro_redesign.sap import discover_ensemble_structures

    seq = "SSSSIIIIIIIIISSS"
    fold_root = tmp_path / "fold"
    fold_root.mkdir()
    model0 = fold_root / "pred_model_0.pdb"
    model1 = fold_root / "pred_model_1.pdb"
    # 文件名以 pred 开头会被跳过，改用 Boltz 风格
    model0 = fold_root / "job_model_0.pdb"
    model1 = fold_root / "job_model_1.pdb"
    model0.write_text(_pdb_extended(seq), encoding="utf-8")
    model1.write_text(_pdb_extended(seq), encoding="utf-8")
    selected = tmp_path / "selected.pdb"
    selected.write_text(_pdb_extended(seq), encoding="utf-8")

    found = discover_ensemble_structures(fold_root, selected)
    assert len(found) == 2
    residues, patches = cluster_patches(selected, ensemble=found)
    assert patches
    assert all(int(r.get("sap_n") or 0) == 2 for r in residues)
    assert all(float(r.get("sap_std") or 0) == 0 for r in residues)


def test_atom_sap_uses_five_angstrom_neighborhood(tmp_path: Path):
    pytest.importorskip("gemmi")
    from hydro_redesign.sap import apply_atom_sap, hydrophobicity
    from boltzfold_shared.geometry.sasa import atom_sasa

    pdb = tmp_path / "ile.pdb"
    pdb.write_text(_pdb_extended("II"), encoding="utf-8")
    atoms = atom_sasa(pdb)
    apply_atom_sap(atoms, radius=5.0)
    xyz = [a["xyz"] for a in atoms]
    for i, atom in enumerate(atoms):
        expected = 0.0
        for j, other in enumerate(atoms):
            dist = float(((xyz[i] - xyz[j]) ** 2).sum() ** 0.5)
            if dist <= 5.0:
                expected += float(other["rsa"]) * hydrophobicity(str(other["aa"]))
        assert atom["sap"] == round(expected, 4)


def test_screen_keeps_one_glutamine_per_framework_site():
    from hydro_redesign.screen import (
        accept_verified,
        combo_header,
        fold_gate,
        mutation_header,
        render_screened_fasta,
        sap_gate,
        select_screened_sites,
    )

    rows = [
        {"chain": "H", "position": 47, "kabat": "47", "wt": "W", "mut": "Q", "region": "FR2", "patch_id": "P1", "hydro_delta": 2.6, "delta_patch": 1.9, "cdr_risk": False, "sequence": "QQQ"},
        {"chain": "H", "position": 47, "kabat": "47", "wt": "W", "mut": "N", "region": "FR2", "patch_id": "P1", "hydro_delta": 2.6, "delta_patch": 1.9, "cdr_risk": False, "sequence": "NNN"},
        {"chain": "H", "position": 59, "kabat": "58", "wt": "Y", "mut": "Q", "region": "CDR-H2", "patch_id": "P1", "hydro_delta": 2.2, "delta_patch": 1.6, "cdr_risk": True, "sequence": "YYY"},
        {"chain": "H", "position": 45, "kabat": "45", "wt": "L", "mut": "R", "region": "FR2", "patch_id": "P2", "hydro_delta": 8.3, "delta_patch": 0.8, "cdr_risk": False, "sequence": "RRR"},
    ]
    picked = select_screened_sites(rows)
    assert [row["mut"] for row in picked] == ["Q"]
    assert picked[0]["position"] == 47
    assert mutation_header("H", "W", "47", "Q") == "H_W47Q"
    assert combo_header(["H_W47Q", "H_Y58Q"]) == "H_W47Q/H_Y58Q"
    text = render_screened_fasta([("H_W47Q", "QQQ")])
    assert text == ">H_W47Q\nQQQ\n"
    assert fold_gate([{"plddt": 94.5, "drop": 0.7}], 96.1)
    assert not fold_gate([{"plddt": 68.0, "drop": 12.7}], 93.9)
    assert sap_gate(6.07, 2.67, [])
    assert not sap_gate(6.07, 2.67, [{"score": 1.2}])
    assert accept_verified({"fold_ok": True, "sap_ok": True, "binding_ok": True})
    assert not accept_verified({"fold_ok": True, "sap_ok": True, "binding_ok": False})


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
