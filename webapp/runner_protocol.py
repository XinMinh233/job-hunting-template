from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from .security import SESSION_ID_RE, USER_ID_RE

JOB_ID_RE = USER_ID_RE
STAGING_NAME_RE = re.compile(r"^[0-9a-f]{32}(?:\.[a-z0-9]{1,8})?$")
SAFE_FILENAME_RE = re.compile(r"[^\w.()\[\] -]+", re.UNICODE)
ALLOWED_FILE_ROOTS = {
    "master.md",
    "base",
    "tailored",
    "dist",
    "data",
    "uploads",
}
NORMAL_TURN_LIMIT = 40
LONG_TURN_LIMIT = 80


def validate_user_id(value: object) -> str:
    text = str(value or "")
    if not USER_ID_RE.fullmatch(text):
        raise ValueError("无效用户 ID")
    return text


def validate_job_id(value: object) -> str:
    text = str(value or "")
    if not JOB_ID_RE.fullmatch(text):
        raise ValueError("无效任务 ID")
    return text


def validate_session_id(value: object | None) -> str | None:
    if value in (None, ""):
        return None
    text = str(value)
    if not SESSION_ID_RE.fullmatch(text):
        raise ValueError("无效会话 ID")
    return text


def safe_filename(value: str) -> str:
    cleaned = SAFE_FILENAME_RE.sub("_", Path(value).name).strip(" .")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("无效文件名")
    return cleaned[:180]


def safe_relative_path(value: object) -> str:
    text = str(value or "").replace("\\", "/")
    pure = PurePosixPath(text)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise ValueError("无效文件路径")
    if pure.parts[0] not in ALLOWED_FILE_ROOTS:
        raise ValueError("文件不在允许目录")
    return pure.as_posix()


def resolve_user_file(workspace: Path, relative: str) -> Path:
    safe = safe_relative_path(relative)
    root = workspace.resolve()
    target = (root / safe).resolve()
    if root != target and root not in target.parents:
        raise ValueError("文件路径越界")
    return target
