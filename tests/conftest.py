"""平台测试的隔离数据库夹具。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import Base
from app.models import User


@pytest.fixture
def sqlite_sessions(tmp_path: Path):
    """每个测试使用独立 SQLite 文件，以便验证跨 session 可见性。"""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def active_user(sqlite_sessions):
    with sqlite_sessions() as db:
        user = User(
            username="phase2-user",
            email="phase2@example.test",
            password_hash="not-used",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
        return user
