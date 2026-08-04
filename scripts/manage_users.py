#!/usr/bin/env python3
"""Manage BoltzFold users: list, approve, disable, create."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.auth import hash_password
from app.config import settings
from app.database import SessionLocal
from app.models import User


def _status_label(user: User) -> str:
    if user.is_active:
        return "已启用"
    return "待审批"


def cmd_list(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        q = select(User).order_by(User.created_at.asc())
        if args.pending:
            q = q.where(User.is_active.is_(False))
        users = db.scalars(q).all()
        if not users:
            print("（无用户）" if not args.pending else "（无待审批用户）")
            return 0
        print(f"{'用户名':<20} {'状态':<8} {'管理员':<6} {'邮箱':<24} {'注册时间'}")
        print("-" * 80)
        for u in users:
            email = u.email or "—"
            created = u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "—"
            admin = "是" if u.is_admin else "否"
            print(f"{u.username:<20} {_status_label(u):<8} {admin:<6} {email:<24} {created}")
        if args.pending:
            print(f"\n共 {len(users)} 个待审批。批准: python scripts/manage_users.py approve <用户名>")
        return 0
    finally:
        db.close()


def _get_user(db, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


def cmd_approve(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        user = _get_user(db, args.username)
        if not user:
            print(f"用户不存在: {args.username}", file=sys.stderr)
            return 1
        if user.is_active:
            print(f"用户「{user.username}」已是启用状态")
            return 0
        user.is_active = True
        db.commit()
        print(f"已批准用户「{user.username}」，现在可以登录")
        return 0
    finally:
        db.close()


def cmd_disable(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        user = _get_user(db, args.username)
        if not user:
            print(f"用户不存在: {args.username}", file=sys.stderr)
            return 1
        if user.is_admin and user.username == settings.admin_username:
            print("不能禁用默认管理员账号", file=sys.stderr)
            return 1
        user.is_active = False
        db.commit()
        print(f"已禁用用户「{user.username}」")
        return 0
    finally:
        db.close()


def cmd_create(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        if _get_user(db, args.username):
            print(f"用户名已存在: {args.username}", file=sys.stderr)
            return 1
        user = User(
            username=args.username,
            email=args.email,
            password_hash=hash_password(args.password),
            is_active=not args.pending,
            is_admin=args.admin,
        )
        db.add(user)
        db.commit()
        state = "待审批" if args.pending else "已启用"
        print(f"已创建用户「{user.username}」（{state}）")
        if args.pending:
            print("请执行: python scripts/manage_users.py approve", user.username)
        return 0
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="BoltzFold 用户管理")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="列出用户")
    p_list.add_argument("--pending", action="store_true", help="仅显示待审批用户")
    p_list.set_defaults(func=cmd_list)

    p_approve = sub.add_parser("approve", help="批准用户（启用登录）")
    p_approve.add_argument("username", help="用户名")
    p_approve.set_defaults(func=cmd_approve)

    p_disable = sub.add_parser("disable", help="禁用用户")
    p_disable.add_argument("username", help="用户名")
    p_disable.set_defaults(func=cmd_disable)

    p_create = sub.add_parser("create", help="管理员创建用户")
    p_create.add_argument("username", help="用户名")
    p_create.add_argument("password", help="初始密码")
    p_create.add_argument("--email", default=None, help="邮箱（可选）")
    p_create.add_argument("--admin", action="store_true", help="设为管理员")
    p_create.add_argument(
        "--pending",
        action="store_true",
        help="创建为待审批状态（默认直接启用）",
    )
    p_create.set_defaults(func=cmd_create)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
