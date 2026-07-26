from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import defaultdict
from collections.abc import AsyncIterator

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from .audit import audit
from .config import settings
from .db import session_scope
from .models import (
    Chat,
    DailyUsage,
    Job,
    JobEvent,
    Message,
    User,
    utcnow,
)
from .runner_client import RunnerError, runner_client
from .security import mint_proxy_token
from .stream_parser import ClaudeStreamParser
from .time_utils import quota_day

TERMINAL_STATES = {"completed", "failed", "cancelled", "interrupted"}
ACTIVE_STATES = {"queued", "running"}
LONG_COMMANDS = ("/scout", "/crossroads")
EVENT_TYPES = {"status", "text_delta", "tool", "artifact", "done", "error"}
logger = logging.getLogger(__name__)
user_job_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def _safe_error(error: str) -> str:
    lowered = error.lower()
    if "permission" in lowered or "not allowed" in lowered:
        return "Claude 请求了未授权操作，任务已停止；请联系管理员核对允许清单"
    if "429" in lowered or "rate limit" in lowered or "quota" in lowered:
        return "模型服务当前限流或额度不足，请稍后重试"
    if (
        "timed out" in lowered
        or "timeout" in lowered
        or "runtime" in lowered
        or "turn limit" in lowered
    ):
        return "任务超过允许运行时间，已停止"
    if "401" in lowered or "unauthorized" in lowered:
        return "模型代理认证失败，请联系管理员"
    if "connection" in lowered or "connect" in lowered or "502" in lowered:
        return "暂时无法连接模型服务，请稍后重试"
    # 不把上游正文、命令、内部 Token 或服务器绝对路径发送给浏览器。
    sanitized = re.sub(r"/(?:var|etc|run|opt)/[^\s]+", "[服务器路径]", error)
    sanitized = re.sub(
        r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b",
        "[内部凭证]",
        sanitized,
    )
    if len(sanitized) > 300:
        return "Claude 任务执行失败，请联系管理员查看服务状态"
    return sanitized or "Claude 任务执行失败"


def _event(job_id: str, event_type: str, data: dict) -> int:
    if event_type not in EVENT_TYPES:
        raise ValueError("不支持的任务事件类型")
    for _attempt in range(5):
        try:
            with session_scope() as db:
                sequence = (
                    db.scalar(
                        select(func.max(JobEvent.seq)).where(
                            JobEvent.job_id == job_id
                        )
                    )
                    or 0
                ) + 1
                db.add(
                    JobEvent(
                        job_id=job_id,
                        seq=sequence,
                        type=event_type,
                        data_json=json.dumps(data, ensure_ascii=False),
                    )
                )
            return sequence
        except IntegrityError:
            continue
    raise RuntimeError("任务事件序号竞争，请重试")


def quota_status(user_id: str) -> dict[str, int]:
    with session_scope() as db:
        user = db.get(User, user_id)
        usage = db.scalar(
            select(DailyUsage).where(
                DailyUsage.user_id == user_id,
                DailyUsage.day == quota_day(),
            )
        )
        return {
            "jobs": usage.jobs if usage else 0,
            "tokens": usage.total_tokens if usage else 0,
            "job_limit": user.daily_job_limit if user else 0,
            "token_limit": user.daily_token_limit if user else 0,
        }


def create_job(user_id: str, chat_id: str, prompt: str) -> Job:
    with session_scope() as db:
        user = db.get(User, user_id)
        chat = db.get(Chat, chat_id)
        if not user or not user.is_active or not chat or chat.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        active = db.scalar(
            select(func.count(Job.id)).where(
                Job.user_id == user_id, Job.state.in_(ACTIVE_STATES)
            )
        )
        if active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="当前已有任务运行或排队，请等待完成",
            )
        usage = db.scalar(
            select(DailyUsage).where(
                DailyUsage.user_id == user_id,
                DailyUsage.day == quota_day(),
            )
        )
        if not usage:
            usage = DailyUsage(
                user_id=user_id,
                day=quota_day(),
                jobs=0,
                api_requests=0,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
            )
            db.add(usage)
        if usage.jobs >= user.daily_job_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="今日任务额度已用完，请联系管理员",
            )
        if usage.total_tokens >= user.daily_token_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="今日 Token 额度已用完，请联系管理员",
            )
        usage.jobs += 1
        job = Job(user_id=user_id, chat_id=chat_id, prompt=prompt)
        db.add(job)
        db.flush()
        db.add(Message(chat_id=chat_id, role="user", content=prompt))
        chat.updated_at = utcnow()
        if chat.title == "新会话":
            chat.title = prompt.strip().replace("\n", " ")[:40] or "新会话"
        audit(
            db,
            "job.created",
            actor_user_id=user_id,
            target=job.id,
            detail={"chat_id": chat_id},
        )
        return job


class JobManager:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.workers: list[asyncio.Task] = []
        self.started = False

    async def start(self) -> None:
        if self.started:
            return
        self.started = True
        self.queue = asyncio.Queue()
        interrupted_ids: list[str] = []
        with session_scope() as db:
            interrupted = list(
                db.scalars(select(Job).where(Job.state == "running"))
            )
            for job in interrupted:
                job.state = "interrupted"
                job.error = "服务重启导致任务中断"
                job.finished_at = utcnow()
                db.add(
                    Message(
                        chat_id=job.chat_id,
                        role="assistant",
                        content=(
                            "[任务中断] 服务重启导致任务中断，"
                            "可在本会话继续发送消息恢复 Claude 会话。"
                        ),
                    )
                )
                chat = db.get(Chat, job.chat_id)
                if chat:
                    chat.updated_at = utcnow()
                interrupted_ids.append(job.id)
            queued = list(db.scalars(select(Job.id).where(Job.state == "queued")))
        for job_id in interrupted_ids:
            _event(
                job_id,
                "error",
                {"message": "服务重启导致任务中断，可在本会话继续"},
            )
        for job_id in queued:
            self.queue.put_nowait(job_id)
        self.workers = [
            asyncio.create_task(self._worker(index))
            for index in range(settings.global_concurrency)
        ]

    async def close(self) -> None:
        with session_scope() as db:
            running_ids = list(
                db.scalars(select(Job.id).where(Job.state == "running"))
            )
        await asyncio.gather(
            *(
                runner_client.request("stop", job_id=job_id)
                for job_id in running_ids
            ),
            return_exceptions=True,
        )
        for worker in self.workers:
            worker.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()
        self.started = False

    def submit(self, job_id: str) -> None:
        self.queue.put_nowait(job_id)

    async def stop(
        self,
        job_id: str,
        user_id: str,
        *,
        actor_user_id: str | None = None,
    ) -> None:
        was_running = False
        with session_scope() as db:
            job = db.get(Job, job_id)
            if not job or job.user_id != user_id:
                raise HTTPException(status_code=404)
            if job.state in TERMINAL_STATES:
                return
            was_running = job.state == "running"
            job.state = "cancelled"
            job.finished_at = utcnow()
            db.add(
                Message(
                    chat_id=job.chat_id,
                    role="assistant",
                    content="[任务已停止] 你可以在本会话继续发送消息。",
                )
            )
            chat = db.get(Chat, job.chat_id)
            if chat:
                chat.updated_at = utcnow()
            audit(
                db,
                "job.cancelled",
                actor_user_id=actor_user_id or user_id,
                target=job_id,
            )
        _event(job_id, "status", {"state": "cancelled", "message": "任务已停止"})
        if was_running:
            try:
                await runner_client.request("stop", job_id=job_id)
            except RunnerError:
                pass

    async def _worker(self, _index: int) -> None:
        while True:
            job_id = await self.queue.get()
            try:
                await self._execute(job_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._fail(job_id, str(exc))
            finally:
                self.queue.task_done()

    async def _fail(self, job_id: str, error: str) -> None:
        safe_error = _safe_error(error)
        logger.warning("任务 %s 失败：%s", job_id, safe_error)
        with session_scope() as db:
            job = db.get(Job, job_id)
            if not job or job.state == "cancelled":
                return
            job.state = "failed"
            job.error = safe_error
            job.finished_at = utcnow()
            db.add(
                Message(
                    chat_id=job.chat_id,
                    role="assistant",
                    content=f"[任务失败] {safe_error}",
                )
            )
            chat = db.get(Chat, job.chat_id)
            if chat:
                chat.updated_at = utcnow()
        _event(job_id, "error", {"message": safe_error})

    async def _execute(self, job_id: str) -> None:
        with session_scope() as db:
            job = db.get(Job, job_id)
            if not job or job.state != "queued":
                return
            user_id = job.user_id
        async with user_job_locks[user_id]:
            with session_scope() as db:
                job = db.get(Job, job_id)
                if not job or job.state != "queued":
                    return
                user = db.get(User, job.user_id)
                chat = db.get(Chat, job.chat_id)
                if not user or not user.is_active or not chat:
                    job.state = "failed"
                    job.error = "用户或会话不可用"
                    job.finished_at = utcnow()
                    return
                job.state = "running"
                job.started_at = utcnow()
                prompt = job.prompt
                chat_id = job.chat_id
                claude_session_id = chat.claude_session_id
        _event(job_id, "status", {"state": "running", "message": "Claude 正在处理"})
        try:
            before_result = await runner_client.request(
                "file_list", user_id=user_id
            )
            before_files = {
                item["relative_path"]: item.get("modified_ns")
                for item in before_result.get("files", [])
            }
        except RunnerError:
            before_files = {}
        with session_scope() as db:
            current = db.get(Job, job_id)
            if not current or current.state == "cancelled":
                return

        parser = ClaudeStreamParser()
        assistant_parts: list[str] = []
        exit_code: int | None = None
        async for runner_event in runner_client.stream_run(
            user_id=user_id,
            job_id=job_id,
            prompt=prompt,
            claude_session_id=claude_session_id,
            proxy_token=mint_proxy_token(
                user_id,
                job_id,
                ttl_seconds=3600,
            ),
            long_run=prompt.lstrip().startswith(LONG_COMMANDS),
        ):
            with session_scope() as db:
                current = db.get(Job, job_id)
                if current and current.state == "cancelled":
                    return
            kind = runner_event.get("type")
            if kind == "started":
                with session_scope() as db:
                    current = db.get(Job, job_id)
                    if current:
                        current.runner_unit = str(runner_event.get("unit") or "")
                continue
            if kind == "output":
                parsed = parser.feed(str(runner_event.get("line") or ""))
                if parsed.session_id:
                    with session_scope() as db:
                        current_chat = db.get(Chat, chat_id)
                        if current_chat:
                            current_chat.claude_session_id = parsed.session_id
                for event_type, data in parsed.events:
                    if event_type == "text_delta":
                        assistant_parts.append(str(data.get("text") or ""))
                    _event(job_id, event_type, data)
                if parsed.done or parsed.failed:
                    if parsed.failed:
                        raise RunnerError(parsed.error or "Claude 执行失败")
            elif kind == "exit":
                exit_code = int(runner_event.get("code") or 0)
                if exit_code != 0:
                    stderr = str(runner_event.get("stderr") or "")
                    raise RunnerError(
                        stderr[-1000:] or f"Claude 退出码：{exit_code}"
                    )

        if exit_code not in (None, 0):
            raise RunnerError(f"Claude 退出码：{exit_code}")
        assistant_text = "".join(assistant_parts).strip()
        with session_scope() as db:
            current = db.get(Job, job_id)
            if not current or current.state == "cancelled":
                return
            if assistant_text:
                db.add(
                    Message(
                        chat_id=chat_id,
                        role="assistant",
                        content=assistant_text,
                    )
                )
            current_chat = db.get(Chat, chat_id)
            if current_chat:
                current_chat.updated_at = utcnow()
            current.state = "completed"
            current.finished_at = utcnow()
            audit(
                db,
                "job.completed",
                actor_user_id=user_id,
                target=job_id,
            )
        try:
            after_result = await runner_client.request(
                "file_list", user_id=user_id
            )
            for item in after_result.get("files", []):
                relative = item["relative_path"]
                if before_files.get(relative) != item.get("modified_ns"):
                    _event(
                        job_id,
                        "artifact",
                        {
                            "relative_path": relative,
                            "size": item.get("size", 0),
                        },
                    )
        except RunnerError:
            pass
        _event(job_id, "done", {"state": "completed"})


job_manager = JobManager()


async def event_stream(
    job_id: str, user_id: str, after: int = 0
) -> AsyncIterator[str]:
    sequence = max(0, after)
    idle_ticks = 0
    while True:
        with session_scope() as db:
            job = db.get(Job, job_id)
            if not job or job.user_id != user_id:
                yield "event: error\ndata: {\"message\":\"任务不存在\"}\n\n"
                return
            events = list(
                db.scalars(
                    select(JobEvent)
                    .where(JobEvent.job_id == job_id, JobEvent.seq > sequence)
                    .order_by(JobEvent.seq)
                )
            )
            state = job.state
        if events:
            idle_ticks = 0
            for item in events:
                sequence = item.seq
                envelope = json.dumps(
                    {
                        "seq": item.seq,
                        "job_id": job_id,
                        "type": item.type,
                        "data": json.loads(item.data_json),
                    },
                    ensure_ascii=False,
                )
                yield f"id: {item.seq}\nevent: {item.type}\ndata: {envelope}\n\n"
        else:
            idle_ticks += 1
            if idle_ticks % 20 == 0:
                yield ": keepalive\n\n"
        if state in TERMINAL_STATES and not events:
            return
        await asyncio.sleep(0.5)
