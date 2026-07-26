from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .audit import audit
from .dependencies import (
    Principal,
    get_admin,
    get_db,
    require_admin_csrf,
)
from .jobs import job_manager, user_job_locks
from .models import AuditLog, DailyUsage, Job, User, WebSession
from .runner_client import RunnerError, runner_client
from .schemas import AdminQuotaIn, AdminResetPasswordIn, AdminUserCreateIn
from .security import USERNAME_RE, generate_password, password_hash
from .time_utils import quota_day

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
def list_users(
    _principal: Principal = Depends(get_admin),
    db: Session = Depends(get_db),
):
    users = list(db.scalars(select(User).order_by(User.created_at)))
    today = {
        usage.user_id: usage
        for usage in db.scalars(
            select(DailyUsage).where(DailyUsage.day == quota_day())
        )
    }
    return [
        {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "is_active": user.is_active,
            "must_change_password": user.must_change_password,
            "linux_username": user.linux_username,
            "template_version": user.template_version,
            "daily_job_limit": user.daily_job_limit,
            "daily_token_limit": user.daily_token_limit,
            "jobs_today": today.get(user.id).jobs if user.id in today else 0,
            "tokens_today": (
                today.get(user.id).total_tokens if user.id in today else 0
            ),
        }
        for user in users
    ]


@router.post("/users")
async def create_user(
    payload: AdminUserCreateIn,
    principal: Principal = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
):
    username = payload.username.strip().lower()
    if not USERNAME_RE.fullmatch(username):
        raise HTTPException(
            status_code=400,
            detail="用户名只能包含字母、数字、点、横线和下划线",
        )
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(status_code=409, detail="用户名已存在")
    temporary_password = generate_password()
    user = User(
        username=username,
        password_hash=password_hash(temporary_password),
        role="user",
        daily_job_limit=payload.daily_job_limit,
        daily_token_limit=payload.daily_token_limit,
        must_change_password=True,
    )
    db.add(user)
    db.flush()
    try:
        provisioned = await runner_client.request(
            "provision", user_id=user.id
        )
    except RunnerError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    user.linux_username = provisioned["linux_username"]
    user.workspace_path = provisioned["workspace_path"]
    user.template_version = provisioned["template_version"]
    audit(
        db,
        "admin.user_created",
        actor_user_id=principal.user.id,
        target=user.id,
        detail={"username": username},
    )
    db.commit()
    return {
        "id": user.id,
        "username": user.username,
        "temporary_password": temporary_password,
        "message": "临时密码只显示一次，请立即安全地交给用户",
    }


@router.post("/users/{user_id}/disable")
async def disable_user(
    user_id: str,
    principal: Principal = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user or user.role == "admin":
        raise HTTPException(status_code=404)
    async with user_job_locks[user_id]:
        active_job_ids = list(
            db.scalars(
                select(Job.id).where(
                    Job.user_id == user_id,
                    Job.state.in_(("queued", "running")),
                )
            )
        )
        for job_id in active_job_ids:
            await job_manager.stop(
                job_id,
                user_id,
                actor_user_id=principal.user.id,
            )
        await runner_client.request("disable", user_id=user_id)
        user.is_active = False
        db.execute(delete(WebSession).where(WebSession.user_id == user_id))
        audit(
            db,
            "admin.user_disabled",
            actor_user_id=principal.user.id,
            target=user_id,
        )
        db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/enable")
async def enable_user(
    user_id: str,
    principal: Principal = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user or user.role == "admin":
        raise HTTPException(status_code=404)
    await runner_client.request("enable", user_id=user_id)
    user.is_active = True
    audit(
        db,
        "admin.user_enabled",
        actor_user_id=principal.user.id,
        target=user_id,
    )
    db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/reset-password")
def reset_password(
    user_id: str,
    payload: AdminResetPasswordIn,
    principal: Principal = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404)
    temporary = generate_password()
    user.password_hash = password_hash(temporary)
    user.must_change_password = payload.force_change
    db.execute(delete(WebSession).where(WebSession.user_id == user_id))
    audit(
        db,
        "admin.password_reset",
        actor_user_id=principal.user.id,
        target=user_id,
    )
    db.commit()
    return {"temporary_password": temporary}


@router.put("/users/{user_id}/quota")
def update_quota(
    user_id: str,
    payload: AdminQuotaIn,
    principal: Principal = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404)
    user.daily_job_limit = payload.daily_job_limit
    user.daily_token_limit = payload.daily_token_limit
    audit(
        db,
        "admin.quota_updated",
        actor_user_id=principal.user.id,
        target=user_id,
        detail=(
            payload.model_dump()
            if hasattr(payload, "model_dump")
            else payload.dict()
        ),
    )
    db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/upgrade-template")
async def upgrade_template(
    user_id: str,
    principal: Principal = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404)
    async with user_job_locks[user_id]:
        active_job = db.scalar(
            select(Job.id).where(
                Job.user_id == user_id,
                Job.state.in_(("queued", "running")),
            )
        )
        if active_job:
            raise HTTPException(
                status_code=409,
                detail="用户仍有任务运行或排队，不能升级模板",
            )
        try:
            result = await runner_client.request("upgrade", user_id=user_id)
        except RunnerError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        user.template_version = result["version"]
        audit(
            db,
            "admin.template_upgraded",
            actor_user_id=principal.user.id,
            target=user_id,
            detail={
                "version": result["version"],
                "conflicts": result["conflicts"],
            },
        )
        db.commit()
    return result


@router.get("/jobs")
def list_jobs(
    _principal: Principal = Depends(get_admin),
    db: Session = Depends(get_db),
):
    jobs = list(db.scalars(select(Job).order_by(Job.created_at.desc()).limit(100)))
    return [
        {
            "id": job.id,
            "user_id": job.user_id,
            "chat_id": job.chat_id,
            "state": job.state,
            "created_at": job.created_at.isoformat(),
            "error": job.error,
        }
        for job in jobs
    ]


@router.post("/jobs/{job_id}/stop")
async def admin_stop_job(
    job_id: str,
    principal: Principal = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404)
    async with user_job_locks[job.user_id]:
        await job_manager.stop(
            job_id,
            job.user_id,
            actor_user_id=principal.user.id,
        )
    audit(
        db,
        "admin.job_stopped",
        actor_user_id=principal.user.id,
        target=job_id,
    )
    db.commit()
    return {"ok": True}


@router.get("/audit")
def list_audit(
    _principal: Principal = Depends(get_admin),
    db: Session = Depends(get_db),
):
    logs = list(
        db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(200))
    )
    return [
        {
            "id": item.id,
            "actor_user_id": item.actor_user_id,
            "action": item.action,
            "target": item.target,
            "detail": json.loads(item.detail_json),
            "created_at": item.created_at.isoformat(),
        }
        for item in logs
    ]
