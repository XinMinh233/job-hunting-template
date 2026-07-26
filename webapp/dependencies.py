from __future__ import annotations

import datetime as dt
import secrets
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import User, WebSession, utcnow
from .security import token_hash

SESSION_COOKIE = "jh_session"
CSRF_HEADER = "X-CSRF-Token"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@dataclass
class Principal:
    user: User
    session: WebSession


def _aware(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value


def get_principal(
    request: Request, db: Session = Depends(get_db)
) -> Principal:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    web_session = db.scalar(
        select(WebSession).where(WebSession.token_hash == token_hash(raw))
    )
    if not web_session or _aware(web_session.expires_at) <= utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    user = db.get(User, web_session.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    web_session.last_seen_at = utcnow()
    db.commit()
    return Principal(user=user, session=web_session)


def get_ready_principal(
    principal: Principal = Depends(get_principal),
) -> Principal:
    if principal.user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "password_change_required", "message": "请先修改密码"},
        )
    return principal


def get_admin(
    principal: Principal = Depends(get_ready_principal),
) -> Principal:
    if principal.user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return principal


def require_csrf(
    request: Request, principal: Principal = Depends(get_principal)
) -> Principal:
    supplied = request.headers.get(CSRF_HEADER, "")
    if not supplied or not secrets.compare_digest(
        supplied, principal.session.csrf_token
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "csrf_failed", "message": "请求验证失败，请刷新页面"},
        )
    return principal


def require_ready_csrf(
    principal: Principal = Depends(require_csrf),
) -> Principal:
    if principal.user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "password_change_required", "message": "请先修改密码"},
        )
    return principal


def require_admin_csrf(
    principal: Principal = Depends(require_ready_csrf),
) -> Principal:
    if principal.user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return principal

