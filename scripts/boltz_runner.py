#!/usr/bin/env python3
"""Core Boltz2 runner: FASTA / sequences -> YAML -> predict -> standardized output."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

VALID_AA = set("ACDEFGHIKLMNPQRSTVWY")
# Boltz2 truncates chain names to 4 chars internally; longer IDs cause silent preprocess failure.
BOLTZ_MAX_CHAIN_ID_LEN = 4

BOLTZ_BIN = Path(os.environ.get("BOLTZ_BIN", "/home/pengpai/data/envs/boltz2/bin/boltz"))
DEFAULT_OUT_ROOT = Path(os.environ.get("BOLTZ2_OUT_ROOT", "/home/pengpai/data/Company_Project/Boltz2/outputs"))


@dataclass
class FoldResult:
    job_id: str
    status: str  # ok | failed
    fasta: str | None
    num_chains: int
    total_length: int
    chains: dict[str, int]
    pred_cif: str | None
    pred_pdb: str | None
    iptm: float | None
    ptm: float | None
    confidence_score: float | None
    complex_plddt: float | None
    seconds: float
    pdockq: float | None = None
    pdockq2: float | None = None
    error: str | None = None


def read_fasta(path: Path | str) -> dict[str, str]:
    path = Path(path)
    seqs: dict[str, str] = {}
    name: str | None = None
    parts: list[str] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            if name is not None:
                seqs[name] = validate_seq("".join(parts), name, str(path))
            name = line[1:].split()[0]
            parts = []
        else:
            parts.append(line.upper())
    if name is None:
        raise ValueError(f"Empty FASTA: {path}")
    seqs[name] = validate_seq("".join(parts), name, str(path))
    return seqs


def parse_fasta_text(text: str) -> dict[str, str]:
    seqs: dict[str, str] = {}
    name: str | None = None
    parts: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            if name is not None:
                seqs[name] = validate_seq("".join(parts), name, "input")
            name = line[1:].split()[0]
            parts = []
        else:
            parts.append(line.upper())
    if name is None:
        raise ValueError("Empty FASTA text")
    seqs[name] = validate_seq("".join(parts), name, "input")
    return seqs


def validate_seq(seq: str, chain_id: str, source: str) -> str:
    bad = sorted({c for c in seq if c not in VALID_AA})
    if bad:
        raise ValueError(f"{source} chain {chain_id}: invalid letters {bad}")
    if len(seq) < 5:
        raise ValueError(f"{source} chain {chain_id}: sequence too short ({len(seq)})")
    return seq


def validate_boltz_chain_ids(seqs: dict[str, str]) -> None:
    """Boltz2 requires chain IDs ≤4 characters (internal truncation breaks MSA mapping)."""
    too_long = sorted(cid for cid in seqs if len(cid) > BOLTZ_MAX_CHAIN_ID_LEN)
    if too_long:
        examples = ", ".join(f">{cid}" for cid in too_long[:3])
        raise ValueError(
            f"Boltz2 链 ID 不能超过 {BOLTZ_MAX_CHAIN_ID_LEN} 个字符，"
            f"当前过长: {too_long}。"
            f"请将 FASTA 头改为短 ID（如 >A、>H），例如把 {examples} 改为 ≤4 字符的唯一 ID。"
        )
    truncated = [cid[:BOLTZ_MAX_CHAIN_ID_LEN] for cid in seqs]
    if len(truncated) != len(set(truncated)):
        dupes = sorted({t for t in truncated if truncated.count(t) > 1})
        raise ValueError(
            f"Boltz2 链 ID 在前 {BOLTZ_MAX_CHAIN_ID_LEN} 个字符内必须唯一（Boltz 会截断长 ID），"
            f"冲突: {dupes}"
        )


def write_boltz_yaml(seqs: dict[str, str], path: Path) -> None:
    lines = ["version: 1", "sequences:"]
    for chain_id, seq in seqs.items():
        lines.append("  - protein:")
        lines.append(f"      id: {chain_id}")
        lines.append(f"      sequence: {seq}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _yaml_quote(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _format_chain_ids(ids: list[str]) -> str:
    if len(ids) == 1:
        return ids[0]
    return "[" + ", ".join(ids) + "]"


def build_boltz_yaml_text(
    components: list[dict],
    *,
    constraints: list[dict] | None = None,
    affinity_binder: str | None = None,
) -> str:
    """Build Boltz input YAML from structured components (protein/dna/rna/ligand)."""
    lines = ["version: 1", "sequences:"]
    for comp in components:
        entity = comp["entity"]
        ids = list(comp["ids"])
        lines.append(f"  - {entity}:")
        lines.append(f"      id: {_format_chain_ids(ids)}")
        if entity == "ligand":
            if comp.get("smiles"):
                lines.append(f"      smiles: {_yaml_quote(str(comp['smiles']).strip())}")
            elif comp.get("ccd"):
                lines.append(f"      ccd: {str(comp['ccd']).strip()}")
            else:
                raise ValueError("ligand requires smiles or ccd")
        else:
            seq = str(comp.get("sequence") or "").replace(" ", "").replace("\n", "").upper()
            lines.append(f"      sequence: {seq}")
            if comp.get("cyclic"):
                lines.append("      cyclic: true")
            mods = comp.get("modifications") or []
            if mods:
                lines.append("      modifications:")
                for mod in mods:
                    lines.append(f"        - position: {int(mod['position'])}")
                    lines.append(f"          ccd: {str(mod['ccd']).strip()}")

    if constraints:
        lines.append("constraints:")
        for c in constraints:
            ctype = c.get("type")
            if ctype == "pocket":
                lines.append("  - pocket:")
                lines.append(f"      binder: {c['binder']}")
                contact_parts = []
                for ch, res in c["contacts"]:
                    contact_parts.append(f"[{ch}, {int(res)}]")
                lines.append(f"      contacts: [ {', '.join(contact_parts)} ]")
                if c.get("max_distance") is not None:
                    lines.append(f"      max_distance: {float(c['max_distance'])}")
                if c.get("force"):
                    lines.append("      force: true")
            elif ctype == "contact":
                t1 = c["token1"]
                t2 = c["token2"]
                lines.append("  - contact:")
                lines.append(f"      token1: [{t1[0]}, {int(t1[1])}]")
                lines.append(f"      token2: [{t2[0]}, {int(t2[1])}]")
                if c.get("max_distance") is not None:
                    lines.append(f"      max_distance: {float(c['max_distance'])}")
                if c.get("force"):
                    lines.append("      force: true")
            else:
                raise ValueError(f"unsupported constraint type: {ctype}")

    if affinity_binder:
        lines.append("properties:")
        lines.append("  - affinity:")
        lines.append(f"      binder: {affinity_binder}")

    return "\n".join(lines) + "\n"


def write_boltz_complex_yaml(
    path: Path,
    components: list[dict],
    *,
    constraints: list[dict] | None = None,
    affinity_binder: str | None = None,
) -> str:
    text = build_boltz_yaml_text(
        components,
        constraints=constraints,
        affinity_binder=affinity_binder,
    )
    path.write_text(text, encoding="utf-8")
    return text


def polymer_seqs_from_components(components: list[dict]) -> dict[str, str]:
    """Expand copies into chain_id -> sequence for polymers only (for hashing / display)."""
    out: dict[str, str] = {}
    for comp in components:
        if comp.get("entity") == "ligand":
            continue
        seq = str(comp.get("sequence") or "").replace(" ", "").replace("\n", "").upper()
        for cid in comp["ids"]:
            out[str(cid)] = seq
    return out


def chains_meta_from_components(components: list[dict]) -> dict[str, int]:
    meta: dict[str, int] = {}
    for comp in components:
        if comp.get("entity") == "ligand":
            token = (comp.get("smiles") or comp.get("ccd") or "").strip()
            for cid in comp["ids"]:
                meta[str(cid)] = max(1, len(token))
        else:
            seq = str(comp.get("sequence") or "").replace(" ", "").replace("\n", "")
            for cid in comp["ids"]:
                meta[str(cid)] = len(seq)
    return meta


def write_fasta(seqs: dict[str, str], path: Path) -> None:
    lines: list[str] = []
    for chain_id, seq in seqs.items():
        lines.append(f">{chain_id}")
        lines.append(seq)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def job_id_from_seqs(seqs: dict[str, str], prefix: str | None = None) -> str:
    payload = json.dumps(seqs, sort_keys=True)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:12]
    if prefix:
        safe = re.sub(r"[^\w\-]", "_", prefix)[:40]
        return f"{safe}_{digest}"
    return digest


def _boltz_run_error(out_dir: Path, proc: subprocess.CompletedProcess) -> str:
    """Best-effort message when boltz exits 0 but produces no structure."""
    log = "\n".join(filter(None, [proc.stderr, proc.stdout])).strip()
    for line in log.splitlines():
        if "Failed to process" in line or "KeyError:" in line or "Error:" in line:
            return line.strip()
    manifest = out_dir / "boltz_results_input" / "processed" / "manifest.json"
    if manifest.is_file():
        try:
            records = json.loads(manifest.read_text()).get("records") or []
            if not records:
                return (
                    "Boltz2 预处理未生成有效输入（常见原因：链 ID 超过 4 个字符，"
                    "请将 FASTA 头改为 >A、>H 等短 ID 后重试）"
                )
        except json.JSONDecodeError:
            pass
    err_log = out_dir / "error.log"
    if err_log.is_file():
        return err_log.read_text(encoding="utf-8").strip()[-4000:]
    if log:
        return log[-4000:]
    return "boltz predict finished without structure output"


def extract_metrics(out_dir: Path, seconds: float | None = None) -> dict:
    cif_files = sorted(out_dir.rglob("*_model_0.cif"))
    if not cif_files:
        raise FileNotFoundError(f"No *_model_0.cif under {out_dir}")
    pred_src = cif_files[0]
    pred_dst = out_dir / "pred.cif"
    shutil.copy2(pred_src, pred_dst)

    conf: dict = {}
    conf_files = sorted(out_dir.rglob("confidence_*_model_0.json"))
    if conf_files:
        conf = json.loads(conf_files[0].read_text())

    metrics = {
        "pred_cif": str(pred_dst),
        "source_cif": str(pred_src),
        "seconds": seconds,
        "confidence_score": conf.get("confidence_score"),
        "ptm": conf.get("ptm"),
        "iptm": conf.get("iptm"),
        "complex_plddt": conf.get("complex_plddt"),
        "complex_iplddt": conf.get("complex_iplddt"),
        "pair_chains_iptm": conf.get("pair_chains_iptm"),
        "chains_ptm": conf.get("chains_ptm"),
    }
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    try:
        from pdockq_runner import compute_pdockq_from_boltz_dir

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


def boltz_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("BOLTZ_CACHE", "/home/pengpai/data/cache/boltz")
    env.setdefault("HF_HOME", "/home/pengpai/data/cache/huggingface")
    env.setdefault("TORCH_HOME", "/home/pengpai/data/cache/torch")
    return env


def run_boltz_predict(
    yaml_path: Path,
    out_dir: Path,
    *,
    use_msa_server: bool = True,
    recycling_steps: int = 3,
    sampling_steps: int = 200,
    diffusion_samples: int = 1,
    max_parallel_samples: int | None = 5,
    step_scale: float | None = None,
    seed: int | None = None,
    output_format: str = "mmcif",
    model: str = "boltz2",
    method: str | None = None,
    use_potentials: bool = False,
    msa_pairing_strategy: str = "greedy",
    max_msa_seqs: int = 8192,
    subsample_msa: bool = False,
    num_subsampled_msa: int = 1024,
    write_full_pae: bool = False,
    write_full_pde: bool = False,
    write_embeddings: bool = False,
    devices: int = 1,
    override: bool = True,
) -> subprocess.CompletedProcess:
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = output_format if output_format in {"mmcif", "pdb"} else "mmcif"
    cmd = [
        str(BOLTZ_BIN),
        "predict",
        str(yaml_path),
        "--out_dir",
        str(out_dir),
        "--model",
        model if model in {"boltz1", "boltz2"} else "boltz2",
        "--recycling_steps",
        str(int(recycling_steps)),
        "--sampling_steps",
        str(int(sampling_steps)),
        "--diffusion_samples",
        str(int(diffusion_samples)),
        "--output_format",
        fmt,
        "--devices",
        str(devices),
        "--max_msa_seqs",
        str(int(max_msa_seqs)),
        "--num_subsampled_msa",
        str(int(num_subsampled_msa)),
    ]
    if max_parallel_samples is not None:
        cmd.extend(["--max_parallel_samples", str(int(max_parallel_samples))])
    if step_scale is not None:
        cmd.extend(["--step_scale", str(float(step_scale))])
    if seed is not None:
        cmd.extend(["--seed", str(int(seed))])
    if method and str(method).strip():
        cmd.extend(["--method", str(method).strip()])
    if use_msa_server:
        cmd.append("--use_msa_server")
        cmd.extend(["--msa_pairing_strategy", msa_pairing_strategy or "greedy"])
    if use_potentials:
        cmd.append("--use_potentials")
    if subsample_msa:
        cmd.append("--subsample_msa")
    if write_full_pae:
        cmd.append("--write_full_pae")
    if write_full_pde:
        cmd.append("--write_full_pde")
    if write_embeddings:
        cmd.append("--write_embeddings")
    if override:
        cmd.append("--override")

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=boltz_env(),
        check=False,
    )


def fold_sequences(
    seqs: dict[str, str],
    out_root: Path | None = None,
    job_id: str | None = None,
    *,
    use_msa_server: bool = True,
    recycling_steps: int = 3,
    sampling_steps: int = 200,
    diffusion_samples: int = 1,
    max_parallel_samples: int | None = 5,
    step_scale: float | None = None,
    seed: int | None = None,
    output_format: str = "mmcif",
    model: str = "boltz2",
    method: str | None = None,
    use_potentials: bool = False,
    msa_pairing_strategy: str = "greedy",
    max_msa_seqs: int = 8192,
    subsample_msa: bool = False,
    num_subsampled_msa: int = 1024,
    write_full_pae: bool = False,
    write_full_pde: bool = False,
    write_embeddings: bool = False,
    skip_if_done: bool = True,
    write_pdb: bool = True,
    fasta_path: Path | None = None,
    yaml_text: str | None = None,
) -> FoldResult:
    """Run Boltz2 on a chain_id -> sequence mapping."""
    t0 = time.time()
    out_root = out_root or DEFAULT_OUT_ROOT
    job_id = job_id or job_id_from_seqs(seqs)
    job_dir = out_root / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    chains_len = {k: len(v) for k, v in seqs.items()}
    total_len = sum(chains_len.values())
    result_path = job_dir / "result.json"

    if skip_if_done and (job_dir / "metrics.json").exists():
        m = json.loads((job_dir / "metrics.json").read_text())
        return FoldResult(
            job_id=job_id,
            status="ok",
            fasta=str(fasta_path) if fasta_path else None,
            num_chains=len(seqs),
            total_length=total_len,
            chains=chains_len,
            pred_cif=m.get("pred_cif"),
            pred_pdb=str(job_dir / "pred.pdb") if (job_dir / "pred.pdb").exists() else None,
            iptm=m.get("iptm"),
            ptm=m.get("ptm"),
            confidence_score=m.get("confidence_score"),
            complex_plddt=m.get("complex_plddt"),
            pdockq=m.get("pdockq"),
            pdockq2=m.get("pdockq2"),
            seconds=m.get("seconds") or 0.0,
        )

    try:
        if seqs:
            validate_boltz_chain_ids(seqs)

        fasta_out = job_dir / "input.fasta"
        yaml_out = job_dir / "input.yaml"
        if seqs:
            write_fasta(seqs, fasta_out)
        if yaml_text and yaml_text.strip():
            yaml_out.write_text(yaml_text, encoding="utf-8")
        else:
            if not seqs:
                raise ValueError("No sequences or YAML provided for Boltz2")
            write_boltz_yaml(seqs, yaml_out)

        predict_kwargs = {
            "use_msa_server": use_msa_server,
            "recycling_steps": recycling_steps,
            "sampling_steps": sampling_steps,
            "diffusion_samples": diffusion_samples,
            "max_parallel_samples": max_parallel_samples,
            "step_scale": step_scale,
            "seed": seed,
            "output_format": output_format,
            "model": model,
            "method": method,
            "use_potentials": use_potentials,
            "msa_pairing_strategy": msa_pairing_strategy,
            "max_msa_seqs": max_msa_seqs,
            "subsample_msa": subsample_msa,
            "num_subsampled_msa": num_subsampled_msa,
            "write_full_pae": write_full_pae,
            "write_full_pde": write_full_pde,
            "write_embeddings": write_embeddings,
        }
        (job_dir / "boltz_params.json").write_text(
            json.dumps(predict_kwargs, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        proc = run_boltz_predict(yaml_out, job_dir, **predict_kwargs)
        elapsed = time.time() - t0

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "boltz predict failed").strip()
            (job_dir / "error.log").write_text(err, encoding="utf-8")
            result = FoldResult(
                job_id=job_id,
                status="failed",
                fasta=str(fasta_path or fasta_out),
                num_chains=len(seqs),
                total_length=total_len,
                chains=chains_len,
                pred_cif=None,
                pred_pdb=None,
                iptm=None,
                ptm=None,
                confidence_score=None,
                complex_plddt=None,
                seconds=elapsed,
                error=err[-4000:],
            )
            result_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
            return result

        # Prefer model_0 cif; also accept pdb if requested
        cif_hits = sorted(job_dir.rglob("*_model_0.cif"))
        pdb_hits = sorted(job_dir.rglob("*_model_0.pdb"))
        if not cif_hits and not pdb_hits:
            err = _boltz_run_error(job_dir, proc)
            (job_dir / "error.log").write_text(err, encoding="utf-8")
            result = FoldResult(
                job_id=job_id,
                status="failed",
                fasta=str(fasta_path or fasta_out),
                num_chains=len(seqs),
                total_length=total_len,
                chains=chains_len,
                pred_cif=None,
                pred_pdb=None,
                iptm=None,
                ptm=None,
                confidence_score=None,
                complex_plddt=None,
                seconds=elapsed,
                error=err[-4000:],
            )
            result_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
            return result

        if not cif_hits and pdb_hits:
            # Normalize pdb output into pred.pdb; metrics may be limited
            pred_pdb = job_dir / "pred.pdb"
            shutil.copy2(pdb_hits[0], pred_pdb)
            result = FoldResult(
                job_id=job_id,
                status="ok",
                fasta=str(fasta_path or fasta_out),
                num_chains=len(seqs),
                total_length=total_len,
                chains=chains_len,
                pred_cif=None,
                pred_pdb=str(pred_pdb),
                iptm=None,
                ptm=None,
                confidence_score=None,
                complex_plddt=None,
                seconds=elapsed,
            )
            result_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
            return result

        metrics = extract_metrics(job_dir, seconds=elapsed)
        pred_cif = Path(metrics["pred_cif"])
        pred_pdb_path: str | None = None
        if write_pdb and pred_cif.exists():
            try:
                pdb_path = job_dir / "pred.pdb"
                cif_to_pdb(pred_cif, pdb_path)
                pred_pdb_path = str(pdb_path)
            except ImportError:
                pass

        result = FoldResult(
            job_id=job_id,
            status="ok",
            fasta=str(fasta_path or fasta_out),
            num_chains=len(seqs),
            total_length=total_len,
            chains=chains_len,
            pred_cif=str(pred_cif),
            pred_pdb=pred_pdb_path,
            iptm=metrics.get("iptm"),
            ptm=metrics.get("ptm"),
            confidence_score=metrics.get("confidence_score"),
            complex_plddt=metrics.get("complex_plddt"),
            pdockq=metrics.get("pdockq"),
            pdockq2=metrics.get("pdockq2"),
            seconds=elapsed,
        )
        result_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
        return result

    except Exception as exc:
        elapsed = time.time() - t0
        result = FoldResult(
            job_id=job_id,
            status="failed",
            fasta=str(fasta_path) if fasta_path else None,
            num_chains=len(seqs),
            total_length=total_len,
            chains=chains_len,
            pred_cif=None,
            pred_pdb=None,
            iptm=None,
            ptm=None,
            confidence_score=None,
            complex_plddt=None,
            seconds=elapsed,
            error=str(exc),
        )
        result_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
        return result


def fold_fasta(
    fasta: Path,
    out_root: Path | None = None,
    job_id: str | None = None,
    **kwargs,
) -> FoldResult:
    seqs = read_fasta(fasta)
    jid = job_id or job_id_from_seqs(seqs, prefix=fasta.stem)
    return fold_sequences(seqs, out_root=out_root, job_id=jid, fasta_path=fasta, **kwargs)
