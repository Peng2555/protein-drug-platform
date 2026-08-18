#!/usr/bin/env python3
"""Linux adapter for the ras-tricomplex-docking repository.

The upstream project is a collection of reproducible scripts. This adapter
copies one project into the job directory, runs one stage, and returns a
machine-readable summary without changing the shared checkout.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class RasDockingResult:
    status: str
    stage: str
    seconds: float
    results: dict
    error: str | None = None


def _run(cmd: list[str], cwd: Path, env: dict[str, str], log: Path) -> None:
    proc = subprocess.run(cmd, cwd=cwd, env=env, text=True,
                          capture_output=True, check=False)
    log.write_text(
        "$ " + " ".join(cmd) + "\n\nSTDOUT:\n" + proc.stdout
        + "\n\nSTDERR:\n" + proc.stderr,
        encoding="utf-8",
    )
    if proc.returncode:
        detail = (proc.stderr or proc.stdout)[-6000:]
        raise RuntimeError(f"命令失败 ({proc.returncode}): {detail}")


def _copy_project(source: Path, project: str, work_dir: Path) -> Path:
    source_project = source / ("rmc6236_cadd" if project == "rmc6236" else "reproduction")
    if not source_project.is_dir():
        raise FileNotFoundError(f"未找到项目目录: {source_project}")
    target = work_dir / project
    if not target.exists():
        shutil.copytree(source_project, target)
    return target


def _stage_command(project: str, stage: str, system: str) -> list[str]:
    if project == "rmc6236":
        scripts = {
            "fetch": "01_fetch_reference.py",
            "prepare": "02_prepare_reference.py",
            "redock": "03_redock_reference.py",
            "screen": "04_screen_candidates.py",
            "contacts": "05_analyze_contacts.py",
            "literature": "06_dock_literature_compounds.py",
        }
        script = scripts.get(stage)
        if not script:
            raise ValueError(f"RMC-6236 不支持阶段: {stage}")
        return ["python", f"scripts/{script}"]

    scripts = {
        "download": "01_download_structures.py",
        "prepare": "02_prepare_complex.py",
        "dock": "03_constrained_docking.py",
    }
    script = scripts.get(stage)
    if not script:
        raise ValueError(f"RMC-6291 当前仅支持 download/prepare/dock，收到: {stage}")
    cmd = ["python", f"scripts/{script}"]
    if script != "01_download_structures.py":
        cmd += ["--system", system]
    return cmd


def _collect_results(project_dir: Path) -> dict:
    result: dict = {"project_dir": str(project_dir)}
    json_files = sorted(project_dir.rglob("*.json"))
    for path in json_files[-30:]:
        try:
            result[path.relative_to(project_dir).as_posix()] = json.loads(
                path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            continue
    csv_files = sorted(project_dir.rglob("*.csv"))
    for path in csv_files[-10:]:
        try:
            with path.open(newline="", encoding="utf-8") as fh:
                result[path.relative_to(project_dir).as_posix()] = list(csv.DictReader(fh))
        except (OSError, csv.Error):
            continue
    outputs = [
        p.relative_to(project_dir).as_posix()
        for p in project_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in {".pdb", ".pdbqt", ".sdf", ".txt", ".png"}
    ]
    result["output_files"] = outputs[-300:]
    return result


def run_ras_docking(
    *,
    work_dir: Path,
    params: dict,
    repo_root: Path,
    python_bin: str = "python",
    vina_bin: str = "vina",
    on_stage: Callable[[str], None] | None = None,
) -> RasDockingResult:
    started = time.time()
    project = str(params.get("project", "rmc6236"))
    stage = str(params.get("stage", "literature"))
    system = str(params.get("system", "rmc6291"))
    try:
        if on_stage:
            on_stage("prepare")
        project_dir = _copy_project(repo_root, project, work_dir)
        candidate = params.get("candidate_path")
        if candidate and project == "rmc6236":
            dest = project_dir / "data" / "candidates" / "candidates.sdf"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, dest)

        cmd = _stage_command(project, stage, system)
        cmd[0] = python_bin
        env = os.environ.copy()
        vina_path = Path(vina_bin)
        if vina_path.is_file():
            env["PATH"] = f"{vina_path.parent}{os.pathsep}{env.get('PATH', '')}"
        if on_stage:
            on_stage(stage)
        _run(cmd, project_dir, env, work_dir / "docking.log")
        if on_stage:
            on_stage("analysis")
        result = _collect_results(project_dir)
        return RasDockingResult("ok", "done", time.time() - started, result)
    except Exception as exc:
        return RasDockingResult("failed", stage, time.time() - started, {}, str(exc))
