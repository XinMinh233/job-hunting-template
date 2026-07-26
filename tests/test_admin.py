from __future__ import annotations

from fastapi.testclient import TestClient

import webapp.admin as admin_module
from webapp.db import session_scope
from webapp.main import app
from webapp.models import User
from webapp.security import password_hash


def test_admin_can_create_adjust_reset_and_disable_user(monkeypatch):
    with session_scope() as db:
        admin = User(
            username="site.admin",
            password_hash=password_hash("admin-password-123"),
            role="admin",
            must_change_password=False,
        )
        db.add(admin)

    calls: list[str] = []

    async def runner(operation, **payload):
        calls.append(operation)
        if operation == "provision":
            return {
                "ok": True,
                "linux_username": "jh_123456789abc",
                "workspace_path": f"/srv/{payload['user_id']}/workspace",
                "template_version": "test-v1",
            }
        return {"ok": True}

    monkeypatch.setattr(admin_module.runner_client, "request", runner)
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={
                "username": "site.admin",
                "password": "admin-password-123",
            },
        )
        csrf = login.json()["csrf_token"]
        created = client.post(
            "/api/admin/users",
            headers={"X-CSRF-Token": csrf},
            json={
                "username": "friend.user",
                "daily_job_limit": 30,
                "daily_token_limit": 1_000_000,
            },
        )
        assert created.status_code == 200
        user_id = created.json()["id"]
        quota = client.put(
            f"/api/admin/users/{user_id}/quota",
            headers={"X-CSRF-Token": csrf},
            json={"daily_job_limit": 12, "daily_token_limit": 500_000},
        )
        reset = client.post(
            f"/api/admin/users/{user_id}/reset-password",
            headers={"X-CSRF-Token": csrf},
            json={"force_change": True},
        )
        disabled = client.post(
            f"/api/admin/users/{user_id}/disable",
            headers={"X-CSRF-Token": csrf},
        )
    assert quota.status_code == 200
    assert len(reset.json()["temporary_password"]) >= 12
    assert disabled.status_code == 200
    assert calls == ["provision", "disable"]
    with session_scope() as db:
        user = db.get(User, user_id)
        assert user.is_active is False
        assert user.daily_job_limit == 12
        assert user.daily_token_limit == 500_000
        assert user.must_change_password is True
