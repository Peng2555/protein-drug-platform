"""Auth routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import create_access_token, hash_password, verify_password
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import RegisterOut, TokenOut, UserCreate, UserLogin, UserOut

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
    if not user.is_active:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            PENDING_APPROVAL_MSG,
        )
    token = create_access_token(user.id)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)
