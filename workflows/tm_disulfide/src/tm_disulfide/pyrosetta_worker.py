#!/usr/bin/env python3
"""在 PyRosetta 环境中运行：按虚拟 SG 坐标建成共价二硫键。"""

from __future__ import annotations

import json
import math
import sys
from itertools import combinations


def _xyz(residue, atom: str):
    vec = residue.xyz(atom)
    return (float(vec.x), float(vec.y), float(vec.z))


def _dist(a, b) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def pose_index_for(pose, chain: str, sequence_index: int) -> int:
    """sequence_index → pose_index，禁止假定两者永远相等。"""
    info = pose.pdb_info()
    if info is not None:
        mapped = int(info.pdb2pose(chain, int(sequence_index)))
        if mapped != 0:
            return mapped
        count = 0
        for i in range(1, pose.total_residue() + 1):
            if str(info.chain(i)).strip() != str(chain).strip():
                continue
            if pose.residue(i).is_protein():
                count += 1
                if count == int(sequence_index):
                    return i
    count = 0
    for i in range(1, pose.total_residue() + 1):
        if pose.residue(i).is_protein():
            count += 1
            if count == int(sequence_index):
                return i
    raise ValueError(f"无法映射 {chain}:{sequence_index} 到 pose_index")


def bonded_cys_pairs(pose) -> set[tuple[int, int]]:
    """已成键的 SG 对，不按距离窗过滤。"""
    sites = [i for i in range(1, pose.total_residue() + 1) if pose.residue(i).has("SG")]
    pairs = set()
    for i, j in combinations(sites, 2):
        if pose.residue(i).is_bonded(pose.residue(j)):
            pairs.add((min(i, j), max(i, j)))
    return pairs


def disulfide_geometry_rows(pose) -> list[dict]:
    rows = []
    sites = [i for i in range(1, pose.total_residue() + 1) if pose.residue(i).has("SG")]
    for i, j in combinations(sites, 2):
        bonded = bool(pose.residue(i).is_bonded(pose.residue(j)))
        if not bonded:
            continue
        dist = _dist(_xyz(pose.residue(i), "SG"), _xyz(pose.residue(j), "SG"))
        rows.append({"pose1": i, "pose2": j, "sg_distance": round(dist, 4), "bonded": True})
    return rows


def _set_sg(pose, resid: int, xyz) -> None:
    from pyrosetta.rosetta.core.id import AtomID
    from pyrosetta.rosetta.numeric import xyzVector_double_t

    index = pose.residue(resid).atom_index("SG")
    pose.set_xyz(AtomID(index, resid), xyzVector_double_t(float(xyz[0]), float(xyz[1]), float(xyz[2])))


def _add_sg_distance_constraint(pose, pose1: int, pose2: int, ss_target: float, ss_sd: float) -> None:
    from pyrosetta.rosetta.core.id import AtomID
    from pyrosetta.rosetta.core.scoring.constraints import AtomPairConstraint
    from pyrosetta.rosetta.core.scoring.func import HarmonicFunc

    r1, r2 = pose.residue(pose1), pose.residue(pose2)
    sg1 = AtomID(r1.atom_index("SG"), pose1)
    sg2 = AtomID(r2.atom_index("SG"), pose2)
    pose.add_constraint(AtomPairConstraint(sg1, sg2, HarmonicFunc(float(ss_target), float(ss_sd))))


def _add_ss_constraints(pose, pose1: int, pose2: int, ss_target: float, ss_sd: float, angle_sd_deg: float) -> None:
    from pyrosetta.rosetta.core.id import AtomID
    from pyrosetta.rosetta.core.scoring.constraints import AngleConstraint
    from pyrosetta.rosetta.core.scoring.func import CircularHarmonicFunc

    _add_sg_distance_constraint(pose, pose1, pose2, ss_target, ss_sd)
    r1, r2 = pose.residue(pose1), pose.residue(pose2)
    sg1 = AtomID(r1.atom_index("SG"), pose1)
    sg2 = AtomID(r2.atom_index("SG"), pose2)
    cb1 = AtomID(r1.atom_index("CB"), pose1)
    cb2 = AtomID(r2.atom_index("CB"), pose2)
    angle_target = math.radians(105.0)
    angle_sd = math.radians(float(angle_sd_deg))
    pose.add_constraint(AngleConstraint(cb1, sg1, sg2, CircularHarmonicFunc(angle_target, angle_sd)))
    pose.add_constraint(AngleConstraint(sg1, sg2, cb2, CircularHarmonicFunc(angle_target, angle_sd)))


def _minimize(pose, pose1: int, pose2: int, score_function, relax_bb: bool) -> None:
    from pyrosetta.rosetta.core.kinematics import MoveMap
    from pyrosetta.rosetta.protocols.minimization_packing import MinMover

    mm = MoveMap()
    mm.set_bb(False)
    mm.set_chi(False)
    mm.set_jump(False)
    for resid in (pose1, pose2):
        mm.set_chi(resid, True)
        if relax_bb:
            mm.set_bb(resid, True)
    mover = MinMover(mm, score_function, "lbfgs_armijo_nonmonotone", 0.01, True)
    mover.max_iter(200)
    mover.apply(pose)


def _local_resids(pose, pose1: int, pose2: int, radius: float) -> list[int]:
    ca1 = pose.residue(pose1).xyz("CA")
    ca2 = pose.residue(pose2).xyz("CA")
    local = []
    for i in range(1, pose.total_residue() + 1):
        res = pose.residue(i)
        if not res.is_protein() or not res.has("CA"):
            continue
        xyz = res.xyz("CA")
        d1 = ((xyz.x - ca1.x) ** 2 + (xyz.y - ca1.y) ** 2 + (xyz.z - ca1.z) ** 2) ** 0.5
        d2 = ((xyz.x - ca2.x) ** 2 + (xyz.y - ca2.y) ** 2 + (xyz.z - ca2.z) ** 2) ** 0.5
        if min(d1, d2) <= radius:
            local.append(i)
    return local


def _pack_local(pose, local: list[int], score_function) -> None:
    from pyrosetta.rosetta.core.pack.task import TaskFactory
    from pyrosetta.rosetta.core.pack.task.operation import IncludeCurrent, RestrictToRepacking
    from pyrosetta.rosetta.protocols.minimization_packing import PackRotamersMover

    tf = TaskFactory()
    tf.push_back(RestrictToRepacking())
    tf.push_back(IncludeCurrent())
    task = tf.create_task_and_apply_taskoperations(pose)
    allowed = set(local)
    for i in range(1, pose.total_residue() + 1):
        if i not in allowed:
            task.nonconst_residue_task(i).prevent_repacking()
    mover = PackRotamersMover(score_function, task)
    mover.apply(pose)


def _minimize_local(pose, local: list[int], score_function) -> None:
    from pyrosetta.rosetta.core.kinematics import MoveMap
    from pyrosetta.rosetta.protocols.minimization_packing import MinMover

    mm = MoveMap()
    mm.set_bb(False)
    mm.set_chi(False)
    mm.set_jump(False)
    for resid in local:
        mm.set_bb(resid, True)
        mm.set_chi(resid, True)
    mover = MinMover(mm, score_function, "lbfgs_armijo_nonmonotone", 0.01, True)
    mover.max_iter(200)
    mover.apply(pose)


def relax_one(score_min, score_fa, dslf: float, job: dict) -> dict:
    import pyrosetta
    from pyrosetta.rosetta.core.scoring import ScoreType

    pose = pyrosetta.pose_from_file(job["pdb"])
    pose.conformation().detect_disulfides()
    pose1 = pose_index_for(pose, job["chain1"], int(job["seq1"]))
    pose2 = pose_index_for(pose, job["chain2"], int(job["seq2"]))
    before = bonded_cys_pairs(pose)
    radius = float(job.get("radius", 8.0))
    local = _local_resids(pose, pose1, pose2, radius)
    error = None
    try:
        score_min.set_weight(ScoreType.atom_pair_constraint, 10.0)
        ss_target = float(job.get("ss_target", 2.03))
        ss_sd = float(job.get("ss_sd", 0.08))
        for left, right in before:
            _add_sg_distance_constraint(pose, left, right, ss_target, ss_sd)
        _pack_local(pose, local, score_min)
        _minimize_local(pose, local, score_min)
        pose.conformation().detect_disulfides()
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
        try:
            pose.conformation().detect_disulfides()
        except Exception:
            pass
    after = bonded_cys_pairs(pose)
    new_pair = (min(pose1, pose2), max(pose1, pose2))
    fa_score = float(score_fa(pose))
    energies = pose.energies().total_energies()
    dslf_energy = float(energies[ScoreType.dslf_fa13])
    ref_energy = float(energies[ScoreType.ref])
    fa_rep = float(energies[ScoreType.fa_rep])
    pose.dump_pdb(job["out_pdb"])
    return {
        "id": job.get("id"),
        "error": error,
        "role": job.get("role"),
        "dslf_fa13": dslf,
        "pose1": pose1,
        "pose2": pose2,
        "fa_score": round(fa_score, 3),
        "fa_score_noref": round(fa_score - ref_energy, 3),
        "fa_rep": round(fa_rep, 3),
        "ref_energy": round(ref_energy, 3),
        "dslf_fa13_energy": round(dslf_energy, 3),
        "n_local": len(local),
        "disulfides_preserved": before <= after,
        "designed_bonded": new_pair in after,
        "n_disulfides_before": len(before),
        "n_disulfides_after": len(after),
        "out_pdb": job["out_pdb"],
        "pdb": job["pdb"],
    }


def build_one(template, score_function, dslf: float, job: dict) -> dict:
    pose = template.clone()
    chain1, seq1 = job["chain1"], int(job["seq1"])
    chain2, seq2 = job["chain2"], int(job["seq2"])
    pose1 = pose_index_for(pose, chain1, seq1)
    pose2 = pose_index_for(pose, chain2, seq2)
    aa1 = pose.residue(pose1).name1()
    aa2 = pose.residue(pose2).name1()
    native_before = bonded_cys_pairs(pose)
    reference = pose.clone()
    relax_bb = bool(job.get("relax_bb", False))
    error = None
    mover_ok = False

    from pyrosetta.rosetta.core.conformation import form_disulfide
    from pyrosetta.rosetta.core.scoring import ScoreType

    try:
        form_disulfide(pose.conformation(), pose1, pose2)
        sg1, sg2 = job.get("sg1"), job.get("sg2")
        if sg1 and sg2:
            _set_sg(pose, pose1, sg1)
            _set_sg(pose, pose2, sg2)
        score_function.set_weight(ScoreType.atom_pair_constraint, 10.0)
        score_function.set_weight(ScoreType.angle_constraint, 5.0)
        _add_ss_constraints(
            pose,
            pose1,
            pose2,
            float(job.get("ss_target", 2.03)),
            float(job.get("ss_sd", 0.08)),
            float(job.get("angle_sd", 10.0)),
        )
        _minimize(pose, pose1, pose2, score_function, relax_bb)
        pose.conformation().detect_disulfides()
        mover_ok = True
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
        try:
            pose.conformation().detect_disulfides()
        except Exception:
            pass

    native_after = bonded_cys_pairs(pose)
    new_pair = (min(pose1, pose2), max(pose1, pose2))
    preserved = native_before - {new_pair} <= native_after
    site1_is_cys = pose.residue(pose1).name3() in {"CYS", "CYD", "CYX", "CSS"} and pose.residue(pose1).has("SG")
    site2_is_cys = pose.residue(pose2).name3() in {"CYS", "CYD", "CYX", "CSS"} and pose.residue(pose2).has("SG")
    bonded = (
        bool(pose.residue(pose1).is_bonded(pose.residue(pose2))) if site1_is_cys and site2_is_cys else False
    )
    if not mover_ok:
        bonded = False
    pose.dump_pdb(job["out_pdb"])
    reference.dump_pdb(job["reference_pdb"])
    return {
        "id": job.get("id"),
        "error": error,
        "mover_ok": mover_ok,
        "dslf_fa13": dslf,
        "pose1": pose1,
        "pose2": pose2,
        "aa1": aa1,
        "aa2": aa2,
        "sequence": pose.sequence(),
        "site1_is_cys": site1_is_cys,
        "site2_is_cys": site2_is_cys,
        "new_disulfide_bonded": bonded,
        "native_before": disulfide_geometry_rows(reference),
        "native_after": disulfide_geometry_rows(pose),
        "native_disulfides_preserved": bool(preserved),
        "out_pdb": job["out_pdb"],
        "reference_pdb": job["reference_pdb"],
        "relax_bb": relax_bb,
        "n_residues": int(pose.total_residue()),
        "used_virtual_sg": bool(job.get("sg1") and job.get("sg2")),
    }


def main() -> None:
    payload = json.loads(sys.stdin.read())
    import pyrosetta
    from pyrosetta.rosetta.core.scoring import ScoreType

    pyrosetta.init("-mute all -ignore_unrecognized_res -ignore_zero_occupancy false -detect_disulf true")
    score_function = pyrosetta.get_fa_scorefxn()
    dslf = float(score_function.get_weight(ScoreType.dslf_fa13))
    if dslf <= 0:
        score_function.set_weight(ScoreType.dslf_fa13, 1.0)
        dslf = float(score_function.get_weight(ScoreType.dslf_fa13))
    task = payload.get("task") or "build"
    jobs = payload.get("jobs")
    single = False
    if not jobs:
        jobs = [payload]
        single = True

    results = []
    if task == "local_relax":
        score_fa = pyrosetta.get_fa_scorefxn()
        if float(score_fa.get_weight(ScoreType.dslf_fa13)) <= 0:
            score_fa.set_weight(ScoreType.dslf_fa13, 1.0)
        for job in jobs:
            try:
                results.append(relax_one(score_function.clone(), score_fa, dslf, job))
            except Exception as exc:  # noqa: BLE001
                results.append(
                    {
                        "id": job.get("id"),
                        "error": str(exc),
                        "role": job.get("role"),
                        "fa_score": None,
                        "disulfides_preserved": False,
                        "designed_bonded": False,
                        "out_pdb": job.get("out_pdb"),
                    }
                )
    else:
        template = pyrosetta.pose_from_file(payload["pdb"])
        template.conformation().detect_disulfides()
        for job in jobs:
            try:
                results.append(build_one(template, score_function.clone(), dslf, job))
            except Exception as exc:  # noqa: BLE001
                results.append(
                    {
                        "id": job.get("id"),
                        "error": str(exc),
                        "mover_ok": False,
                        "relax_bb": bool(job.get("relax_bb", False)),
                        "out_pdb": job.get("out_pdb"),
                        "reference_pdb": job.get("reference_pdb"),
                        "site1_is_cys": False,
                        "site2_is_cys": False,
                        "new_disulfide_bonded": False,
                        "native_disulfides_preserved": False,
                        "used_virtual_sg": bool(job.get("sg1") and job.get("sg2")),
                    }
                )
    print(json.dumps(results[0] if single else {"results": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
