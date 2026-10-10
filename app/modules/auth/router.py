"""Auth routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.core.models import User
from app.schemas.auth import (
    AdminPasswordReset,
    AdminUserUpdate,
    PasswordChange,
    RegisterOut,
    TokenOut,
    UserCreate,
    UserLogin,
    UserOut,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

PENDING_APPROVAL_MSG = "账号待管理员审批，请联系管理员开通后再登录"
DISABLED_USER_MSG = "账号已被禁用，请联系管理员"


@router.post("/register", response_model=RegisterOut)
def register(body: UserCreate, db: Session = Depends(get_db)):
    if not settings.allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "当前不允许自助注册，请联系管理员创建账号")

    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Username already exists")
    if body.email and db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already exists")

    requires_approval = settings.registration_requires_approval
    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        is_active=not requires_approval,
        is_admin=False,
        account_status="pending" if requires_approval else "active",
        token_version=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    if requires_approval:
        return RegisterOut(
            message="注册成功，请等待管理员审批后再登录",
            username=user.username,
            pending_approval=True,
        )
    token = create_access_token(user.id)
    # 无需审批时仍返回 RegisterOut；前端可提示后直接登录
    return RegisterOut(
        message="注册成功，请登录",
        username=user.username,
        pending_approval=False,
    )


@router.post("/login", response_model=TokenOut)
def login(body: UserLogin, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    if user.account_status == "disabled":
        raise HTTPException(status.HTTP_403_FORBIDDEN, DISABLED_USER_MSG)
    if not user.is_active or user.account_status == "pending":
        raise HTTPException(status.HTTP_403_FORBIDDEN, PENDING_APPROVAL_MSG)
    token = create_access_token(user.id, user.token_version or 1)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


def _bump_token(user: User) -> None:
    user.token_version = int(user.token_version or 1) + 1


def _set_status(user: User, account_status: str) -> None:
    user.account_status = account_status
    user.is_active = account_status == "active"
    if account_status != "active":
        _bump_token(user)


@router.post("/password", response_model=TokenOut)
def change_password(
    body: PasswordChange,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "当前密码不正确")
    if body.old_password == body.new_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "新密码不能与当前密码相同")
    user.password_hash = hash_password(body.new_password)
    _bump_token(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, user.token_version)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    rows = db.scalars(select(User).order_by(User.created_at.asc())).all()
    return [UserOut.model_validate(item) for item in rows]


@router.post("/users/{user_id}/approve", response_model=UserOut)
def approve_user(
    user_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    if user.account_status == "disabled":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该账号已禁用，请先启用")
    user.account_status = "active"
    user.is_active = True
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/users/{user_id}/disable", response_model=UserOut)
def disable_user(
    user_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    if user.id == actor.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能禁用当前登录的管理员")
    _set_status(user, "disabled")
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/users/{user_id}/enable", response_model=UserOut)
def enable_user(
    user_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    user.account_status = "active"
    user.is_active = True
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user_admin(
    user_id: str,
    body: AdminUserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    if user.id == actor.id and not body.is_admin:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能取消自己的管理员权限")
    user.is_admin = body.is_admin
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/users/{user_id}/password", response_model=UserOut)
def reset_user_password(
    user_id: str,
    body: AdminPasswordReset,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    user.password_hash = hash_password(body.new_password)
    _bump_token(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)
