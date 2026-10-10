"""抗体项目文件的路径与完整性辅助函数。"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from app.core.config import settings


def project_storage_dir(project_id: str) -> Path:
    """返回项目目录；UUID 校验可防止路径穿越。"""
    safe_id = str(uuid.UUID(project_id))
    path = settings.antibody_projects_out_root / safe_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """分块计算文件 SHA-256，避免大文件一次性读入内存。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()
