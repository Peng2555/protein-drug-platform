"""Boltz2 sample discovery, selection, metrics, and structure conversion."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


def _model_index(path: Path) -> int | None:
    m = re.search(r"_model_(\d+)\.(?:cif|pdb|json)$", path.name)
    return int(m.group(1)) if m else None


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return float(s[mid])
    return float(s[mid - 1] + s[mid]) / 2.0


def _n_pair_chains(pair: dict | None) -> int:
    if not isinstance(pair, dict) or not pair:
        return 0
    ids = {str(k) for k in pair}
    for inner in pair.values():
        if isinstance(inner, dict):
            ids.update(str(k) for k in inner)
    return len(ids)


def _is_monomer_fold(num_chains: int | None, samples: list[dict]) -> bool:
    """单体没有跨链界面，Boltz 仍可能写出 iptm=0。"""
    if num_chains is not None and num_chains <= 1:
        return True
    pair_ns = [_n_pair_chains(s.get("pair_chains_iptm")) for s in samples]
    pair_ns = [n for n in pair_ns if n > 0]
    if pair_ns and max(pair_ns) <= 1:
        return True
    return False


def _select_best_sample(samples: list[dict], *, monomer: bool = False) -> dict:
    """复合物：ipTM 最高；单体：pTM / confidence_score 最高。"""

    def key(s: dict):
        if monomer:
            ptm = s.get("ptm")
            conf = s.get("confidence_score")
            return (
                1 if ptm is None else 0,
                -(float(ptm) if ptm is not None else 0.0),
                1 if conf is None else 0,
                -(float(conf) if conf is not None else 0.0),
                int(s.get("index") or 0),
            )
        iptm = s.get("iptm")
        conf = s.get("confidence_score")
        return (
            1 if iptm is None else 0,
            -(float(iptm) if iptm is not None else 0.0),
            1 if conf is None else 0,
            -(float(conf) if conf is not None else 0.0),
            int(s.get("index") or 0),
        )

    return min(samples, key=key)


def discover_boltz_samples(out_dir: Path) -> list[dict]:
    """收集 Boltz 各 diffusion sample 的结构与 confidence。"""
    by_idx: dict[int, dict] = {}
    for path in out_dir.rglob("*_model_*.cif"):
        idx = _model_index(path)
        if idx is None or path.name.startswith("pred"):
            continue
        by_idx.setdefault(idx, {})["cif"] = path
    for path in out_dir.rglob("*_model_*.pdb"):
        idx = _model_index(path)
        if idx is None:
            continue
        by_idx.setdefault(idx, {})["pdb"] = path
    for path in out_dir.rglob("confidence_*_model_*.json"):
        idx = _model_index(path)
        if idx is None:
            continue
        by_idx.setdefault(idx, {})["conf_path"] = path

    samples: list[dict] = []
    for idx in sorted(by_idx):
        item = by_idx[idx]
        conf: dict = {}
        conf_path = item.get("conf_path")
        if conf_path and Path(conf_path).is_file():
            try:
                conf = json.loads(Path(conf_path).read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                conf = {}
        samples.append(
            {
                "index": idx,
                "cif": str(item["cif"]) if item.get("cif") else None,
                "pdb": str(item["pdb"]) if item.get("pdb") else None,
                "iptm": conf.get("iptm"),
                "ptm": conf.get("ptm"),
                "confidence_score": conf.get("confidence_score"),
                "complex_plddt": conf.get("complex_plddt"),
                "complex_iplddt": conf.get("complex_iplddt"),
                "pair_chains_iptm": conf.get("pair_chains_iptm"),
                "chains_ptm": conf.get("chains_ptm"),
            }
        )
    return samples


def extract_metrics(out_dir: Path, seconds: float | None = None, num_chains: int | None = None) -> dict:
    """汇总多 sample：官方 ipTM 为中位数；pred.cif 复制 ipTM 最高的那一个。

    单体无界面：不把 Boltz 的 iptm=0 当成有效 ipTM，代表结构改按 pTM 选取。
    若仅有 PDB 输出，先写 pred.pdb，再尽量转成 pred.cif。
    """
    samples = discover_boltz_samples(out_dir)
    struct_samples = [s for s in samples if s.get("cif") or s.get("pdb")]
    if not struct_samples:
        cif_files = sorted(out_dir.rglob("*_model_0.cif"))
        pdb_files = sorted(out_dir.rglob("*_model_0.pdb"))
        if cif_files:
            struct_samples = [{"index": 0, "cif": str(cif_files[0]), "iptm": None}]
        elif pdb_files:
            struct_samples = [{"index": 0, "pdb": str(pdb_files[0]), "iptm": None}]
        else:
            raise FileNotFoundError(f"No *_model_*.cif/pdb under {out_dir}")
        samples = struct_samples

    monomer = _is_monomer_fold(num_chains, samples)
    best = _select_best_sample(struct_samples, monomer=monomer)
    pred_cif = out_dir / "pred.cif"
    pred_pdb = out_dir / "pred.pdb"
    source_struct: Path
    if best.get("cif"):
        source_struct = Path(best["cif"])
        shutil.copy2(source_struct, pred_cif)
        if not pred_pdb.is_file():
            try:
                cif_to_pdb(pred_cif, pred_pdb)
            except Exception:
                pass
    else:
        source_struct = Path(best["pdb"])
        shutil.copy2(source_struct, pred_pdb)
        try:
            pdb_to_cif(pred_pdb, pred_cif)
        except Exception:
            if pred_cif.is_file():
                pred_cif.unlink(missing_ok=True)

    if monomer:
        iptm_median = None
        iptm_max = None
        iptm_mean = None
        ptms = [float(s["ptm"]) for s in samples if s.get("ptm") is not None]
        ptm_value = best.get("ptm")
        if ptm_value is None and ptms:
            ptm_value = _median(ptms)
    else:
        iptms = [float(s["iptm"]) for s in samples if s.get("iptm") is not None]
        iptm_median = _median(iptms)
        iptm_max = max(iptms) if iptms else None
        iptm_mean = sum(iptms) / len(iptms) if iptms else None
        ptm_value = best.get("ptm")

    metrics = {
        "pred_cif": str(pred_cif) if pred_cif.is_file() else None,
        "pred_pdb": str(pred_pdb) if pred_pdb.is_file() else None,
        "source_cif": str(source_struct),
        "seconds": seconds,
        "n_samples": len(samples),
        "selected_model": best.get("index"),
        "has_interface": not monomer,
        "iptm": iptm_median,
        "iptm_median": iptm_median,
        "iptm_max": iptm_max,
        "iptm_mean": round(iptm_mean, 6) if iptm_mean is not None else None,
        "confidence_score": best.get("confidence_score") if not monomer else (best.get("confidence_score") or best.get("ptm")),
        "ptm": ptm_value,
        "complex_plddt": best.get("complex_plddt"),
        "complex_iplddt": best.get("complex_iplddt"),
        "pair_chains_iptm": best.get("pair_chains_iptm"),
        "chains_ptm": best.get("chains_ptm"),
        "samples": [
            {
                "index": s.get("index"),
                "iptm": None if monomer else s.get("iptm"),
                "ptm": s.get("ptm"),
                "confidence_score": s.get("confidence_score"),
            }
            for s in samples
        ],
    }
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    if not monomer:
        try:
            try:
                from pdockq_runner import compute_pdockq_from_boltz_dir
            except ImportError:
                from scripts.pdockq_runner import compute_pdockq_from_boltz_dir

            pq = compute_pdockq_from_boltz_dir(out_dir)
            if pq.pdockq is not None and pq.pdockq > 0:
                metrics["pdockq"] = pq.pdockq
                metrics["pdockq2"] = pq.pdockq2
                metrics["pdockq_interfaces"] = [
                    {
                        "chain_a": i.chain_a,
                        "chain_b": i.chain_b,
                        "contact_pairs": i.contact_pairs,
                        "avg_interface_plddt": i.avg_interface_plddt,
                        "pdockq": i.pdockq,
                        "pdockq2": i.pdockq2,
                    }
                    for i in pq.interfaces
                ]
                (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        except Exception:
            pass

    return metrics


def cif_to_pdb(cif_path: Path, pdb_path: Path) -> None:
    """Convert mmCIF to PDB for downstream tools (IgGM, DockQ, etc.)."""
    cif_path = Path(cif_path)
    pdb_path = Path(pdb_path)
    pdb_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from biotite.structure.io.pdbx import CIFFile, get_structure
        from biotite.structure.io.pdb import PDBFile

        cif = CIFFile.read(str(cif_path))
        stack = get_structure(cif, model=1, use_author_fields=True)
        pdb = PDBFile()
        pdb.set_structure(stack)
        pdb.write(str(pdb_path))
        return
    except ImportError:
        pass

    try:
        import gemmi

        structure = gemmi.read_structure(str(cif_path))
        structure.write_pdb(str(pdb_path))
        return
    except ImportError as exc:
        raise ImportError(
            "CIF→PDB conversion requires biotite or gemmi; "
            "install biotite in boltz2 env or ensure boltz (gemmi) is available"
        ) from exc


def pdb_to_cif(pdb_path: Path, cif_path: Path) -> None:
    """Convert PDB to mmCIF so the platform viewer / downstream tools can use pred.cif."""
    pdb_path = Path(pdb_path)
    cif_path = Path(cif_path)
    cif_path.parent.mkdir(parents=True, exist_ok=True)
    import gemmi

    structure = gemmi.read_structure(str(pdb_path))
    structure.make_mmcif_document().write_file(str(cif_path))


def sequences_from_structure(structure_path: Path | str) -> dict[str, str]:
    """Extract one-letter protein sequences per chain from PDB/mmCIF."""
    import gemmi

    path = Path(structure_path)
    if not path.is_file():
        raise FileNotFoundError(f"Structure not found: {path}")

    structure = gemmi.read_structure(str(path))
    if len(structure) == 0:
        raise ValueError(f"No models in structure: {path}")

    out: dict[str, str] = {}
    for chain in structure[0]:
        letters: list[str] = []
        for res in chain:
            tab = gemmi.find_tabulated_residue(res.name)
            if tab is None or not tab.is_amino_acid():
                continue
            code = tab.one_letter_code
            if code and code != "?":
                letters.append(code)
        if letters:
            out[chain.name] = "".join(letters)

    if not out:
        raise ValueError(f"No protein chains found in structure: {path}")
    return out


def pick_chain_key(seqs: dict[str, str], chain_id: str) -> str:
    chain_id = chain_id.strip()
    if chain_id in seqs:
        return chain_id
    upper_map = {k.upper(): k for k in seqs}
    if chain_id.upper() in upper_map:
        return upper_map[chain_id.upper()]
    raise ValueError(
        f"Chain {chain_id!r} not found in structure; available: {', '.join(sorted(seqs))}"
    )
