from __future__ import annotations

import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from webapp.db import Base
from webapp.models import (
    Chat,
    DailyUsage,
    FileRecord,
    Job,
    JobEvent,
    Message,
    User,
)
from webapp.security import password_hash


def database(path: Path):
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32))")
        )
        connection.execute(
            text("INSERT INTO alembic_version VALUES ('0001')")
        )
    return engine


def test_single_user_database_restore_keeps_auth_and_interrupts_job(
    tmp_path: Path,
):
    source_path = tmp_path / "snapshot.sqlite3"
    target_path = tmp_path / "target.sqlite3"
    source_engine = database(source_path)
    target_engine = database(target_path)
    user_id = str(uuid.uuid4())
    chat_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    current_hash = password_hash("current-password-123")
    with Session(source_engine) as db:
        db.add(
            User(
                id=user_id,
                username="restore.user",
                password_hash=password_hash("old-password-123"),
                is_active=False,
                template_version="snapshot-v1",
            )
        )
        chat = Chat(
            id=chat_id,
            user_id=user_id,
            title="快照会话",
            claude_session_id="snapshot_session_123",
        )
        db.add(chat)
        db.add(Message(chat_id=chat_id, role="user", content="恢复我"))
        job = Job(
            id=job_id,
            user_id=user_id,
            chat_id=chat_id,
            prompt="in flight",
            state="running",
        )
        db.add(job)
        db.add(
            JobEvent(
                job_id=job_id,
                seq=1,
                type="status",
                data_json='{"state":"running"}',
            )
        )
        db.add(
            DailyUsage(
                user_id=user_id,
                day=date(2026, 7, 26),
                jobs=1,
                total_tokens=10,
            )
        )
        db.add(
            FileRecord(
                user_id=user_id,
                relative_path="uploads/x/resume.txt",
                original_name="resume.txt",
                mime_type="text/plain",
                size_bytes=10,
            )
        )
        db.commit()
    with Session(target_engine) as db:
        db.add(
            User(
                id=user_id,
                username="restore.user",
                password_hash=current_hash,
                is_active=False,
                template_version="current-v2",
            )
        )
        db.add(Chat(user_id=user_id, title="应被替换"))
        db.commit()

    script = (
        Path(__file__).parents[1]
        / "deploy"
        / "scripts"
        / "restore_user_db.py"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--snapshot-db",
            str(source_path),
            "--target-db",
            str(target_path),
            "--user-id",
            user_id,
            "--confirm-offline",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "恢复完成" in result.stdout
    with Session(target_engine) as db:
        user = db.get(User, user_id)
        assert user.password_hash == current_hash
        assert user.template_version == "snapshot-v1"
        assert db.get(Chat, chat_id).claude_session_id == "snapshot_session_123"
        assert db.get(Job, job_id).state == "interrupted"
        assert db.query(Message).filter_by(chat_id=chat_id).count() == 1
        assert db.query(FileRecord).filter_by(user_id=user_id).count() == 1
    backups = list(tmp_path.glob("target.sqlite3.before-user-restore-*"))
    assert len(backups) == 1
    assert backups[0].stat().st_mode & 0o077 == 0
