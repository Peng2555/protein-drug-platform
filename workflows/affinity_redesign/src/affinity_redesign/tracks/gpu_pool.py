"""选择当前空闲的 GPU，供 Boltz2 多卡并行。"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _parse_cuda_visible() -> list[int] | None:
    raw = os.environ.get("CUDA_VISIBLE_DEVICES")
    if raw is None or raw.strip() == "":
        return None
    ids: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return ids or None


def _query_nvidia_smi() -> list[dict]:
    bin_path = shutil.which("nvidia-smi")
    if not bin_path:
        return []
    proc = subprocess.run(
        [
            bin_path,
            "--query-gpu=index,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return []
    rows: list[dict] = []
    for line in proc.stdout.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            rows.append(
                {
                    "index": int(parts[0]),
                    "mem_used_mib": float(parts[1]),
                    "util": float(parts[2]),
                }
            )
        except ValueError:
            continue
    return rows


def select_idle_gpu_ids(
    *,
    max_gpus: int | None = None,
    mem_used_max_mib: float = 5000.0,
    util_max: float = 20.0,
) -> list[int]:
    """有几张空卡返回几张；本进程已绑定的卡始终纳入。"""
    cap = max_gpus
    if cap is None:
        try:
            cap = int(os.environ.get("CELERY_GPU_COUNT") or os.environ.get("AFFINITY_REDESIGN_GPUS") or "4")
        except ValueError:
            cap = 4
    cap = max(1, cap)

    assigned = _parse_cuda_visible()
    ours = assigned[0] if assigned else None
    smi = _query_nvidia_smi()

    idle: list[int] = []
    if smi:
        for row in smi:
            idx = int(row["index"])
            if ours is not None and idx == ours:
                continue
            if row["mem_used_mib"] <= mem_used_max_mib and row["util"] <= util_max:
                idle.append(idx)
        chosen: list[int] = []
        if ours is not None:
            chosen.append(ours)
        for idx in idle:
            if idx not in chosen:
                chosen.append(idx)
            if len(chosen) >= cap:
                break
        if chosen:
            return chosen[:cap]
        if ours is not None:
            return [ours]
        return [int(smi[0]["index"])]

    if assigned:
        return assigned[:cap]
    return [0]


def write_pool_status(path: Path, gpu_ids: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    assigned = _parse_cuda_visible()
    smi = _query_nvidia_smi()
    payload = {
        "gpu_ids": gpu_ids,
        "n_gpus": len(gpu_ids),
        "cuda_visible_devices": assigned,
        "nvidia_smi": smi,
    }
    import json

    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
