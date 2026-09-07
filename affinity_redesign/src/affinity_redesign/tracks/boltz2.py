"""Boltz2 复合物预测封装（subprocess 到 boltz2 env）。"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from affinity_redesign.config import settings

_SRC_ROOT = Path(__file__).resolve().parents[2]


def fold_complex(
    fasta: Path,
    out_root: Path,
    job_id: str,
    *,
    use_msa_server: bool = True,
    recycling_steps: int = 3,
    sampling_steps: int = 200,
    diffusion_samples: int = 10,
    gpu_id: int | None = None,
) -> dict:
    out_root.mkdir(parents=True, exist_ok=True)
    result_path = out_root / job_id / "fold_result.json"
    if result_path.is_file():
        data = json.loads(result_path.read_text(encoding="utf-8"))
        n_have = int(data.get("n_samples") or 0)
        if n_have < 1:
            metrics_path = out_root / job_id / "metrics.json"
            if metrics_path.is_file():
                try:
                    n_have = int(json.loads(metrics_path.read_text(encoding="utf-8")).get("n_samples") or 1)
                except json.JSONDecodeError:
                    n_have = 1
            else:
                n_have = 1
        if (
            data.get("status") == "ok"
            and data.get("pred_pdb")
            and Path(data["pred_pdb"]).is_file()
            and n_have >= int(diffusion_samples or 1)
        ):
            return data

    cmd = [
        settings.boltz2_python,
        "-m",
        "affinity_redesign.tracks.boltz2_worker",
        "--fasta",
        str(fasta),
        "--out-root",
        str(out_root),
        "--job-id",
        job_id,
        "--recycling-steps",
        str(recycling_steps),
        "--sampling-steps",
        str(sampling_steps),
        "--diffusion-samples",
        str(diffusion_samples),
    ]
    if use_msa_server:
        cmd.append("--use-msa-server")

    env = os.environ.copy()
    if gpu_id is not None:
        env["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    env["PYTHONPATH"] = (
        str(_SRC_ROOT) + os.pathsep + str(settings.boltz2_root / "scripts") + os.pathsep + env.get("PYTHONPATH", "")
    ).rstrip(os.pathsep)

    log_path = out_root / job_id
    log_path.mkdir(parents=True, exist_ok=True)
    log_file = log_path / "fold.log"
    with log_file.open("w", encoding="utf-8") as log_f:
        proc = subprocess.run(
            cmd,
            env=env,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    if proc.returncode != 0 or not result_path.is_file():
        tail = log_file.read_text(encoding="utf-8", errors="replace")[-4000:]
        raise RuntimeError(f"Boltz2 fold {job_id} 失败 (code={proc.returncode}):\n{tail}")
    return json.loads(result_path.read_text(encoding="utf-8"))
