"""不依赖任一算法包的共享运行时配置。"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_SHARED_ROOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = _SHARED_ROOT.parent
_FALLBACK_ROOT = Path("/home/pengpai/data/Company_Project/Boltz2")
_BOLTZ_ROOT = _REPO_ROOT if (_REPO_ROOT / "app" / "config.py").is_file() else _FALLBACK_ROOT
_ENV_FILE = _BOLTZ_ROOT / ".env" if (_BOLTZ_ROOT / ".env").is_file() else _SHARED_ROOT / ".env"


class RuntimeSettings(BaseSettings):
    """只包含共享算法运行时所需的稳定配置键。"""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.is_file() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anarci_python: str = "/home/pengpai/data/envs/IgGM/bin/python"
    hmmer_path: str = "/home/pengpai/data/envs/IgGM/bin"
    boltz2_python: str = "/home/pengpai/data/envs/boltz2/bin/python"
    boltz2_root: Path = _BOLTZ_ROOT


settings = RuntimeSettings()
