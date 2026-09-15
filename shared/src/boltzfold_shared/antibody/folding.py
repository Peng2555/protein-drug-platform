"""不依赖具体算法包的 Boltz2 抗体折叠适配。"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from boltzfold_shared.runtime.settings import settings


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
    """通过 shared 自有 worker 调用平台 Boltz2 runner。"""
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
        settings.boltz2_python, "-m", "boltzfold_shared.antibody.boltz2_worker",
        "--fasta", str(fasta), "--out-root", str(out_root), "--job-id", job_id,
        "--recycling-steps", str(recycling_steps), "--sampling-steps", str(sampling_steps),
        "--diffusion-samples", str(diffusion_samples),
    ]
    if use_msa_server:
        cmd.append("--use-msa-server")
    env = os.environ.copy()
    if gpu_id is not None:
        env["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    shared_src = Path(__file__).resolve().parents[2]
    env["PYTHONPATH"] = (
        str(shared_src) + os.pathsep + str(settings.boltz2_root / "scripts")
        + os.pathsep + env.get("PYTHONPATH", "")
    ).rstrip(os.pathsep)
    log_path = out_root / job_id
    log_path.mkdir(parents=True, exist_ok=True)
    log_file = log_path / "fold.log"
    with log_file.open("w", encoding="utf-8") as log_handle:
        proc = subprocess.run(
            cmd, env=env, stdout=log_handle, stderr=subprocess.STDOUT, text=True, check=False
        )
    if proc.returncode != 0 or not result_path.is_file():
        tail = log_file.read_text(encoding="utf-8", errors="replace")[-4000:]
        raise RuntimeError(f"Boltz2 fold {job_id} 失败 (code={proc.returncode}):\n{tail}")
    return json.loads(result_path.read_text(encoding="utf-8"))


def fold_antibody(fasta: Path, fold_root: Path, job_id: str = "WT") -> Path:
    """使用三个工作流既有的固定 Boltz2 参数折叠抗体。"""
    data = fold_complex(
        fasta, fold_root, job_id, use_msa_server=True,
        recycling_steps=3, sampling_steps=200, diffusion_samples=3,
    )
    if data.get("status") != "ok":
        raise RuntimeError(data.get("error") or "Boltz2 折抗体失败")
    prediction = data.get("pred_pdb") or data.get("pred_cif")
    if not prediction or not Path(prediction).is_file():
        raise RuntimeError("Boltz2 未产出 pred.pdb/cif")
    return Path(prediction)
