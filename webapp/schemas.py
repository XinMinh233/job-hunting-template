from __future__ import annotations

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=512)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=12, max_length=512)


class ChatCreateIn(BaseModel):
    title: str = Field(default="新会话", min_length=1, max_length=160)


class MessageCreateIn(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)


class AdminUserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    daily_job_limit: int = Field(default=30, ge=1, le=1000)
    daily_token_limit: int = Field(default=1_000_000, ge=10_000, le=1_000_000_000)


class AdminQuotaIn(BaseModel):
    daily_job_limit: int = Field(ge=1, le=1000)
    daily_token_limit: int = Field(ge=10_000, le=1_000_000_000)


class AdminResetPasswordIn(BaseModel):
    force_change: bool = True

