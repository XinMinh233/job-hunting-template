#!/usr/bin/env python3
"""从快照 SQLite 中恢复一个已存在用户的聊天与 Web 元数据。"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sqlite3
from pathlib import Path
from typing import Iterable

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def rows(
    connection: sqlite3.Connection,
    query: str,
    parameters: tuple = (),
) -> list[sqlite3.Row]:
    return list(connection.execute(query, parameters))


def insert_rows(
    connection: sqlite3.Connection,
    table: str,
    columns: tuple[str, ...],
    values: Iterable[sqlite3.Row | tuple],
) -> None:
    placeholders = ", ".join("?" for _ in columns)
    connection.executemany(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        (tuple(value) for value in values),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-db", type=Path, required=True)
    parser.add_argument("--target-db", type=Path, required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument(
        "--confirm-offline",
        action="store_true",
        help="确认 Web 与 Runner 已停止，允许替换该用户的数据库记录",
    )
    args = parser.parse_args()
    if not args.confirm_offline:
        parser.error("必须传入 --confirm-offline")
    if not UUID_RE.fullmatch(args.user_id):
        parser.error("用户 UUID 格式无效")
    if not args.snapshot_db.is_file() or not args.target_db.is_file():
        parser.error("快照数据库或目标数据库不存在")
    if args.snapshot_db.resolve() == args.target_db.resolve():
        parser.error("快照数据库和目标数据库不能是同一个文件")

    source = sqlite3.connect(f"file:{args.snapshot_db}?mode=ro", uri=True)
    target = sqlite3.connect(args.target_db)
    source.row_factory = sqlite3.Row
    target.row_factory = sqlite3.Row
    source.execute("PRAGMA foreign_keys=ON")
    target.execute("PRAGMA foreign_keys=ON")
    try:
        source_revision = source.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        target_revision = target.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        if (
            not source_revision
            or not target_revision
            or source_revision[0] != target_revision[0]
        ):
            parser.error("快照与目标数据库的 Alembic revision 不一致")
        source_user = source.execute(
            "SELECT id, template_version FROM users WHERE id = ?",
            (args.user_id,),
        ).fetchone()
        target_user = target.execute(
            "SELECT id, is_active FROM users WHERE id = ?",
            (args.user_id,),
        ).fetchone()
        if not source_user or not target_user:
            parser.error("用户必须同时存在于快照和目标数据库")
        if target_user["is_active"]:
            parser.error("恢复前必须先停用目标用户")

        chat_columns = (
            "id",
            "user_id",
            "title",
            "claude_session_id",
            "is_archived",
            "created_at",
            "updated_at",
        )
        job_columns = (
            "id",
            "user_id",
            "chat_id",
            "state",
            "prompt",
            "runner_unit",
            "error",
            "created_at",
            "started_at",
            "finished_at",
        )
        file_columns = (
            "id",
            "user_id",
            "relative_path",
            "original_name",
            "mime_type",
            "size_bytes",
            "extracted_path",
            "created_at",
        )
        usage_columns = (
            "user_id",
            "day",
            "jobs",
            "api_requests",
            "input_tokens",
            "output_tokens",
            "total_tokens",
        )
        chats = rows(
            source,
            f"SELECT {', '.join(chat_columns)} FROM chats WHERE user_id = ?",
            (args.user_id,),
        )
        chat_ids = [item["id"] for item in chats]
        jobs = rows(
            source,
            f"SELECT {', '.join(job_columns)} FROM jobs WHERE user_id = ?",
            (args.user_id,),
        )
        job_ids = [item["id"] for item in jobs]
        messages = (
            rows(
                source,
                "SELECT chat_id, role, content, created_at FROM messages "
                f"WHERE chat_id IN ({', '.join('?' for _ in chat_ids)})",
                tuple(chat_ids),
            )
            if chat_ids
            else []
        )
        events = (
            rows(
                source,
                "SELECT job_id, seq, type, data_json, created_at "
                f"FROM job_events WHERE job_id IN "
                f"({', '.join('?' for _ in job_ids)})",
                tuple(job_ids),
            )
            if job_ids
            else []
        )
        usage = rows(
            source,
            f"SELECT {', '.join(usage_columns)} "
            "FROM daily_usage WHERE user_id = ?",
            (args.user_id,),
        )
        files = rows(
            source,
            f"SELECT {', '.join(file_columns)} FROM files WHERE user_id = ?",
            (args.user_id,),
        )

        timestamp = dt.datetime.now(dt.timezone.utc).strftime(
            "%Y%m%dT%H%M%S%fZ"
        )
        backup = args.target_db.with_name(
            f"{args.target_db.name}.before-user-restore-{timestamp}"
        )
        backup_connection = sqlite3.connect(backup)
        try:
            target.backup(backup_connection)
        finally:
            backup_connection.close()
        os.chmod(backup, 0o600)

        target.execute("BEGIN IMMEDIATE")
        current_chat_ids = [
            item[0]
            for item in target.execute(
                "SELECT id FROM chats WHERE user_id = ?",
                (args.user_id,),
            )
        ]
        current_job_ids = [
            item[0]
            for item in target.execute(
                "SELECT id FROM jobs WHERE user_id = ?",
                (args.user_id,),
            )
        ]
        if current_job_ids:
            placeholders = ", ".join("?" for _ in current_job_ids)
            target.execute(
                f"DELETE FROM job_events WHERE job_id IN ({placeholders})",
                tuple(current_job_ids),
            )
        if current_chat_ids:
            placeholders = ", ".join("?" for _ in current_chat_ids)
            target.execute(
                f"DELETE FROM messages WHERE chat_id IN ({placeholders})",
                tuple(current_chat_ids),
            )
        target.execute("DELETE FROM jobs WHERE user_id = ?", (args.user_id,))
        target.execute("DELETE FROM chats WHERE user_id = ?", (args.user_id,))
        target.execute(
            "DELETE FROM daily_usage WHERE user_id = ?",
            (args.user_id,),
        )
        target.execute("DELETE FROM files WHERE user_id = ?", (args.user_id,))
        target.execute(
            "DELETE FROM web_sessions WHERE user_id = ?",
            (args.user_id,),
        )

        insert_rows(target, "chats", chat_columns, chats)
        recovered_jobs = []
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        for job in jobs:
            value = list(job)
            if value[3] in {"queued", "running"}:
                value[3] = "interrupted"
                value[5] = None
                value[6] = "从备份恢复时中断"
                value[9] = now
            recovered_jobs.append(tuple(value))
        insert_rows(target, "jobs", job_columns, recovered_jobs)
        insert_rows(
            target,
            "messages",
            ("chat_id", "role", "content", "created_at"),
            messages,
        )
        insert_rows(
            target,
            "job_events",
            ("job_id", "seq", "type", "data_json", "created_at"),
            events,
        )
        insert_rows(target, "daily_usage", usage_columns, usage)
        insert_rows(target, "files", file_columns, files)
        target.execute(
            "UPDATE users SET template_version = ? WHERE id = ?",
            (source_user["template_version"], args.user_id),
        )
        integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"恢复后数据库完整性检查失败：{integrity}")
        target.commit()
        print(f"单用户数据库记录恢复完成；恢复前副本：{backup}")
    except Exception:
        target.rollback()
        raise
    finally:
        source.close()
        target.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
