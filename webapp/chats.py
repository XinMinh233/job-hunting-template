from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .dependencies import (
    Principal,
    get_db,
    get_ready_principal,
    require_ready_csrf,
)
from .jobs import (
    create_job,
    event_stream,
    job_manager,
    quota_status,
    user_job_locks,
)
from .models import Chat, Job, Message
from .schemas import ChatCreateIn, MessageCreateIn

router = APIRouter(prefix="/api", tags=["chats"])


def _owned_chat(db: Session, chat_id: str, user_id: str) -> Chat:
    chat = db.get(Chat, chat_id)
    if not chat or chat.user_id != user_id:
        raise HTTPException(status_code=404)
    return chat


@router.get("/chats")
def list_chats(
    principal: Principal = Depends(get_ready_principal),
    db: Session = Depends(get_db),
):
    chats = list(
        db.scalars(
            select(Chat)
            .where(Chat.user_id == principal.user.id, Chat.is_archived.is_(False))
            .order_by(Chat.updated_at.desc())
        )
    )
    return [
        {
            "id": chat.id,
            "title": chat.title,
            "claude_session_id": bool(chat.claude_session_id),
            "updated_at": chat.updated_at.isoformat(),
            "active_job_id": db.scalar(
                select(Job.id)
                .where(
                    Job.chat_id == chat.id,
                    Job.state.in_(("queued", "running")),
                )
                .order_by(Job.created_at.desc())
                .limit(1)
            ),
        }
        for chat in chats
    ]


@router.post("/chats")
def create_chat(
    payload: ChatCreateIn,
    principal: Principal = Depends(require_ready_csrf),
    db: Session = Depends(get_db),
):
    chat = Chat(user_id=principal.user.id, title=payload.title.strip())
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return {"id": chat.id, "title": chat.title}


@router.get("/chats/{chat_id}/messages")
def list_messages(
    chat_id: str,
    principal: Principal = Depends(get_ready_principal),
    db: Session = Depends(get_db),
):
    _owned_chat(db, chat_id, principal.user.id)
    messages = list(
        db.scalars(
            select(Message)
            .where(Message.chat_id == chat_id)
            .order_by(Message.id)
        )
    )
    return [
        {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "created_at": message.created_at.isoformat(),
        }
        for message in messages
    ]


@router.post("/chats/{chat_id}/messages")
async def send_message(
    chat_id: str,
    payload: MessageCreateIn,
    principal: Principal = Depends(require_ready_csrf),
):
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="消息不能为空")
    async with user_job_locks[principal.user.id]:
        job = create_job(principal.user.id, chat_id, content)
        job_manager.submit(job.id)
    return {"job_id": job.id, "status": "queued"}


@router.post("/chats/{chat_id}/archive")
def archive_chat(
    chat_id: str,
    principal: Principal = Depends(require_ready_csrf),
    db: Session = Depends(get_db),
):
    chat = _owned_chat(db, chat_id, principal.user.id)
    active = db.scalar(
        select(Job.id).where(
            Job.chat_id == chat_id, Job.state.in_(("queued", "running"))
        )
    )
    if active:
        raise HTTPException(status_code=409, detail="会话仍有任务运行")
    chat.is_archived = True
    db.commit()
    return {"ok": True}


@router.get("/jobs/{job_id}/events")
async def job_events(
    job_id: str,
    request: Request,
    after: int = Query(default=0, ge=0),
    principal: Principal = Depends(get_ready_principal),
):
    last_event_id = request.headers.get("last-event-id", "")
    if len(last_event_id) <= 20 and last_event_id.isdigit():
        after = max(after, int(last_event_id))
    return StreamingResponse(
        event_stream(job_id, principal.user.id, after),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/jobs/{job_id}/stop")
async def stop_job(
    job_id: str,
    principal: Principal = Depends(require_ready_csrf),
):
    async with user_job_locks[principal.user.id]:
        await job_manager.stop(job_id, principal.user.id)
    return {"ok": True}


@router.get("/usage")
def usage(principal: Principal = Depends(get_ready_principal)):
    return quota_status(principal.user.id)
