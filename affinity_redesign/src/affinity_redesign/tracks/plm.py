"""序列 PLM 轨：ESM-1b + ESM-1v 共识（Hie et al.）。"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from affinity_redesign.config import settings
from affinity_redesign.schemas import Round1Config

_SRC_ROOT = Path(__file__).resolve().parents[2]  # .../affinity_redesign/src


def score_plm_track(
    campaign_dir: Path,
    config: Round1Config,
    out_dir: Path,
) -> dict:
    """对 candidates_filtered.csv 打分，写出 scores.csv / top_per_chain.csv。"""
    campaign_dir = campaign_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    sequences = campaign_dir / "input" / "sequences.fasta"
    candidates = campaign_dir / "prepare" / "candidates_filtered.csv"
    if not sequences.is_file():
        raise FileNotFoundError(f"缺少序列: {sequences}")
    if not candidates.is_file():
        raise FileNotFoundError(
            f"缺少候选表: {candidates}。请先运行 affinity-redesign init"
        )

    plm = config.plm
    models = ",".join(plm.models)
    cmd = [
        settings.esm_python,
        "-m",
        "affinity_redesign.tracks.plm_worker",
        "--sequences",
        str(sequences),
        "--candidates",
        str(candidates),
        "--out-dir",
        str(out_dir),
        "--models",
        models,
        "--consensus-k",
        str(plm.consensus_k),
        "--dll-threshold",
        "0.0",
        "--top-per-chain",
        str(plm.top_per_chain),
        "--maxrep",
        str(plm.maxrep),
        "--device",
        "auto",
        "--torch-home",
        settings.torch_home,
    ]

    env = os.environ.copy()
    env["TORCH_HOME"] = settings.torch_home
    env["PYTHONPATH"] = (
        str(_SRC_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    ).rstrip(os.pathsep)

    log_path = out_dir / "plm_worker.log"
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
        raise RuntimeError(f"PLM worker 失败 (code={proc.returncode}):\n{tail}")

    result_path = out_dir / "result.json"
    if not result_path.is_file():
        tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
        raise RuntimeError(f"PLM worker 未写出 result.json:\n{tail}")

    return json.loads(result_path.read_text(encoding="utf-8"))
