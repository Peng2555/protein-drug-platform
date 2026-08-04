#!/usr/bin/env python3
"""Rehash user passwords with current bcrypt rounds (faster login after upgrade)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.auth import hash_password
from app.config import settings
from app.database import SessionLocal
from app.models import User


def main() -> None:
    db = SessionLocal()
    try:
        users = db.scalars(select(User)).all()
        if not users:
            print("No users found.")
            return
        for user in users:
            if user.username == settings.admin_username:
                user.password_hash = hash_password(settings.admin_password)
                print(f"Rehashed admin ({settings.admin_username})")
            else:
                print(f"Skip {user.username} (only admin auto-reset; register again or extend script)")
        db.commit()
        print("Done. Admin password unchanged:", settings.admin_password)
    finally:
        db.close()


if __name__ == "__main__":
    main()
