from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .audit import audit
from .config import settings
from .dependencies import (
    SESSION_COOKIE,
    Principal,
    get_db,
    get_principal,
    require_csrf,
)
from .models import LoginAttempt, User, WebSession, utcnow
from .schemas import LoginIn, PasswordChangeIn
from .security import (
    generate_csrf_token,
    generate_session_token,
    identity_hash,
    password_hash,
    token_hash,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
_DUMMY_PASSWORD_HASH = password_hash("dummy-password-for-timing-only")


def _client_ip(request: Request) -> str:
    # 仅信任 Caddy 覆盖的第一跳；生产 Caddy 会重写而非透传客户端自造值。
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/login")
def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    username = payload.username.strip().lower()
    fingerprint = identity_hash(username, _client_ip(request))
    cutoff = utcnow() - dt.timedelta(minutes=15)
    failures = db.scalar(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.identity_hash == fingerprint,
            LoginAttempt.succeeded.is_(False),
            LoginAttempt.created_at >= cutoff,
        )
    )
    if (failures or 0) >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录失败次数过多，请 15 分钟后再试",
        )

    user = db.scalar(select(User).where(User.username == username))
    candidate_hash = user.password_hash if user else _DUMMY_PASSWORD_HASH
    password_valid = verify_password(candidate_hash, payload.password)
    valid = bool(user and user.is_active and password_valid)
    db.add(LoginAttempt(identity_hash=fingerprint, succeeded=valid))
    if not valid:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    raw_token = generate_session_token()
    expires = utcnow() + dt.timedelta(days=settings.session_days)
    web_session = WebSession(
        user_id=user.id,
        token_hash=token_hash(raw_token),
        csrf_token=generate_csrf_token(),
        expires_at=expires,
    )
    db.add(web_session)
    audit(db, "auth.login", actor_user_id=user.id, target=user.username)
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        raw_token,
        max_age=settings.session_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return {
        "ok": True,
        "must_change_password": user.must_change_password,
        "csrf_token": web_session.csrf_token,
    }


@router.post("/logout")
def logout(
    response: Response,
    principal: Principal = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    db.execute(delete(WebSession).where(WebSession.id == principal.session.id))
    audit(
        db,
        "auth.logout",
        actor_user_id=principal.user.id,
        target=principal.user.username,
    )
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(principal: Principal = Depends(get_principal)):
    user = principal.user
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "must_change_password": user.must_change_password,
        "csrf_token": principal.session.csrf_token,
        "daily_job_limit": user.daily_job_limit,
        "daily_token_limit": user.daily_token_limit,
    }


@router.post("/change-password")
def change_password(
    payload: PasswordChangeIn,
    principal: Principal = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    if not verify_password(
        principal.user.password_hash, payload.current_password
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前密码错误",
        )
    try:
        principal.user.password_hash = password_hash(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    principal.user.must_change_password = False
    db.execute(
        delete(WebSession).where(
            WebSession.user_id == principal.user.id,
            WebSession.id != principal.session.id,
        )
    )
    audit(
        db,
        "auth.password_changed",
        actor_user_id=principal.user.id,
        target=principal.user.username,
    )
    db.commit()
    return {"ok": True}
