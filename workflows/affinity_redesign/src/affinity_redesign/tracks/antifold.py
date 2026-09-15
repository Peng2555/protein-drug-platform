"""结构轨：AntiFold（默认）或 ESM-IF1 复合物 inverse folding 打分。"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from affinity_redesign.config import settings
from affinity_redesign.schemas import Round1Config

_SRC_ROOT = Path(__file__).resolve().parents[2]  # .../affinity_redesign/src


def score_structure_track(
    campaign_dir: Path,
    config: Round1Config,
    out_dir: Path,
) -> dict:
    """对 candidates_filtered.csv 做结构轨打分，写出 scores / top_per_chain。"""
    campaign_dir = campaign_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    sequences = campaign_dir / "input" / "sequences.fasta"
    candidates = campaign_dir / "prepare" / "candidates_filtered.csv"
    struct_rel = config.structure.path or "input/complex.pdb"
    pdb_path = (campaign_dir / struct_rel).resolve()

    if not sequences.is_file():
        raise FileNotFoundError(f"缺少序列: {sequences}")
    if not candidates.is_file():
        raise FileNotFoundError(
            f"缺少候选表: {candidates}。请先运行 affinity-redesign init"
        )
    if not pdb_path.is_file():
        raise FileNotFoundError(f"缺少复合物结构: {pdb_path}")

    st = config.structure_track
    engine = st.engine
    esm_if1 = engine == "esm_if1"

    heavy = config.chains.heavy
    light = config.chains.light or ""
    antigen = config.chains.antigen or ""

    cmd = [
        settings.antifold_python,
        "-m",
        "affinity_redesign.tracks.antifold_worker",
        "--pdb",
        str(pdb_path),
        "--sequences",
        str(sequences),
        "--candidates",
        str(candidates),
        "--out-dir",
        str(out_dir),
        "--heavy",
        heavy,
        "--light",
        light,
        "--antigen",
        antigen,
        "--antifold-root",
        str(settings.antifold_root),
        "--dll-threshold",
        str(getattr(st, "dll_threshold", 0.0)),
        "--top-per-chain",
        str(st.top_per_chain),
        "--maxrep",
        str(st.maxrep),
        "--torch-home",
        settings.torch_home,
    ]
    if esm_if1:
        cmd.append("--esm-if1-mode")

    env = os.environ.copy()
    env["TORCH_HOME"] = settings.torch_home
    env["PYTHONPATH"] = (
        str(_SRC_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    ).rstrip(os.pathsep)

    log_path = out_dir / "structure_worker.log"
    with log_path.open("w", encoding="utf-8") as log_f:
        proc = subprocess.run(
            cmd,
            cwd=str(campaign_dir),
            env=env,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )

    if proc.returncode != 0:
        tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
        raise RuntimeError(f"结构轨 worker 失败 (code={proc.returncode}):\n{tail}")

    result_path = out_dir / "result.json"
    if not result_path.is_file():
        tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
        raise RuntimeError(f"结构轨 worker 未写出 result.json:\n{tail}")

    return json.loads(result_path.read_text(encoding="utf-8"))
