#!/usr/bin/env python3
"""GROMACS MD validation runner for nanobody–antigen complexes."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
MDP_DIR = Path(__file__).resolve().parent / "md_templates"
FF_DIR = Path(__file__).resolve().parent / "md_forcefields"
FORCEFIELD = "charmm36-jul2022"

GMX_BIN = Path(os.environ.get("GMX_BIN", "/home/pengpai/data/envs/IgGM/bin/gmx"))
GEMMI_PY = os.environ.get("GEMMI_PY", "/home/pengpai/data/envs/IgGM/bin/python")
DEFAULT_MD_OUT = Path(os.environ.get("MD_OUT_ROOT", str(ROOT / "md_outputs")))


@dataclass
class MdResult:
    job_id: str
    status: str  # ok | failed
    stage: str
    seconds: float
    structure_input: str | None = None
    structure_output: str | None = None
    results: dict | None = None
    error: str | None = None


StageCallback = Callable[[str], None]


def _run(cmd: list[str], *, cwd: Path, env: dict | None = None, input_text: str | None = None) -> subprocess.CompletedProcess:
    log_dir = cwd / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^\w\-]+", "_", cmd[1] if len(cmd) > 1 else "cmd")
    log_path = log_dir / f"{name}.log"
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env or os.environ.copy(),
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
    log_path.write_text(
        f"$ {' '.join(cmd)}\n\nSTDOUT:\n{proc.stdout}\n\nSTDERR:\n{proc.stderr}\n",
        encoding="utf-8",
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-4000:]
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{tail}")
    return proc


def cif_to_pdb(cif_path: Path, pdb_path: Path) -> None:
    script = (
        "import gemmi\n"
        f"st = gemmi.read_structure({str(cif_path)!r})\n"
        "st.remove_ligands_and_waters()\n"
        f"st.write_pdb({str(pdb_path)!r})\n"
    )
    proc = subprocess.run(
        [GEMMI_PY, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"CIF→PDB failed: {proc.stderr or proc.stdout}")
    if not pdb_path.is_file():
        raise RuntimeError("CIF→PDB produced no output file")


def _write_prod_mdp(path: Path, *, production_ns: float, gen_seed: int) -> None:
    nsteps = int(round(production_ns * 1_000_000 / 2))  # dt=0.002 ps
    text = (MDP_DIR / "md_prod.mdp").read_text(encoding="utf-8")
    text = re.sub(r"nsteps\s*=\s*\d+", f"nsteps                  = {nsteps}", text)
    text = re.sub(r"gen_seed\s*=\s*-?\d+", f"gen_seed                = {gen_seed}", text)
    path.write_text(text, encoding="utf-8")


def _forcefield_dir() -> Path:
    path = FF_DIR / f"{FORCEFIELD}.ff"
    if not path.is_dir():
        raise FileNotFoundError(
            f"未找到力场 {path}。请将 CHARMM36 GROMACS 端口放到 scripts/md_forcefields/"
        )
    return path


def _gmx_env(gpu_id: int) -> dict[str, str]:
    env = os.environ.copy()
    env["GMX_BIN"] = str(GMX_BIN)
    env["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    # GROMACS searches GMXLIB in addition to the install tree (2026: cwd, install, GMXLIB).
    extra = str(FF_DIR)
    existing = env.get("GMXLIB", "").strip()
    env["GMXLIB"] = extra if not existing else f"{extra}:{existing}"
    return env


def _analyze_replica(work_dir: Path, rep: int) -> dict:
    rep_dir = work_dir / "03_prod" / f"rep{rep}"
    tpr = rep_dir / "md.tpr"
    xtc = rep_dir / "md.xtc"
    summary: dict = {"replica": rep}
    if not tpr.is_file() or not xtc.is_file():
        summary["error"] = "missing tpr/xtc"
        return summary

    ndx = work_dir / "04_analysis" / "backbone.ndx"
    ndx.parent.mkdir(parents=True, exist_ok=True)
    if not ndx.is_file():
        _run(
            [str(GMX_BIN), "make_ndx", "-f", str(rep_dir / "md.gro"), "-o", str(ndx)],
            cwd=rep_dir,
            input_text="1\nq\n",
        )

    rms_xvg = rep_dir / "rmsd_backbone.xvg"
    _run(
        [
            str(GMX_BIN),
            "rms",
            "-s",
            str(tpr),
            "-f",
            str(xtc),
            "-o",
            str(rms_xvg),
            "-n",
            str(ndx),
        ],
        cwd=rep_dir,
        input_text="Backbone\nBackbone\n",
    )
    values: list[float] = []
    for line in rms_xvg.read_text(encoding="utf-8").splitlines():
        if line.startswith(("#", "@")):
            continue
        parts = line.split()
        if len(parts) >= 2:
            try:
                values.append(float(parts[1]))
            except ValueError:
                pass
    if values:
        summary["backbone_rmsd_nm_mean"] = round(sum(values) / len(values), 4)
        summary["backbone_rmsd_nm_last"] = round(values[-1], 4)
    return summary


def run_md_validation(
    *,
    input_structure: Path,
    work_dir: Path,
    production_ns: float = 1.0,
    replicas: int = 1,
    gpu_id: int = 0,
    antigen_chain: str = "A",
    binder_chain: str = "H",
    on_stage: StageCallback | None = None,
) -> MdResult:
    """Run prep → equil → short production → basic analysis."""

    t0 = time.time()
    stage = "prep"

    def set_stage(name: str) -> None:
        nonlocal stage
        stage = name
        if on_stage:
            on_stage(name)

    work_dir.mkdir(parents=True, exist_ok=True)
    env = _gmx_env(gpu_id)
    ntomp = max(4, min(16, (os.cpu_count() or 8) // 2))

    try:
        set_stage("prep")
        struct_dir = work_dir / "00_structure"
        struct_dir.mkdir(parents=True, exist_ok=True)
        src = struct_dir / input_structure.name
        if input_structure.resolve() != src.resolve():
            shutil.copy2(input_structure, src)

        pdb_path = struct_dir / "complex.pdb"
        if src.suffix.lower() in {".cif", ".mmcif"}:
            cif_to_pdb(src, pdb_path)
        elif src.suffix.lower() == ".pdb":
            shutil.copy2(src, pdb_path)
        else:
            raise ValueError(f"Unsupported structure format: {src.suffix}")

        set_stage("topo")
        topo_dir = work_dir / "01_topo"
        topo_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pdb_path, topo_dir / "complex.pdb")
        ff_src = _forcefield_dir()
        ff_dst = topo_dir / ff_src.name
        if ff_dst.exists():
            shutil.rmtree(ff_dst)
        shutil.copytree(ff_src, ff_dst)
        # -ss yes asks y/n for each cysteine pair; auto-accept suggested disulfides.
        _run(
            [
                str(GMX_BIN),
                "pdb2gmx",
                "-f",
                "complex.pdb",
                "-o",
                "processed.gro",
                "-p",
                "topol.top",
                "-ff",
                FORCEFIELD,
                "-water",
                "tip3p",
                "-ignh",
                "-ss",
                "yes",
            ],
            cwd=topo_dir,
            env=env,
            input_text="y\n" * 32,
        )

        set_stage("equil")
        equil_dir = work_dir / "02_equil"
        equil_dir.mkdir(parents=True, exist_ok=True)
        for fname in ("processed.gro", "topol.top"):
            shutil.copy2(topo_dir / fname, equil_dir / fname)
        for itp in topo_dir.glob("*.itp"):
            shutil.copy2(itp, equil_dir / itp.name)

        _run(
            [str(GMX_BIN), "editconf", "-f", "processed.gro", "-o", "boxed.gro", "-c", "-d", "1.2", "-bt", "dodecahedron"],
            cwd=equil_dir,
            env=env,
        )
        _run(
            [str(GMX_BIN), "solvate", "-cp", "boxed.gro", "-cs", "spc216.gro", "-o", "solv.gro", "-p", "topol.top"],
            cwd=equil_dir,
            env=env,
        )
        shutil.copy2(MDP_DIR / "ions.mdp", equil_dir / "ions.mdp")
        _run(
            [str(GMX_BIN), "grompp", "-f", "ions.mdp", "-c", "solv.gro", "-p", "topol.top", "-o", "ions.tpr", "-maxwarn", "2"],
            cwd=equil_dir,
            env=env,
        )
        _run(
            [
                str(GMX_BIN),
                "genion",
                "-s",
                "ions.tpr",
                "-o",
                "solv_ions.gro",
                "-p",
                "topol.top",
                "-pname",
                "NA",
                "-nname",
                "CL",
                "-neutral",
                "-conc",
                "0.15",
            ],
            cwd=equil_dir,
            env=env,
            input_text="SOL\n",
        )

        for step, mdp_name, deffnm in (
            ("em", "minim.mdp", "em"),
            ("nvt", "nvt.mdp", "nvt"),
            ("npt", "npt.mdp", "npt"),
        ):
            shutil.copy2(MDP_DIR / f"{mdp_name}", equil_dir / f"{mdp_name}")
            prev = "solv_ions.gro" if step == "em" else ("em.gro" if step == "nvt" else "nvt.gro")
            _run(
                [
                    str(GMX_BIN),
                    "grompp",
                    "-f",
                    mdp_name,
                    "-c",
                    prev,
                    "-p",
                    "topol.top",
                    "-o",
                    f"{deffnm}.tpr",
                    "-maxwarn",
                    "2",
                ],
                cwd=equil_dir,
                env=env,
            )
            gpu_flags: list[str] = []
            if step != "em":
                gpu_flags = ["-nb", "gpu", "-pme", "gpu", "-bonded", "gpu", "-update", "gpu", "-gpu_id", "0"]
            _run(
                [str(GMX_BIN), "mdrun", "-deffnm", deffnm, "-ntmpi", "1", "-ntomp", str(ntomp), *gpu_flags],
                cwd=equil_dir,
                env=env,
            )

        set_stage("prod")
        replica_summaries: list[dict] = []
        prod_root = work_dir / "03_prod"
        prod_root.mkdir(parents=True, exist_ok=True)

        for rep in range(1, replicas + 1):
            rep_dir = prod_root / f"rep{rep}"
            rep_dir.mkdir(parents=True, exist_ok=True)
            for fname in ("npt.gro", "topol.top"):
                shutil.copy2(equil_dir / fname, rep_dir / fname)
            for itp in equil_dir.glob("*.itp"):
                shutil.copy2(itp, rep_dir / itp.name)

            prod_mdp = rep_dir / "md.mdp"
            _write_prod_mdp(prod_mdp, production_ns=production_ns, gen_seed=1000 + rep)
            _run(
                [
                    str(GMX_BIN),
                    "grompp",
                    "-f",
                    "md.mdp",
                    "-c",
                    "npt.gro",
                    "-p",
                    "topol.top",
                    "-o",
                    "md.tpr",
                    "-maxwarn",
                    "2",
                ],
                cwd=rep_dir,
                env=env,
            )
            _run(
                [
                    str(GMX_BIN),
                    "mdrun",
                    "-deffnm",
                    "md",
                    "-ntmpi",
                    "1",
                    "-ntomp",
                    str(ntomp),
                    "-nb",
                    "gpu",
                    "-pme",
                    "gpu",
                    "-bonded",
                    "gpu",
                    "-update",
                    "gpu",
                    "-gpu_id",
                    "0",
                ],
                cwd=rep_dir,
                env=env,
            )
            try:
                replica_summaries.append(_analyze_replica(work_dir, rep))
            except Exception as exc:
                replica_summaries.append({"replica": rep, "error": str(exc)[:500]})

        set_stage("analysis")
        results = {
            "production_ns": production_ns,
            "replicas": replicas,
            "antigen_chain": antigen_chain,
            "binder_chain": binder_chain,
            "replica_summaries": replica_summaries,
            "verdict": "completed",
        }
        (work_dir / "04_analysis").mkdir(parents=True, exist_ok=True)
        (work_dir / "04_analysis" / "summary.json").write_text(
            json.dumps(results, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        seconds = time.time() - t0
        out_gro = prod_root / "rep1" / "md.gro"
        return MdResult(
            job_id=work_dir.name,
            status="ok",
            stage="done",
            seconds=seconds,
            structure_input=str(input_structure),
            structure_output=str(out_gro) if out_gro.is_file() else None,
            results=results,
        )
    except Exception as exc:
        return MdResult(
            job_id=work_dir.name,
            status="failed",
            stage=stage,
            seconds=time.time() - t0,
            structure_input=str(input_structure),
            error=str(exc)[:8000],
        )


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Run GROMACS MD validation")
    p.add_argument("structure", type=Path)
    p.add_argument("--work-dir", type=Path, required=True)
    p.add_argument("--production-ns", type=float, default=1.0)
    p.add_argument("--replicas", type=int, default=1)
    p.add_argument("--gpu-id", type=int, default=0)
    args = p.parse_args()
    out = run_md_validation(
        input_structure=args.structure,
        work_dir=args.work_dir,
        production_ns=args.production_ns,
        replicas=args.replicas,
        gpu_id=args.gpu_id,
    )
    print(json.dumps(asdict(out), indent=2))
    raise SystemExit(0 if out.status == "ok" else 1)
