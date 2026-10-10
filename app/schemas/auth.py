"""Authentication schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    email: str | None = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: str
    username: str
    email: str | None
    is_active: bool = True
    is_admin: bool = False
    account_status: str = "active"
    created_at: datetime

    model_config = {"from_attributes": True}


class PasswordChange(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


class AdminPasswordReset(BaseModel):
    new_password: str = Field(min_length=6, max_length=128)


class AdminUserUpdate(BaseModel):
    is_admin: bool


class RegisterOut(BaseModel):
    message: str
    username: str
    pending_approval: bool = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
