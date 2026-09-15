#!/usr/bin/env python3
"""Initialize database tables and default admin user."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.security import hash_password
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.migrations import run_migrations
from app.core.models import User


def main() -> None:
    print(f"Database: {settings.database_url}")
    Base.metadata.create_all(bind=engine)
    run_migrations()

    db = SessionLocal()
    try:
        existing = db.scalar(select(User).limit(1))
        if existing:
            print(f"Users already exist (e.g. {existing.username}). Skip admin creation.")
            return

        admin = User(
            username=settings.admin_username,
            password_hash=hash_password(settings.admin_password),
            email="admin@local",
            is_active=True,
            is_admin=True,
        )
        db.add(admin)
        db.commit()
        print(f"Created admin user: {settings.admin_username}")
        print(f"Default password: {settings.admin_password}  (change after first login)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
