from __future__ import annotations

import dataclasses
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx
from fastapi.testclient import TestClient

import webapp.deepseek_proxy as proxy_module
from webapp.config import settings
from webapp.db import session_scope
from webapp.main import app
from webapp.models import Chat, DailyUsage, Job, User
from webapp.security import mint_proxy_token, password_hash


def create_proxy_job(*, active: bool = True) -> tuple[str, str]:
    with session_scope() as db:
        user = User(
            username=f"proxy-{uuid.uuid4().hex[:8]}",
            password_hash=password_hash("proxy-password-123"),
            is_active=active,
            must_change_password=False,
        )
        db.add(user)
        db.flush()
        chat = Chat(user_id=user.id)
        db.add(chat)
        db.flush()
        job = Job(
            user_id=user.id,
            chat_id=chat.id,
            prompt="proxy test",
            state="running",
        )
        db.add(job)
        db.flush()
        return user.id, job.id


def configured_proxy(monkeypatch, handler):
    proxy_settings = dataclasses.replace(
        settings,
        deepseek_api_key="upstream-test-key",
    )
    monkeypatch.setattr(proxy_module, "settings", proxy_settings)
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        proxy_module,
        "_new_upstream_client",
        lambda: httpx.AsyncClient(transport=transport),
    )


def test_streaming_usage_is_attributed_to_signed_user(monkeypatch):
    def upstream(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == "upstream-test-key"
        content = (
            b'data: {"type":"message_start","message":'
            b'{"usage":{"input_tokens":11}}}\n\n'
            b'data: {"type":"message_delta","usage":{"output_tokens":7}}\n\n'
        )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=content,
        )

    configured_proxy(monkeypatch, upstream)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        user_id, job_id = create_proxy_job()
        token = mint_proxy_token(user_id, job_id)
        response = client.post(
            "/internal/deepseek/anthropic/v1/messages",
            headers={"Authorization": f"Bearer {token}"},
            json={"model": settings.primary_model, "messages": []},
        )
    assert response.status_code == 200
    assert "message_delta" in response.text
    with session_scope() as db:
        usage = db.query(DailyUsage).filter_by(user_id=user_id).one()
        assert usage.api_requests == 1
        assert usage.input_tokens == 11
        assert usage.output_tokens == 7
        assert usage.total_tokens == 18


def test_proxy_rejects_unpinned_model_before_upstream(monkeypatch):
    called = False

    def upstream(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    configured_proxy(monkeypatch, upstream)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        user_id, job_id = create_proxy_job()
        response = client.post(
            "/internal/deepseek/anthropic/v1/messages",
            headers={
                "Authorization": f"Bearer {mint_proxy_token(user_id, job_id)}"
            },
            json={"model": "unapproved-model", "messages": []},
        )
    assert response.status_code == 400
    assert called is False


def test_disabling_user_revokes_existing_proxy_token(monkeypatch):
    monkeypatch.setattr(
        proxy_module,
        "settings",
        dataclasses.replace(settings, deepseek_api_key="upstream-test-key"),
    )
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        user_id, job_id = create_proxy_job()
        token = mint_proxy_token(user_id, job_id)
        with session_scope() as db:
            db.get(User, user_id).is_active = False
        response = client.post(
            "/internal/deepseek/anthropic/v1/messages",
            headers={"Authorization": f"Bearer {token}"},
            json={"model": settings.primary_model, "messages": []},
        )
    assert response.status_code == 403


def test_finished_job_revokes_existing_proxy_token(monkeypatch):
    monkeypatch.setattr(
        proxy_module,
        "settings",
        dataclasses.replace(settings, deepseek_api_key="upstream-test-key"),
    )
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        user_id, job_id = create_proxy_job()
        token = mint_proxy_token(user_id, job_id)
        with session_scope() as db:
            db.get(Job, job_id).state = "completed"
        response = client.post(
            "/internal/deepseek/anthropic/v1/messages",
            headers={"Authorization": f"Bearer {token}"},
            json={"model": settings.primary_model, "messages": []},
        )
    assert response.status_code == 403


def test_proxy_returns_502_when_upstream_is_unreachable(monkeypatch):
    def upstream(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    configured_proxy(monkeypatch, upstream)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        user_id, job_id = create_proxy_job()
        response = client.post(
            "/internal/deepseek/anthropic/v1/messages",
            headers={
                "Authorization": f"Bearer {mint_proxy_token(user_id, job_id)}"
            },
            json={"model": settings.primary_model, "messages": []},
        )
    assert response.status_code == 502
    assert "DeepSeek" in response.json()["detail"]


def test_usage_updates_are_atomic_for_parallel_subagents():
    user_id, _job_id = create_proxy_job()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(
            pool.map(
                lambda _index: proxy_module._record_tokens(user_id, 3, 2),
                range(12),
            )
        )
        list(
            pool.map(
                lambda _index: proxy_module._record_request(user_id),
                range(12),
            )
        )
    with session_scope() as db:
        usage = db.query(DailyUsage).filter_by(user_id=user_id).one()
        assert usage.input_tokens == 36
        assert usage.output_tokens == 24
        assert usage.total_tokens == 60
        assert usage.api_requests == 12
