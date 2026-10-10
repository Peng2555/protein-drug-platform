"""Boltz2 process environment and CLI execution."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

BOLTZ_BIN = Path(os.environ.get("BOLTZ_BIN", "/home/pengpai/data/envs/boltz2/bin/boltz"))


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


def boltz_run_error(out_dir: Path, proc: subprocess.CompletedProcess) -> str:
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


_boltz_run_error = boltz_run_error
