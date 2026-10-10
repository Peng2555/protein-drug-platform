"""把 Boltz2 predict 转到昇腾 npu-3（scripts/npu_fold），本机不占 NVIDIA GPU。"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUBMIT_SH = ROOT / "scripts" / "npu_fold" / "submit_one.sh"


def npu_remote_enabled() -> bool:
    raw = os.environ.get("BOLTZ_NPU_REMOTE", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _flag(value: bool) -> str:
    return "1" if value else "0"


def remote_job_id(out_dir: Path) -> str:
    """远程目录必须带上任务路径。只取最后一级时，疏水/CIC/画像都会叫 WT，互相覆盖。"""
    resolved = out_dir.resolve()
    tail = resolved.parts[-3:] if len(resolved.parts) >= 3 else resolved.parts
    raw = "__".join(tail)
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in raw).strip("_.")
    return (safe or "fold")[:120]


def run_boltz_predict_npu(
    yaml_path: Path,
    out_dir: Path,
    *,
    use_msa_server: bool = True,
    recycling_steps: int = 3,
    sampling_steps: int = 200,
    diffusion_samples: int = 1,
    max_parallel_samples: int | None = 5,
    max_msa_seqs: int = 8192,
    subsample_msa: bool = False,
    num_subsampled_msa: int = 1024,
    **_ignored,
) -> subprocess.CompletedProcess:
    """调用 submit_one.sh；结果 rsync 进 out_dir，供 extract_metrics 扫描。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = Path(yaml_path)
    job_id = remote_job_id(out_dir)
    env = os.environ.copy()
    env["NPU_SSH_HOST"] = env.get("NPU_SSH_HOST") or env.get("BOLTZ_NPU_SSH_HOST") or "npu-3"
    env["USE_MSA_SERVER"] = _flag(bool(use_msa_server))
    env["RECYCLING_STEPS"] = str(int(recycling_steps))
    env["SAMPLING_STEPS"] = str(int(sampling_steps))
    env["DIFFUSION_SAMPLES"] = str(int(diffusion_samples))
    env["MAX_PARALLEL_SAMPLES"] = str(int(max_parallel_samples if max_parallel_samples is not None else 5))
    env["MAX_MSA_SEQS"] = str(int(max_msa_seqs))
    env["SUBSAMPLE_MSA"] = _flag(bool(subsample_msa))
    env["NUM_SUBSAMPLED_MSA"] = str(int(num_subsampled_msa))
    env["DRY_RUN"] = "0"

    cmd = [
        "bash",
        str(SUBMIT_SH),
        "--job-id",
        job_id,
        "--yaml",
        str(yaml_path),
        "--device",
        "auto",
        "--local-out",
        str(out_dir),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    log_path = out_dir / "log.txt"
    combined = "\n".join(filter(None, [proc.stdout, proc.stderr]))
    if log_path.is_file():
        combined = (combined + "\n" + log_path.read_text(encoding="utf-8", errors="replace")).strip()
    if proc.returncode != 0:
        (out_dir / "error.log").write_text(combined[-8000:], encoding="utf-8")
    return subprocess.CompletedProcess(cmd, proc.returncode, combined, proc.stderr or "")
