"""Boltz2 姿态层：相对 WT 的 iRMSD / CDR RMSD / 接触保留 / 多种子一致性。

置信度（ipTM 等）在 fold 阶段按 10 次中位数汇总；本模块只比较结构。
默认用「ipTM 最高」的代表结构 vs WT 代表结构；种子一致性再扫各 sample。
标签只作着色，不在此做 hard drop。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

CONTACT_CUTOFF = 4.5  # 残基对，最小重原子距离 (Å)
INTERFACE_CA_CUTOFF = 10.0  # iRMSD 界面：抗体 CA 距抗原 CA
IRMSD_PREFER = 3.0
IRMSD_CAUTION = 5.0
SEED_IRMSD_CUT = 3.0
SEED_STABLE_FRAC = 0.7  # ≥7/10
RETENTION_PREFER = 0.70
RETENTION_CAUTION = 0.50
DELTA_IPTM_SEVERE = -0.05


@dataclass
class Residue:
    chain: str
    seqid: int
    name: str
    ca: np.ndarray | None
    heavy: np.ndarray
    plddt: float | None


@dataclass
class Structure:
    residues: list[Residue] = field(default_factory=list)

    def by_chain(self) -> dict[str, list[Residue]]:
        out: dict[str, list[Residue]] = {}
        for r in self.residues:
            out.setdefault(r.chain, []).append(r)
        return out

    def lookup(self) -> dict[tuple[str, int], Residue]:
        return {(r.chain, r.seqid): r for r in self.residues}


def _rmsd(a: np.ndarray, b: np.ndarray) -> float:
    diff = a - b
    return float(np.sqrt((diff * diff).sum() / max(len(a), 1)))


def load_pdb(path: Path) -> Structure:
    residues: dict[tuple[str, int], Residue] = {}
    heavies: dict[tuple[str, int], list[np.ndarray]] = {}
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.startswith(("ATOM", "HETATM")) or len(line) < 54:
                continue
            name = line[12:16].strip()
            resname = line[17:20].strip()
            chain = (line[21].strip() or "A")
            try:
                seqid = int(line[22:26])
            except ValueError:
                continue
            try:
                x, y, z = float(line[30:38]), float(line[38:46]), float(line[46:54])
            except ValueError:
                continue
            elem = (line[76:78].strip() if len(line) >= 78 else name[:1]).upper()
            if elem == "H" or name.startswith("H"):
                continue
            key = (chain, seqid)
            xyz = np.array([x, y, z], dtype=float)
            bfac = None
            if len(line) >= 66:
                try:
                    bfac = float(line[60:66])
                except ValueError:
                    bfac = None
            heavies.setdefault(key, []).append(xyz)
            rec = residues.get(key)
            if rec is None:
                residues[key] = Residue(
                    chain=chain,
                    seqid=seqid,
                    name=resname,
                    ca=xyz.copy() if name == "CA" else None,
                    heavy=np.zeros((0, 3)),
                    plddt=bfac if name == "CA" else None,
                )
            else:
                if name == "CA":
                    rec.ca = xyz.copy()
                    if bfac is not None:
                        rec.plddt = bfac
    out = Structure()
    for key, res in sorted(residues.items()):
        arr = np.stack(heavies[key], axis=0) if heavies.get(key) else np.zeros((0, 3))
        res.heavy = arr
        out.residues.append(res)
    return out


def load_structure(path: Path) -> Structure:
    suf = path.suffix.lower()
    if suf in {".cif", ".mmcif"}:
        try:
            return _load_gemmi(path)
        except Exception:
            raise
    return load_pdb(path)


def _load_gemmi(path: Path) -> Structure:
    import gemmi

    st = gemmi.read_structure(str(path))
    out = Structure()
    if not st:
        return out
    model = st[0]
    for chain in model:
        cid = chain.name or "A"
        for res in chain:
            if res.is_water():
                continue
            heavies: list[np.ndarray] = []
            ca = None
            plddt = None
            try:
                seqid = int(res.seqid.num)
            except (TypeError, ValueError):
                continue
            for atom in res:
                if atom.is_hydrogen():
                    continue
                pos = np.array([atom.pos.x, atom.pos.y, atom.pos.z], dtype=float)
                heavies.append(pos)
                if atom.name == "CA":
                    ca = pos.copy()
                    plddt = float(atom.b_iso)
            if not heavies:
                continue
            out.residues.append(
                Residue(
                    chain=cid,
                    seqid=seqid,
                    name=res.name,
                    ca=ca,
                    heavy=np.stack(heavies, axis=0),
                    plddt=plddt,
                )
            )
    return out


def _paired_ca(a: list[Residue], b: list[Residue]) -> tuple[np.ndarray, np.ndarray] | None:
    lb = {r.seqid: r for r in b if r.ca is not None}
    pa, pb = [], []
    for ra in a:
        rb = lb.get(ra.seqid)
        if ra.ca is None or rb is None or rb.ca is None:
            continue
        pa.append(ra.ca)
        pb.append(rb.ca)
    if len(pa) < 3:
        return None
    return np.stack(pa), np.stack(pb)


def interface_ab_residues(
    st: Structure,
    ab_chains: list[str],
    ag_chain: str,
    cutoff: float = INTERFACE_CA_CUTOFF,
) -> list[Residue]:
    by = st.by_chain()
    ag = [r for r in by.get(ag_chain, []) if r.ca is not None]
    if not ag:
        return []
    ag_ca = np.stack([r.ca for r in ag], axis=0)
    hits: list[Residue] = []
    for cid in ab_chains:
        for r in by.get(cid, []):
            if r.ca is None:
                continue
            d = np.linalg.norm(ag_ca - r.ca, axis=1).min()
            if d <= cutoff:
                hits.append(r)
    return hits


def irmsd_vs_wt(
    wt: Structure,
    mut: Structure,
    ab_chains: list[str],
    ag_chain: str,
) -> float | None:
    """抗原 CA 对齐后，WT 界面抗体 CA 的 RMSD。"""
    wt_ag = [r for r in wt.by_chain().get(ag_chain, []) if r.ca is not None]
    mut_ag = [r for r in mut.by_chain().get(ag_chain, []) if r.ca is not None]
    pair_ag = _paired_ca(wt_ag, mut_ag)
    if pair_ag is None:
        return None
    wt_ifc = interface_ab_residues(wt, ab_chains, ag_chain)
    mut_lu = mut.lookup()
    wt_pts, mut_pts = [], []
    for r in wt_ifc:
        m = mut_lu.get((r.chain, r.seqid))
        if r.ca is None or m is None or m.ca is None:
            continue
        wt_pts.append(r.ca)
        mut_pts.append(m.ca)
    if len(wt_pts) < 3:
        return None
    r, t = _rotation_translation(pair_ag[1], pair_ag[0])
    mut_ifc = np.stack(mut_pts) @ r.T + t
    return round(_rmsd(mut_ifc, np.stack(wt_pts)), 4)


def _rotation_translation(mobile: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mc = mobile.mean(axis=0)
    tc = target.mean(axis=0)
    p = mobile - mc
    q = target - tc
    h = p.T @ q
    u, _s, vt = np.linalg.svd(h)
    rot = vt.T @ u.T
    if np.linalg.det(rot) < 0:
        vt = vt.copy()
        vt[-1] *= -1
        rot = vt.T @ u.T
    trans = tc - mc @ rot.T
    return rot, trans


def _region_is_cdr(reg: str, cdr_name: str) -> bool:
    """ANARCI 区域名如 CDR-H3 / CDR-L1。"""
    if "CDR" not in (reg or ""):
        return False
    n = cdr_name[-1] if cdr_name[-1].isdigit() else ""
    if not n:
        return False
    return bool(re.search(rf"(?:CDR-?[HL]?{n}|CDR{n})$", reg))


def cdr_rmsd_vs_wt(
    wt: Structure,
    mut: Structure,
    chain: str,
    regions: list[str],
    cdr_name: str,
) -> float | None:
    """FR 对齐后指定 CDR 的 CA RMSD。regions 为 0-based 序列上的 ANARCI 区域名。"""
    wt_ch = wt.by_chain().get(chain, [])
    mut_ch = mut.by_chain().get(chain, [])
    if not wt_ch or not mut_ch:
        return None
    fr_wt, fr_mut, cdr_wt, cdr_mut = [], [], [], []
    for r in wt_ch:
        idx = r.seqid - 1
        if idx < 0 or idx >= len(regions):
            continue
        m = mut.lookup().get((chain, r.seqid))
        if r.ca is None or m is None or m.ca is None:
            continue
        reg = regions[idx] or ""
        if (reg or "").startswith("FR"):
            fr_wt.append(r.ca)
            fr_mut.append(m.ca)
        if _region_is_cdr(reg, cdr_name):
            cdr_wt.append(r.ca)
            cdr_mut.append(m.ca)
    if len(fr_wt) < 3 or len(cdr_wt) < 2:
        return None
    r, t = _rotation_translation(np.stack(fr_mut), np.stack(fr_wt))
    cdr_aln = np.stack(cdr_mut) @ r.T + t
    return round(_rmsd(cdr_aln, np.stack(cdr_wt)), 4)


def residue_contacts(
    st: Structure,
    ab_chains: list[str],
    ag_chain: str,
    cutoff: float = CONTACT_CUTOFF,
) -> set[tuple[str, int, str, int]]:
    by = st.by_chain()
    ag = by.get(ag_chain, [])
    pairs: set[tuple[str, int, str, int]] = set()
    for cid in ab_chains:
        for ar in by.get(cid, []):
            if ar.heavy.size == 0:
                continue
            for gr in ag:
                if gr.heavy.size == 0:
                    continue
                d = np.linalg.norm(ar.heavy[:, None, :] - gr.heavy[None, :, :], axis=2).min()
                if d <= cutoff:
                    pairs.add((ar.chain, ar.seqid, gr.chain, gr.seqid))
    return pairs


def _mean_plddt(res_list: list[Residue]) -> float | None:
    vals = [r.plddt for r in res_list if r.plddt is not None]
    if not vals:
        return None
    m = float(sum(vals) / len(vals))
    if max(vals) <= 1.5:
        return round(m, 4)
    return round(m / 100.0, 4)


def plddt_splits(
    st: Structure,
    ab_chains: list[str],
    ag_chain: str,
    regions_by_chain: dict[str, list[str]],
) -> dict[str, float | None]:
    ifc = interface_ab_residues(st, ab_chains, ag_chain)
    ab_all: list[Residue] = []
    cdr: dict[str, list[Residue]] = {"CDR1": [], "CDR2": [], "CDR3": []}
    for cid in ab_chains:
        regs = regions_by_chain.get(cid) or []
        for r in st.by_chain().get(cid, []):
            ab_all.append(r)
            idx = r.seqid - 1
            if not (0 <= idx < len(regs)):
                continue
            name = regs[idx]
            for key in ("CDR1", "CDR2", "CDR3"):
                if _region_is_cdr(name, key):
                    cdr[key].append(r)
    return {
        "plddt_overall": _mean_plddt(ab_all),
        "plddt_interface": _mean_plddt(ifc),
        "plddt_cdr1": _mean_plddt(cdr["CDR1"]),
        "plddt_cdr2": _mean_plddt(cdr["CDR2"]),
        "plddt_cdr3": _mean_plddt(cdr["CDR3"]),
    }


def list_sample_structures(job_dir: Path) -> list[Path]:
    if not job_dir.is_dir():
        return []
    paths: list[Path] = []
    for p in job_dir.rglob("*_model_*"):
        if p.suffix.lower() not in {".cif", ".pdb", ".mmcif"}:
            continue
        if p.name in {"pred.cif", "pred.pdb"}:
            continue
        if re.search(r"_model_\d+\.(cif|pdb|mmcif)$", p.name, re.I):
            paths.append(p)
    # 同 index 优先 pdb
    by_idx: dict[int, Path] = {}
    for p in paths:
        m = re.search(r"_model_(\d+)\.", p.name)
        if not m:
            continue
        idx = int(m.group(1))
        prev = by_idx.get(idx)
        if prev is None or p.suffix.lower() == ".pdb":
            by_idx[idx] = p
    return [by_idx[i] for i in sorted(by_idx)]


def _band_irmsd(val: float | None) -> str:
    if val is None:
        return ""
    if val < IRMSD_PREFER:
        return "prefer"
    if val < IRMSD_CAUTION:
        return "grey"
    return "caution"


def _band_retention(val: float | None) -> str:
    if val is None:
        return ""
    if val >= RETENTION_PREFER:
        return "prefer"
    if val >= RETENTION_CAUTION:
        return "mixed"
    return "caution"


def delta_iptm_band(delta: float | None) -> str:
    if delta is None:
        return ""
    if delta < DELTA_IPTM_SEVERE:
        return "severe"
    if delta < -0.03:
        return "drop"
    return "pass"


def compare_mutant_to_wt(
    wt_path: Path,
    mut_path: Path,
    *,
    ab_chains: list[str],
    ag_chain: str,
    regions_by_chain: dict[str, list[str]] | None = None,
    sample_paths: list[Path] | None = None,
) -> dict:
    """返回写入 ranked 表的姿态字段（失败则空字段）。"""
    empty = {
        "irmsd": None,
        "cdr3_rmsd": None,
        "cdr1_rmsd": None,
        "cdr2_rmsd": None,
        "contact_retention": None,
        "n_wt_contacts": None,
        "n_new_contacts": None,
        "plddt_overall": None,
        "plddt_interface": None,
        "plddt_cdr3": None,
        "n_seed_same_mode": None,
        "n_seeds": None,
        "seed_stable": "",
        "irmsd_band": "",
        "retention_band": "",
        "pose_tags": "",
    }
    try:
        wt = load_structure(wt_path)
        mut = load_structure(mut_path)
    except Exception:
        return empty

    regions_by_chain = regions_by_chain or {}
    irmsd = irmsd_vs_wt(wt, mut, ab_chains, ag_chain)
    cdr_vals: dict[str, float | None] = {"cdr1_rmsd": None, "cdr2_rmsd": None, "cdr3_rmsd": None}
    for cid, regs in regions_by_chain.items():
        for key, name in (("cdr1_rmsd", "CDR1"), ("cdr2_rmsd", "CDR2"), ("cdr3_rmsd", "CDR3")):
            val = cdr_rmsd_vs_wt(wt, mut, cid, regs, name)
            if val is not None:
                cdr_vals[key] = val if cdr_vals[key] is None else max(cdr_vals[key], val)

    wt_ct = residue_contacts(wt, ab_chains, ag_chain)
    mut_ct = residue_contacts(mut, ab_chains, ag_chain)
    n_wt = len(wt_ct)
    retained = len(wt_ct & mut_ct)
    n_new = len(mut_ct - wt_ct)
    retention = round(retained / n_wt, 4) if n_wt else None

    plddt = plddt_splits(mut, ab_chains, ag_chain, regions_by_chain)

    n_same = 0
    n_seeds = 0
    for sp in sample_paths or []:
        try:
            sample = load_structure(sp)
        except Exception:
            continue
        n_seeds += 1
        d = irmsd_vs_wt(wt, sample, ab_chains, ag_chain)
        if d is not None and d < SEED_IRMSD_CUT:
            n_same += 1
    if n_seeds == 0 and irmsd is not None:
        n_seeds = 1
        n_same = 1 if irmsd < SEED_IRMSD_CUT else 0
    seed_frac = (n_same / n_seeds) if n_seeds else 0.0
    seed_stable = "yes" if n_seeds and seed_frac >= SEED_STABLE_FRAC else ("no" if n_seeds else "")

    irmsd_b = _band_irmsd(irmsd)
    ret_b = _band_retention(retention)
    tags = [t for t in (f"irmsd:{irmsd_b}" if irmsd_b else "", f"contacts:{ret_b}" if ret_b else "", f"seeds:{n_same}/{n_seeds}" if n_seeds else "") if t]

    return {
        "irmsd": irmsd,
        "cdr3_rmsd": cdr_vals["cdr3_rmsd"],
        "cdr1_rmsd": cdr_vals["cdr1_rmsd"],
        "cdr2_rmsd": cdr_vals["cdr2_rmsd"],
        "contact_retention": retention,
        "n_wt_contacts": n_wt,
        "n_new_contacts": n_new,
        "plddt_overall": plddt.get("plddt_overall"),
        "plddt_interface": plddt.get("plddt_interface"),
        "plddt_cdr3": plddt.get("plddt_cdr3"),
        "n_seed_same_mode": n_same if n_seeds else None,
        "n_seeds": n_seeds or None,
        "seed_stable": seed_stable,
        "irmsd_band": irmsd_b,
        "retention_band": ret_b,
        "pose_tags": ";".join(tags),
    }
