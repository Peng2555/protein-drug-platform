"""Web worker: RFdiffusion masking peptide + MPNN + cyclic FastRelax."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MaskingPeptideResult:
    status: str
    stage: str
    seconds: float
    results: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def _write_status(work_dir: Path, payload: dict) -> None:
    path = work_dir / "workflow_status.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _chain_length(pdb: Path, chain_id: str) -> int:
    seen: set[str] = set()
    for line in pdb.read_text(errors="replace").splitlines():
        if not line.startswith(("ATOM", "HETATM")):
            continue
        if len(line) < 22:
            continue
        if line[21:22].strip() != chain_id:
            continue
        seen.add(line[22:26].strip())
    if not seen:
        raise RuntimeError(f"PDB {pdb} 中未找到链 {chain_id}")
    return len(seen)


def _merge_round_csv(out_dir: Path) -> Path | None:
    rows: list[dict] = []
    for p in sorted(out_dir.glob("gpu*/sequences.csv")):
        with p.open(newline="", encoding="utf-8") as f:
            rows.extend(csv.DictReader(f))
    if not rows:
        return None
    merged = out_dir / "sequences.csv"
    with merged.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return merged


def _collect_exports(work_dir: Path, params: dict) -> dict[str, Any]:
    exports = work_dir / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    rounds = int(params.get("mpnn_rounds") or 4)
    last_round = work_dir / "05_mpnn" / f"round{rounds}"
    seq_src = last_round / "sequences.csv"
    if not seq_src.is_file():
        seq_src = _merge_round_csv(last_round) if last_round.is_dir() else None

    ranked: list[dict] = []
    if seq_src and seq_src.is_file():
        with seq_src.open(newline="", encoding="utf-8") as f:
            ranked = list(csv.DictReader(f))
        dest_csv = exports / "sequences_final.csv"
        dest_csv.write_text(seq_src.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        dest_csv = None

    struct_dir = exports / "structures"
    struct_dir.mkdir(parents=True, exist_ok=True)
    merged = last_round / "merged"
    n_struct = 0
    if merged.is_dir():
        for pdb in sorted(merged.glob("*.pdb")):
            dest = struct_dir / pdb.name
            if not dest.exists():
                dest.write_bytes(pdb.read_bytes())
            n_struct += 1

    backbone_count = len(
        list((work_dir / "04_rfdiffusion").rglob("mask_pep_*.pdb"))
    )
    summary = {
        "status": "ok" if ranked else "partial",
        "n_backbones": backbone_count,
        "n_sequences": len(ranked),
        "n_structures": n_struct,
        "mpnn_rounds": rounds,
        "total_designs": params.get("total_designs"),
        "sequences_csv": str(dest_csv) if dest_csv else None,
        "structures_dir": str(struct_dir),
    }
    (exports / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {
        "exports_dir": str(exports),
        "sequences_csv": str(dest_csv) if dest_csv else None,
        "structures_dir": str(struct_dir),
        "summary": summary,
        "sequences": ranked,
    }


def _run_cmd(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None) -> None:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-4000:]
        raise RuntimeError(f"命令失败 ({proc.returncode}): {' '.join(cmd)}\n{tail}")


def _run_backbone_shard(
    *,
    rf_root: Path,
    rf_py: str,
    antibody_pdb: Path,
    out_prefix: Path,
    num_designs: int,
    design_startnum: int,
    contig: str,
    hotspots: list[str],
    gpu: int,
    diffuser_t: int,
) -> None:
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(gpu)
    hotspot_str = ",".join(hotspots)
    cmd = [
        rf_py,
        "scripts/run_inference.py",
        "--config-name",
        "base",
        f"inference.output_prefix={out_prefix}",
        f"inference.num_designs={num_designs}",
        f"inference.design_startnum={design_startnum}",
        f"inference.input_pdb={antibody_pdb}",
        f"contigmap.contigs=[{contig}]",
        "inference.cyclic=True",
        "inference.cyc_chains=a",
        f"diffuser.T={diffuser_t}",
        f"ppi.hotspot_res=[{hotspot_str}]",
    ]
    _run_cmd(cmd, cwd=rf_root, env=env)


def _run_mpnn_shard(
    *,
    mpnn_script: Path,
    se3_py: str,
    pdb_dir: Path,
    out_dir: Path,
    work_dir: Path,
    gpu: int,
    seed: int,
    relax_jobs: int,
) -> None:
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(gpu)
    cmd = [
        se3_py,
        str(mpnn_script),
        "--pdb_dir",
        str(pdb_dir),
        "--out_dir",
        str(out_dir),
        "--work_dir",
        str(work_dir),
        "--peptide_chain",
        "A",
        "--seed",
        str(seed),
        "--relax_jobs",
        str(relax_jobs),
    ]
    _run_cmd(cmd, env=env)


def run_masking_peptide_job(
    *,
    work_dir: Path,
    params: dict[str, Any] | None = None,
    on_stage: Callable[[str], None] | None = None,
) -> MaskingPeptideResult:
    """Execute RF backbone → MPNN+Relax rounds under work_dir (campaign layout)."""
    params = dict(params or {})
    work_dir = work_dir.resolve()
    t0 = time.monotonic()

    def stage(name: str) -> None:
        if on_stage:
            on_stage(name)

    try:
        rf_root = Path(params.get("rfdiffusion_root") or "/home/pengpai/data/Company_Project/RFdiffusion")
        rf_py = params.get("rf_py") or "/home/pengpai/data/envs/SE3nv/bin/python"
        se3_py = params.get("se3_py") or "/home/pengpai/data/envs/SE3nv/bin/python"
        mpnn_script = Path(
            params.get("mpnn_relax_script")
            or "/home/pengpai/data/Company_Project/CD98-23110_masking_peptide/scripts/run_mpnn_relax_round.py"
        )

        antibody_pdb = work_dir / "02_structures" / "antibody_H.pdb"
        if not antibody_pdb.is_file():
            return MaskingPeptideResult(
                status="failed",
                stage="init",
                seconds=time.monotonic() - t0,
                error=f"缺少抗体 PDB: {antibody_pdb}",
            )

        target_chain = str(params.get("target_chain") or "H")
        peptide_length = str(params.get("peptide_length") or "12-18")
        hotspots = params.get("hotspot_res") or ["H35", "H47", "H50", "H104", "H110"]
        if isinstance(hotspots, str):
            hotspots = [h.strip() for h in hotspots.split(",") if h.strip()]

        ab_len = _chain_length(antibody_pdb, target_chain)
        contig = f"{peptide_length} {target_chain}1-{ab_len}/0"
        total_designs = int(params.get("total_designs") or 200)
        mpnn_rounds = int(params.get("mpnn_rounds") or 4)
        relax_jobs = int(params.get("relax_jobs") or 8)
        gpu_str = str(params.get("gpus") or "0,1,2,3")
        gpus = [int(x.strip()) for x in gpu_str.split(",") if x.strip()]
        ngpu = max(1, len(gpus))
        if total_designs % ngpu != 0:
            total_designs = (total_designs // ngpu) * ngpu or ngpu
        per_gpu = total_designs // ngpu

        (work_dir / "logs").mkdir(parents=True, exist_ok=True)
        (work_dir / "04_rfdiffusion").mkdir(parents=True, exist_ok=True)
        (work_dir / "05_mpnn").mkdir(parents=True, exist_ok=True)

        if not params.get("skip_backbone"):
            stage("backbone")
            pids: list[subprocess.Popen] = []
            for idx, gpu in enumerate(gpus):
                start = idx * per_gpu
                out_dir = work_dir / "04_rfdiffusion" / f"gpu{gpu}"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_prefix = out_dir / "mask_pep"
                log_path = work_dir / "logs" / f"backbone_gpu{gpu}.log"
                env = os.environ.copy()
                env["CUDA_VISIBLE_DEVICES"] = str(gpu)
                hotspot_str = ",".join(hotspots)
                cmd = [
                    rf_py,
                    "scripts/run_inference.py",
                    "--config-name",
                    "base",
                    f"inference.output_prefix={out_prefix}",
                    f"inference.num_designs={per_gpu}",
                    f"inference.design_startnum={start}",
                    f"inference.input_pdb={antibody_pdb}",
                    f"contigmap.contigs=[{contig}]",
                    "inference.cyclic=True",
                    "inference.cyc_chains=a",
                    "diffuser.T=50",
                    f"ppi.hotspot_res=[{hotspot_str}]",
                ]
                log_f = log_path.open("w", encoding="utf-8")
                pids.append(
                    subprocess.Popen(
                        cmd,
                        cwd=str(rf_root),
                        env=env,
                        stdout=log_f,
                        stderr=subprocess.STDOUT,
                    )
                )
            fail = 0
            for p in pids:
                if p.wait() != 0:
                    fail = 1
            if fail:
                raise RuntimeError("骨架扩散阶段有 GPU 任务失败，请查看 logs/backbone_gpu*.log")

        all_pdbs = sorted(
            p
            for p in (work_dir / "04_rfdiffusion").rglob("mask_pep_*.pdb")
            if "traj" not in p.parts
        )
        if not all_pdbs:
            raise RuntimeError("04_rfdiffusion/ 下未找到 mask_pep_*.pdb")

        stage0 = work_dir / "05_mpnn" / "round0_backbones"
        stage0.mkdir(parents=True, exist_ok=True)
        for old in stage0.glob("*.pdb"):
            old.unlink()
        for pdb in all_pdbs:
            gpu_tag = pdb.parent.name
            link = stage0 / f"{gpu_tag}_{pdb.stem}.pdb"
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(pdb.resolve())

        in_dir = stage0
        for round_i in range(1, mpnn_rounds + 1):
            stage(f"mpnn_round{round_i}")
            out_dir = work_dir / "05_mpnn" / f"round{round_i}"
            out_dir.mkdir(parents=True, exist_ok=True)
            pdbs = sorted(in_dir.glob("*.pdb"))
            if not pdbs:
                raise RuntimeError(f"round {round_i} 无输入 PDB")

            shard_root = work_dir / "05_mpnn" / f"shards_round{round_i}"
            if shard_root.exists():
                import shutil

                shutil.rmtree(shard_root)
            for gpu in gpus:
                (shard_root / f"gpu{gpu}").mkdir(parents=True)

            for i, pdb in enumerate(pdbs):
                gpu = gpus[i % ngpu]
                dest = shard_root / f"gpu{gpu}" / pdb.name
                if dest.exists() or dest.is_symlink():
                    dest.unlink()
                dest.symlink_to(pdb.resolve())

            mpnn_pids: list[subprocess.Popen] = []
            for gpu in gpus:
                shard = shard_root / f"gpu{gpu}"
                work = work_dir / "05_mpnn" / f"work_round{round_i}_gpu{gpu}"
                out_shard = out_dir / f"gpu{gpu}"
                out_shard.mkdir(parents=True, exist_ok=True)
                log_path = work_dir / "logs" / f"mpnn_round{round_i}_gpu{gpu}.log"
                env = os.environ.copy()
                env["CUDA_VISIBLE_DEVICES"] = str(gpu)
                cmd = [
                    se3_py,
                    str(mpnn_script),
                    "--pdb_dir",
                    str(shard),
                    "--out_dir",
                    str(out_shard),
                    "--work_dir",
                    str(work),
                    "--peptide_chain",
                    "A",
                    "--seed",
                    str(37 + round_i * 10 + gpu),
                    "--relax_jobs",
                    str(relax_jobs),
                ]
                log_f = log_path.open("w", encoding="utf-8")
                mpnn_pids.append(
                    subprocess.Popen(cmd, env=env, stdout=log_f, stderr=subprocess.STDOUT)
                )
            fail = 0
            for p in mpnn_pids:
                if p.wait() != 0:
                    fail = 1
            if fail:
                raise RuntimeError(f"MPNN round {round_i} 失败，见 logs/mpnn_round{round_i}_gpu*.log")

            merge = out_dir / "merged"
            merge.mkdir(parents=True, exist_ok=True)
            for shard_pdb in out_dir.rglob("gpu*/*.pdb"):
                dest = merge / shard_pdb.name
                if not dest.exists():
                    dest.write_bytes(shard_pdb.read_bytes())
            _merge_round_csv(out_dir)
            in_dir = merge

        stage("export")
        results = _collect_exports(work_dir, params)
        _write_status(
            work_dir,
            {
                "status": "ok",
                "stage": "done",
                "summary": results.get("summary"),
            },
        )
        return MaskingPeptideResult(
            status="ok",
            stage="done",
            seconds=time.monotonic() - t0,
            results=results,
        )
    except Exception as exc:
        results = _collect_exports(work_dir, params) if work_dir.is_dir() else {}
        _write_status(
            work_dir,
            {"status": "failed", "stage": "error", "error": str(exc)},
        )
        return MaskingPeptideResult(
            status="failed",
            stage="error",
            seconds=time.monotonic() - t0,
            results=results,
            error=str(exc),
        )
