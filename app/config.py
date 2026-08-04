"""Application configuration from environment."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite:///{ROOT / 'data' / 'boltzfold.db'}"
    redis_url: str = "redis://127.0.0.1:6380/0"
    secret_key: str = "dev-secret-change-in-production"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    boltz2_out_root: Path = ROOT / "outputs"
    boltz_cache: str = "/home/pengpai/data/cache/boltz"
    hf_home: str = "/home/pengpai/data/cache/huggingface"
    torch_home: str = "/home/pengpai/data/cache/torch"
    boltz_bin: str = "/home/pengpai/data/envs/boltz2/bin/boltz"
    dockq_python: str = "/home/pengpai/data/envs/dockq/bin/python"
    esmfold_py: str = "/home/pengpai/data/envs/esmfold2/bin/python"
    esmfold_model: str = "biohub/ESMFold2"

    admin_username: str = "admin"
    admin_password: str = "admin123"

    # 允许自助注册；新用户默认 is_active=False，需管理员审批（scripts/manage_users.py approve）
    allow_registration: bool = True
    registration_requires_approval: bool = True

    max_total_sequence_length: int = 4000
    # 0 = no cap on queued jobs; workers keep pulling until queue empty
    max_jobs_per_user_queued: int = 0
    max_jobs_per_user_running: int = 0  # legacy alias; 0 = do not block submit
    max_vhh_panel_size: int = 5000
    celery_gpu_count: int = 4
    celery_gpu_queue: str = "gpu"  # unified queue: fold + MD share all GPUs

    md_out_root: Path = ROOT / "md_outputs"
    maturation_out_root: Path = ROOT / "maturation_outputs"
    gmx_bin: str = "/home/pengpai/data/envs/IgGM/bin/gmx"
    gemmi_py: str = "/home/pengpai/data/envs/IgGM/bin/python"
    iggm_py: str = "/home/pengpai/data/envs/IgGM/bin/python"
    iggm_root: str = "/home/pengpai/data/Company_Project/IgGM"
    md_production_ns: float = 1.0
    md_replicas: int = 1
    md_parallel_replicas: bool = True  # run multiple replicas on different GPUs when idle
    max_md_jobs_per_user_running: int = 0

    api_host: str = "0.0.0.0"
    api_port: int = 8765


settings = Settings()

# Ensure output dirs exist
settings.boltz2_out_root.mkdir(parents=True, exist_ok=True)
settings.md_out_root.mkdir(parents=True, exist_ok=True)
settings.maturation_out_root.mkdir(parents=True, exist_ok=True)
(ROOT / "data").mkdir(parents=True, exist_ok=True)

# Propagate cache env vars for boltz subprocess
os.environ.setdefault("BOLTZ2_OUT_ROOT", str(settings.boltz2_out_root))
os.environ.setdefault("BOLTZ_CACHE", settings.boltz_cache)
os.environ.setdefault("HF_HOME", settings.hf_home)
os.environ.setdefault("TORCH_HOME", settings.torch_home)
os.environ.setdefault("BOLTZ_BIN", settings.boltz_bin)
os.environ.setdefault("DOCKQ_PYTHON", settings.dockq_python)
os.environ.setdefault("ESMFOLD_PY", settings.esmfold_py)
os.environ.setdefault("ESMFOLD_MODEL", settings.esmfold_model)
os.environ.setdefault("GMX_BIN", settings.gmx_bin)
os.environ.setdefault("GEMMI_PY", settings.gemmi_py)
os.environ.setdefault("IGGM_PY", settings.iggm_py)
os.environ.setdefault("IGGM_ROOT", settings.iggm_root)
os.environ.setdefault("MD_OUT_ROOT", str(settings.md_out_root))
os.environ.setdefault("MATURATION_OUT_ROOT", str(settings.maturation_out_root))
