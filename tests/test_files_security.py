from __future__ import annotations

import asyncio
import dataclasses
import subprocess
import zipfile
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient

import webapp.files as files_module
import webapp.runner_client as runner_client_module
from webapp.config import settings
from webapp.db import session_scope
from webapp.file_extract import extract_text
from webapp.main import app
from webapp.models import Chat, Job, User
from webapp.security import password_hash


def create_and_login(client: TestClient, username: str) -> str:
    password = "upload-password-123"
    with session_scope() as db:
        user = User(
            username=username,
            password_hash=password_hash(password),
            must_change_password=False,
        )
        db.add(user)
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def test_docx_zip_bomb_is_rejected_before_parsing(tmp_path: Path):
    malicious = tmp_path / "bomb.docx"
    with zipfile.ZipFile(
        malicious,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr("word/document.xml", "0" * (2 * 1024 * 1024))
    try:
        extract_text(malicious, ".docx")
    except ValueError as exc:
        assert "压缩比例" in str(exc)
    else:
        raise AssertionError("异常压缩比 DOCX 不应进入解析器")


@pytest.mark.asyncio
async def test_docx_extraction_runs_in_limited_subprocess(tmp_path: Path):
    source = tmp_path / "resume.docx"
    output = tmp_path / "resume.txt"
    document = Document()
    document.add_paragraph("隔离提取测试")
    document.save(source)
    await files_module._extract_in_subprocess(source, ".docx", output)
    assert output.read_text(encoding="utf-8") == "隔离提取测试"


def test_upload_size_limit_and_script_suffix(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        files_module,
        "settings",
        dataclasses.replace(
            settings,
            staging_root=tmp_path / "staging",
            max_upload_bytes=10,
        ),
    )
    with TestClient(app) as client:
        csrf = create_and_login(client, "upload.user")
        oversized = client.post(
            "/api/files/upload",
            headers={"X-CSRF-Token": csrf},
            files={"upload": ("resume.txt", b"12345678901", "text/plain")},
        )
        assert oversized.status_code == 413
        script = client.post(
            "/api/files/upload",
            headers={"X-CSRF-Token": csrf},
            files={"upload": ("run.sh", b"echo unsafe", "text/x-shellscript")},
        )
        assert script.status_code == 415


def test_upload_is_rejected_while_user_has_active_job(tmp_path: Path):
    with TestClient(app) as client:
        csrf = create_and_login(client, "upload.busy")
        with session_scope() as db:
            user = db.query(User).filter_by(username="upload.busy").one()
            chat = Chat(user_id=user.id)
            db.add(chat)
            db.flush()
            db.add(
                Job(
                    user_id=user.id,
                    chat_id=chat.id,
                    prompt="still running",
                    state="running",
                )
            )
        response = client.post(
            "/api/files/upload",
            headers={"X-CSRF-Token": csrf},
            files={"upload": ("resume.txt", b"safe", "text/plain")},
        )
    assert response.status_code == 409
    assert "任务结束" in response.json()["detail"]


def test_successful_upload_is_readonly_and_committed(monkeypatch, tmp_path: Path):
    template = tmp_path / "template"
    template.mkdir()
    (template / "README.md").write_text("template", encoding="utf-8")
    isolated = dataclasses.replace(
        settings,
        template_root=template,
        development_root=tmp_path / "users",
        staging_root=tmp_path / "staging",
    )
    monkeypatch.setattr(files_module, "settings", isolated)
    monkeypatch.setattr(runner_client_module, "settings", isolated)

    with TestClient(app) as client:
        csrf = create_and_login(client, "upload.commit")
        with session_scope() as db:
            user_id = (
                db.query(User)
                .filter_by(username="upload.commit")
                .one()
                .id
            )
        asyncio.run(
            runner_client_module.runner_client.request(
                "provision",
                user_id=user_id,
            )
        )
        response = client.post(
            "/api/files/upload",
            headers={"X-CSRF-Token": csrf},
            files={"upload": ("resume.txt", b"safe content", "text/plain")},
        )
    assert response.status_code == 200
    workspace = isolated.development_root / user_id / "workspace"
    uploaded = workspace / response.json()["relative_path"]
    assert uploaded.read_bytes() == b"safe content"
    assert uploaded.stat().st_mode & 0o222 == 0
    log = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    assert log.stdout.strip() == "user: upload resume.txt"
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    assert status.stdout == ""


def test_markdown_preview_is_authenticated_owned_and_size_limited(monkeypatch):
    content = b"# Preview\n\n<script>alert('unsafe')</script>\n"

    async def fake_request(operation: str, **_payload):
        assert operation == "file_list"
        return {
            "files": [
                {
                    "relative_path": "dist/result.md",
                    "size": len(content),
                    "mime_type": "text/markdown",
                }
            ]
        }

    async def fake_read_file(_user_id: str, relative_path: str):
        assert relative_path == "dist/result.md"
        yield content

    monkeypatch.setattr(files_module.runner_client, "request", fake_request)
    monkeypatch.setattr(files_module.runner_client, "read_file", fake_read_file)

    with TestClient(app) as client:
        assert (
            client.get("/api/files/preview?path=dist/result.md").status_code
            == 401
        )
        create_and_login(client, "preview.user")
        preview = client.get("/api/files/preview?path=dist/result.md")
        missing = client.get("/api/files/preview?path=dist/missing.md")
        unsupported = client.get("/api/files/preview?path=dist/result.txt")

    assert preview.status_code == 200
    assert preview.json() == {
        "relative_path": "dist/result.md",
        "content": content.decode(),
    }
    assert preview.headers["cache-control"] == "no-store"
    assert missing.status_code == 404
    assert unsupported.status_code == 415


def test_markdown_preview_rejects_large_file_before_reading(monkeypatch):
    async def fake_request(operation: str, **_payload):
        assert operation == "file_list"
        return {
            "files": [
                {
                    "relative_path": "dist/large.md",
                    "size": files_module.MAX_MARKDOWN_PREVIEW_BYTES + 1,
                }
            ]
        }

    async def unexpected_read_file(_user_id: str, _relative_path: str):
        raise AssertionError("超限文件不应进入读取阶段")
        yield b""

    monkeypatch.setattr(files_module.runner_client, "request", fake_request)
    monkeypatch.setattr(
        files_module.runner_client,
        "read_file",
        unexpected_read_file,
    )

    with TestClient(app) as client:
        create_and_login(client, "preview.large")
        response = client.get("/api/files/preview?path=dist/large.md")

    assert response.status_code == 413
    assert "2 MB" in response.json()["detail"]
