"""Application configuration from environment."""

from __future__ import annotations

import os
import sys
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
    synthesis_out_root: Path = ROOT / "synthesis_outputs"
    ras_docking_root: Path = ROOT / "external" / "ras-tricomplex-docking"
    ras_docking_out_root: Path = ROOT / "docking_outputs"
    ras_docking_python: str = "python3"
    vina_bin: str = "vina"
    gnina_bin: str = "gnina"
    obabel_bin: str = "/home/pengpai/data/envs/boltz2/bin/obabel"
    docking_out_root: Path = ROOT / "docking_outputs"
    developability_out_root: Path = ROOT / "developability_outputs"
    design_out_root: Path = ROOT / "design_outputs"
    # ProteinMPNN（默认指向本机 RFantibody 内置脚本与权重）
    proteinmpnn_python: str = "/home/pengpai/projects/RFantibody/.venv/bin/python"
    proteinmpnn_script: Path = Path(
        "/home/pengpai/projects/RFantibody/src/rfantibody/proteinmpnn/model/protein_mpnn_run.py"
    )
    proteinmpnn_weights_dir: Path = Path("/home/pengpai/projects/RFantibody/weights")
    proteinmpnn_model_name: str = "ProteinMPNN_v48_noise_0.2"
    rosetta_eval_out_root: Path = ROOT / "rosetta_eval_outputs"
    affinity_redesign_out_root: Path = ROOT / "affinity_redesign_outputs"
    # 算法包默认用仓库内 affinity_redesign/；仍可通过环境变量改到外部目录
    antibody_redesign_root: Path = ROOT
    masking_peptide_out_root: Path = ROOT / "masking_peptide_outputs"
    masking_peptide_project_root: Path = Path(
        "/home/pengpai/data/Company_Project/CD98-23110_masking_peptide"
    )
    rfdiffusion_root: Path = Path("/home/pengpai/data/Company_Project/RFdiffusion")
    se3nv_python: str = "/home/pengpai/data/envs/SE3nv/bin/python"
    rosetta_bin_dir: str = ""
    rosetta_nstruct: int = 3
    rosetta_n_jobs: int = 16
    pyrosetta_python: str = "/home/pengpai/data/envs/pyrosetta/bin/python"
    esm2_3b_path: Path = Path(
        "/home/pengpai/data/cache/torch/hub/checkpoints/esm2_t36_3B_UR50D.pt"
    )
    maxwell_python: str = "/home/pengpai/miniconda3/envs/maxwell/bin/python"
    maxwell_ckpt: Path = Path(
        "/home/pengpai/data/Company_Project/Venus-MAXWELL/weights/esmif-maxwell.ckpt"
    )
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


def affinity_redesign_src_dir() -> Path:
    bundled = ROOT / "affinity_redesign" / "src"
    if bundled.is_dir():
        return bundled
    return Path(settings.antibody_redesign_root) / "affinity_redesign" / "src"


def ensure_affinity_redesign_on_path() -> Path | None:
    src = affinity_redesign_src_dir()
    if not src.is_dir():
        return None
    src_str = str(src)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)
    return src


ensure_affinity_redesign_on_path()

# Ensure output dirs exist
settings.boltz2_out_root.mkdir(parents=True, exist_ok=True)
settings.md_out_root.mkdir(parents=True, exist_ok=True)
settings.maturation_out_root.mkdir(parents=True, exist_ok=True)
settings.synthesis_out_root.mkdir(parents=True, exist_ok=True)
settings.ras_docking_out_root.mkdir(parents=True, exist_ok=True)
settings.docking_out_root.mkdir(parents=True, exist_ok=True)
settings.developability_out_root.mkdir(parents=True, exist_ok=True)
settings.design_out_root.mkdir(parents=True, exist_ok=True)
settings.rosetta_eval_out_root.mkdir(parents=True, exist_ok=True)
settings.affinity_redesign_out_root.mkdir(parents=True, exist_ok=True)
settings.masking_peptide_out_root.mkdir(parents=True, exist_ok=True)
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
os.environ.setdefault("SYNTHESIS_OUT_ROOT", str(settings.synthesis_out_root))
os.environ.setdefault("ESM2_3B_PATH", str(settings.esm2_3b_path))
_rosetta_bin = settings.rosetta_bin_dir or os.environ.get("ROSETTA_BIN") or os.environ.get("ROSETTA3") or ""
if _rosetta_bin:
    os.environ.setdefault("ROSETTA_BIN", _rosetta_bin)
if settings.pyrosetta_python:
    os.environ.setdefault("PYROSETTA_PYTHON", settings.pyrosetta_python)
if settings.rosetta_n_jobs:
    os.environ.setdefault("ROSETTA_N_JOBS", str(settings.rosetta_n_jobs))
