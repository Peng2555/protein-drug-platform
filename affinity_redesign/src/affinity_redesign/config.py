"""从环境变量读取模型路径与运行根目录。"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PKG_ROOT = Path(__file__).resolve().parents[3]
_PARENT = _PKG_ROOT.parent
_BOLTZ_ROOT = _PARENT if (_PARENT / "app" / "config.py").is_file() else Path("/home/pengpai/data/Company_Project/Boltz2")
_ENV_FILE = _BOLTZ_ROOT / ".env" if (_BOLTZ_ROOT / ".env").is_file() else _PKG_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.is_file() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    esm_python: str = "/home/pengpai/data/envs/boltz2/bin/python"
    esm2_3b_path: Path = Path(
        "/home/pengpai/data/cache/torch/hub/checkpoints/esm2_t36_3B_UR50D.pt"
    )
    torch_home: str = "/home/pengpai/data/cache/torch"
    # fair-esm 权重目录（esm1b / esm1v_*）
    esm_checkpoint_dir: Path = Path("/home/pengpai/data/cache/torch/hub/checkpoints")

    antifold_python: str = "/home/pengpai/miniconda3/envs/maxwell/bin/python"
    antifold_root: Path = Path("/home/pengpai/data/Company_Project/AntiFold")

    anarci_python: str = "/home/pengpai/data/envs/IgGM/bin/python"
    hmmer_path: str = "/home/pengpai/data/envs/IgGM/bin"

    boltz2_python: str = "/home/pengpai/data/envs/boltz2/bin/python"
    boltz2_root: Path = _BOLTZ_ROOT
    boltz2_out_root: Path = _BOLTZ_ROOT / "outputs"

    pyrosetta_python: str = "/home/pengpai/data/envs/pyrosetta/bin/python"

    affinity_runs_root: Path = _BOLTZ_ROOT / "affinity_redesign_outputs"


settings = Settings()
settings.affinity_runs_root.mkdir(parents=True, exist_ok=True)
