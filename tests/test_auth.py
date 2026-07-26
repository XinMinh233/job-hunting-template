from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

import webapp.auth as auth_module
from webapp.config import settings
from webapp.db import session_scope
from webapp.main import app
from webapp.models import Chat, Job, JobEvent, User
from webapp.security import password_hash


def create_user(username: str, password: str, *, must_change: bool = False):
    with session_scope() as db:
        db.add(
            User(
                username=username,
                password_hash=password_hash(password),
                role="user",
                is_active=True,
                must_change_password=must_change,
            )
        )


def test_login_cookie_csrf_and_forced_password_change():
    create_user("friend.one", "temporary-password-123", must_change=True)
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={"username": "friend.one", "password": "temporary-password-123"},
        )
        assert response.status_code == 200
        assert response.json()["must_change_password"] is True
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie
        assert "SameSite=lax" in cookie
        me = client.get("/api/auth/me")
        assert me.status_code == 200
        csrf = me.json()["csrf_token"]
        denied = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "temporary-password-123",
                "new_password": "new-secure-password-456",
            },
        )
        assert denied.status_code == 403
        changed = client.post(
            "/api/auth/change-password",
            headers={"X-CSRF-Token": csrf},
            json={
                "current_password": "temporary-password-123",
                "new_password": "new-secure-password-456",
            },
        )
        assert changed.status_code == 200
        assert client.get("/api/chats").status_code == 200


def test_production_cookie_is_secure(monkeypatch):
    create_user("secure.cookie", "secure-cookie-password")
    monkeypatch.setattr(
        auth_module,
        "settings",
        dataclasses.replace(settings, cookie_secure=True),
    )
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post(
            "/api/auth/login",
            json={
                "username": "secure.cookie",
                "password": "secure-cookie-password",
            },
        )
    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]


def test_login_is_limited_after_five_failures():
    create_user("limited.user", "correct-password-123")
    with TestClient(app) as client:
        for _ in range(5):
            response = client.post(
                "/api/auth/login",
                json={"username": "limited.user", "password": "wrong"},
            )
            assert response.status_code == 401
        blocked = client.post(
            "/api/auth/login",
            json={"username": "limited.user", "password": "correct-password-123"},
        )
        assert blocked.status_code == 429


def test_regular_user_cannot_access_admin_and_disabled_cookie_is_rejected():
    create_user("ordinary.user", "ordinary-password-123")
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={
                "username": "ordinary.user",
                "password": "ordinary-password-123",
            },
        )
        assert login.status_code == 200
        assert client.get("/api/admin/users").status_code == 403
        with session_scope() as db:
            db.query(User).filter_by(username="ordinary.user").one().is_active = (
                False
            )
        assert client.get("/api/auth/me").status_code == 403


def test_sse_last_event_id_only_replays_newer_events():
    create_user("events.user", "events-password-123")
    with session_scope() as db:
        user = db.query(User).filter_by(username="events.user").one()
        chat = Chat(user_id=user.id, title="事件测试")
        db.add(chat)
        db.flush()
        job = Job(
            user_id=user.id,
            chat_id=chat.id,
            prompt="test",
            state="completed",
        )
        db.add(job)
        db.flush()
        db.add_all(
            [
                JobEvent(
                    job_id=job.id,
                    seq=1,
                    type="text_delta",
                    data_json='{"text":"旧"}',
                ),
                JobEvent(
                    job_id=job.id,
                    seq=2,
                    type="done",
                    data_json='{"state":"completed"}',
                ),
            ]
        )
        job_id = job.id
    with TestClient(app) as client:
        client.post(
            "/api/auth/login",
            json={
                "username": "events.user",
                "password": "events-password-123",
            },
        )
        response = client.get(
            f"/api/jobs/{job_id}/events",
            headers={"Last-Event-ID": "1"},
        )
    assert response.status_code == 200
    assert '"seq": 2' in response.text
    assert '"seq": 1' not in response.text


def test_user_cannot_send_to_another_users_chat():
    create_user("owner.user", "owner-password-123")
    create_user("attacker.user", "attacker-password-123")
    with session_scope() as db:
        owner = db.query(User).filter_by(username="owner.user").one()
        chat = Chat(
            user_id=owner.id,
            title="private",
            claude_session_id="private_session_123",
        )
        db.add(chat)
        db.flush()
        chat_id = chat.id
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={
                "username": "attacker.user",
                "password": "attacker-password-123",
            },
        )
        csrf = login.json()["csrf_token"]
        history = client.get(f"/api/chats/{chat_id}/messages")
        send = client.post(
            f"/api/chats/{chat_id}/messages",
            headers={"X-CSRF-Token": csrf},
            json={"content": "resume someone else's session"},
        )
    assert history.status_code == 404
    assert send.status_code == 404
