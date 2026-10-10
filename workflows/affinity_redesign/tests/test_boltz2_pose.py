"""Boltz2 姿态层：iRMSD / CDR3 RMSD / 接触保留 / 多种子。"""

from pathlib import Path

from affinity_redesign.pipeline.boltz2_pose import (
    compare_mutant_to_wt,
    list_sample_structures,
)
from affinity_redesign.pipeline.rescore import recommend_row
from affinity_redesign.schemas import RescoreConfig


def _atom(serial: int, name: str, resn: str, chain: str, resi: int, x: float, y: float, z: float, b: float = 90.0) -> str:
    aname = f" {name:<3s}" if len(name) < 4 else name[:4]
    return (
        f"ATOM  {serial:5d} {aname} {resn:3s} {chain}{resi:4d}    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00{b:6.2f}           {name[0]}\n"
    )


def _write_complex(path: Path, h_z: dict[int, float]) -> None:
    """A 链抗原固定；H 链 CA 的 z 由 h_z 给出（缺省 0）。"""
    lines: list[str] = []
    n = 1
    for i in range(1, 5):
        lines.append(_atom(n, "CA", "ALA", "A", i, 0.0, (i - 1) * 3.8, 0.0))
        n += 1
        lines.append(_atom(n, "CB", "ALA", "A", i, 1.5, (i - 1) * 3.8, 0.0))
        n += 1
    # H1–H3 FR 远离界面；H4–H8 靠近抗原
    for i in range(1, 9):
        z = h_z.get(i, 0.0)
        x = 28.0 if i <= 3 else 3.5
        y = (i - 1) * 3.8
        lines.append(_atom(n, "CA", "GLY", "H", i, x, y, z, b=80.0))
        n += 1
        lines.append(_atom(n, "CB", "GLY", "H", i, x + 1.2, y, z, b=80.0))
        n += 1
    path.write_text("".join(lines) + "END\n", encoding="utf-8")


def test_compare_mutant_metrics_and_seeds(tmp_path: Path):
    wt = tmp_path / "WT.pdb"
    mut = tmp_path / "mut.pdb"
    job = tmp_path / "H_T1A"
    job.mkdir()
    pred = job / "pred.pdb"

    _write_complex(wt, {})
    # 整体平移 1Å + CDR3(H6–H8) 再抬 3Å
    mut_z = {i: 1.0 for i in range(1, 9)}
    mut_z[6] = 4.0
    mut_z[7] = 4.0
    mut_z[8] = 4.0
    _write_complex(mut, mut_z)
    _write_complex(pred, mut_z)

    for i in range(10):
        zmap = dict(mut_z) if i < 7 else {j: 8.0 for j in range(1, 9)}
        _write_complex(job / f"job_model_{i}.pdb", zmap)

    regions = {
        "H": [
            "FR-H1",
            "FR-H1",
            "FR-H1",
            "FR-H2",
            "FR-H2",
            "CDR-H3",
            "CDR-H3",
            "CDR-H3",
        ]
    }
    samples = list_sample_structures(job)
    assert len(samples) == 10
    out = compare_mutant_to_wt(
        wt,
        pred,
        ab_chains=["H"],
        ag_chain="A",
        regions_by_chain=regions,
        sample_paths=samples,
    )
    assert out["irmsd"] is not None
    assert 0.5 < out["irmsd"] < 2.5
    assert out["irmsd_band"] == "prefer"
    assert out["cdr3_rmsd"] is not None
    assert out["cdr3_rmsd"] > 2.0
    assert out["contact_retention"] is not None
    assert out["n_wt_contacts"] >= 1
    assert out["n_seeds"] == 10
    assert out["n_seed_same_mode"] == 7
    assert out["seed_stable"] == "yes"
    assert out["plddt_overall"] is not None


def test_recommend_ignores_pose_caution():
    cfg = RescoreConfig(delta_iptm_min=-0.03, max_ddg=3.0)
    keep = recommend_row(
        {
            "boltz2_status": "ok",
            "delta_iptm": 0.01,
            "ddG": 0.2,
            "tier": "B",
            "rosetta_flags": "",
            "irmsd": 6.5,
            "contact_retention": 0.2,
        },
        cfg,
    )
    assert keep[0] == "keep"
