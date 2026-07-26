from __future__ import annotations

from pathlib import Path

import pytest

from webapp.runner_protocol import (
    LONG_TURN_LIMIT,
    NORMAL_TURN_LIMIT,
    STAGING_NAME_RE,
    resolve_user_file,
    safe_filename,
    safe_relative_path,
)
from webapp.runner_server import _systemd_command


@pytest.mark.parametrize(
    "value",
    [
        "../shadow",
        "/etc/passwd",
        "uploads/../../etc/passwd",
        r"uploads\..\data\secret",
        "unknown/file.txt",
    ],
)
def test_path_traversal_and_non_whitelisted_roots_are_rejected(value):
    with pytest.raises(ValueError):
        safe_relative_path(value)


def test_allowed_relative_path():
    assert safe_relative_path("uploads/a/resume.pdf") == "uploads/a/resume.pdf"
    assert safe_relative_path("master.md") == "master.md"


def test_malicious_filename_is_reduced_to_basename():
    assert safe_filename("../../evil<script>.pdf") == "evil_script_.pdf"
    assert safe_filename("简历 2026.pdf") == "简历 2026.pdf"


def test_staging_name_is_fixed_random_name():
    assert STAGING_NAME_RE.fullmatch("a" * 32 + ".pdf")
    assert not STAGING_NAME_RE.fullmatch("../" + "a" * 32 + ".pdf")


def test_symlink_escape_is_rejected(tmp_path: Path):
    workspace = tmp_path / "workspace"
    uploads = workspace / "uploads"
    uploads.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (uploads / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        resolve_user_file(workspace, "uploads/link/secret.txt")


def test_systemd_command_is_fixed_resumable_and_hardened(tmp_path: Path):
    workspace = tmp_path / "workspace"
    home = tmp_path / "home"
    (workspace / ".claude").mkdir(parents=True)
    home.mkdir()
    (workspace / ".git").mkdir()
    (workspace / ".git" / "config").write_text("[core]\n")
    (workspace / ".claude" / "settings.json").write_text("{}")
    for script in (
        "build_resumes.py",
        "resume_lint.py",
        "build_dashboard.py",
        "build_career_tree.py",
        "check_links.py",
    ):
        (workspace / script).write_text("")
    entry = {
        "linux_username": "jh_1234567890ab",
        "workspace": str(workspace),
        "home": str(home),
    }
    unit, command = _systemd_command(
        entry=entry,
        user_id="12345678-1234-4123-8123-1234567890ab",
        job_id="87654321-4321-4321-8321-ba0987654321",
        session_id="session_12345678",
        proxy_token="signed.internal-token",
        long_run=True,
    )
    rendered = " ".join(command)
    assert unit.startswith("jh-123456781234-")
    assert "--resume session_12345678" in rendered
    assert "--continue" not in command
    assert "--dangerously-skip-permissions" not in command
    assert "RuntimeMaxSec=1800" in rendered
    assert "MemoryMax=2G" in rendered
    assert "TasksMax=128" in rendered
    assert "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6" in rendered
    assert "BindReadOnlyPaths=" in rendered
    assert "core.hooksPath" in rendered
    assert "Bash(python3 check_links.py:*)" in rendered
    assert "--max-turns" not in command
    assert NORMAL_TURN_LIMIT == 40
    assert LONG_TURN_LIMIT == 80
