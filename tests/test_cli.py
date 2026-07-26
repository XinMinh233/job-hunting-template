from __future__ import annotations

import argparse

import webapp.cli as cli_module
from webapp.db import session_scope
from webapp.models import User


def test_bootstrap_admin_also_provisions_isolated_workspace(
    monkeypatch,
):
    monkeypatch.setenv("TEST_ADMIN_PASSWORD", "admin-password-123")

    async def provision(operation, **payload):
        assert operation == "provision"
        return {
            "ok": True,
            "linux_username": "jh_123456789abc",
            "workspace_path": f"/srv/users/{payload['user_id']}/workspace",
            "template_version": "test-v1",
        }

    monkeypatch.setattr(cli_module.runner_client, "request", provision)
    result = cli_module._bootstrap_admin(
        argparse.Namespace(
            username="admin",
            password_env="TEST_ADMIN_PASSWORD",
        )
    )
    assert result == 0
    with session_scope() as db:
        admin = db.query(User).filter_by(username="admin").one()
        assert admin.role == "admin"
        assert admin.linux_username == "jh_123456789abc"
        assert admin.workspace_path.endswith("/workspace")
        assert admin.template_version == "test-v1"

