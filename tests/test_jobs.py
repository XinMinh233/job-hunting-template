from __future__ import annotations

import asyncio
import datetime as dt
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import webapp.jobs as jobs_module
from webapp.db import session_scope
from webapp.jobs import JobManager, create_job
from webapp.models import Chat, DailyUsage, Job, JobEvent, Message, User
from webapp.security import password_hash
from webapp.time_utils import quota_day


def setup_user_and_chat(
    *,
    job_limit: int = 30,
    username: str = "queue.user",
) -> tuple[str, str]:
    with session_scope() as db:
        user = User(
            username=username,
            password_hash=password_hash("safe-password-123"),
            must_change_password=False,
            daily_job_limit=job_limit,
        )
        db.add(user)
        db.flush()
        chat = Chat(user_id=user.id)
        db.add(chat)
        db.flush()
        return user.id, chat.id


def test_each_user_can_only_have_one_active_job():
    user_id, chat_id = setup_user_and_chat()
    create_job(user_id, chat_id, "first")
    with pytest.raises(HTTPException) as exc:
        create_job(user_id, chat_id, "second")
    assert exc.value.status_code == 409


def test_daily_job_quota_is_checked_before_start():
    user_id, chat_id = setup_user_and_chat(job_limit=1)
    create_job(user_id, chat_id, "first")
    with session_scope() as db:
        job = db.query(Job).first()
        job.state = "completed"
    with pytest.raises(HTTPException) as exc:
        create_job(user_id, chat_id, "second")
    assert exc.value.status_code == 429


def test_daily_quota_resets_on_next_local_day():
    user_id, chat_id = setup_user_and_chat(job_limit=1)
    with session_scope() as db:
        db.add(
            DailyUsage(
                user_id=user_id,
                day=quota_day() - dt.timedelta(days=1),
                jobs=1,
                total_tokens=1_000_000,
            )
        )
    assert create_job(user_id, chat_id, "new local day").state == "queued"


@pytest.mark.asyncio
async def test_running_job_becomes_interrupted_after_manager_restart():
    user_id, chat_id = setup_user_and_chat()
    with session_scope() as db:
        job = Job(
            user_id=user_id,
            chat_id=chat_id,
            prompt="in flight",
            state="running",
        )
        db.add(job)
        db.flush()
        job_id = job.id
    manager = JobManager()
    await manager.start()
    with session_scope() as db:
        assert db.get(Job, job_id).state == "interrupted"
        assert (
            db.query(Message)
            .filter_by(chat_id=chat_id, role="assistant")
            .one()
            .content.startswith("[任务中断]")
        )
        event = db.query(JobEvent).filter_by(job_id=job_id).one()
        assert event.type == "error"
    await manager.close()


@pytest.mark.asyncio
async def test_global_queue_never_runs_more_than_three(monkeypatch):
    job_ids = []
    for index in range(4):
        user_id, chat_id = setup_user_and_chat(
            username=f"parallel.user{index}"
        )
        job_ids.append(create_job(user_id, chat_id, f"job {index}").id)

    class FakeRunner:
        def __init__(self):
            self.active = 0
            self.maximum = 0
            self.three_started = asyncio.Event()
            self.release = asyncio.Event()

        async def request(self, operation, **_payload):
            if operation == "file_list":
                return {"ok": True, "files": []}
            return {"ok": True}

        async def stream_run(self, **payload):
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            if self.active == 3:
                self.three_started.set()
            try:
                yield {"type": "started", "unit": f"fake-{payload['job_id']}"}
                await self.release.wait()
                yield {"type": "exit", "code": 0, "stderr": ""}
            finally:
                self.active -= 1

    fake = FakeRunner()
    monkeypatch.setattr(jobs_module, "runner_client", fake)
    monkeypatch.setattr(
        jobs_module,
        "settings",
        SimpleNamespace(global_concurrency=3),
    )
    manager = JobManager()
    await manager.start()
    await asyncio.wait_for(fake.three_started.wait(), timeout=2)
    with session_scope() as db:
        states = [db.get(Job, job_id).state for job_id in job_ids]
    assert states.count("running") == 3
    assert states.count("queued") == 1
    assert fake.maximum == 3
    fake.release.set()
    await asyncio.wait_for(manager.queue.join(), timeout=2)
    await manager.close()
    with session_scope() as db:
        assert all(db.get(Job, job_id).state == "completed" for job_id in job_ids)
