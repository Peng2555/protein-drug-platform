"""FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, decode_token
from app.core.database import get_db
from app.core.models import User

security = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    decoded = decode_access_token(creds.credentials)
    if not decoded:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    user_id, token_version = decoded
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    if int(token_version) != int(user.token_version or 1):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "登录已失效，请重新登录")
    if user.account_status == "disabled" or (not user.is_active and user.account_status == "disabled"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "账号已被禁用，请联系管理员")
    if not user.is_active or user.account_status == "pending":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "账号待管理员审批，请联系管理员开通后再登录")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    return user
