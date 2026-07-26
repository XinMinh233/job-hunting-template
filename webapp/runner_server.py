from __future__ import annotations

import asyncio
import base64
import contextlib
import datetime as dt
import grp
import json
import mimetypes
import os
import pwd
import re
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

from .config import settings
from .runner_protocol import (
    LONG_TURN_LIMIT,
    NORMAL_TURN_LIMIT,
    STAGING_NAME_RE,
    resolve_user_file,
    safe_filename,
    safe_relative_path,
    validate_job_id,
    validate_session_id,
    validate_user_id,
)
from .stream_parser import counts_assistant_turn
from .template_files import (
    atomic_json,
    copy_template,
    template_version,
    upgrade_template,
)

MAX_REQUEST = 512 * 1024
CLAUDE_STREAM_LIMIT = 1024 * 1024
SYSTEM_USER_RE = re.compile(r"^jh_[0-9a-f]{12}$")


class Registry:
    def __init__(self, path: Path):
        self.path = path
        self.lock = asyncio.Lock()
        self.data: dict[str, dict[str, Any]] = {}

    def load(self) -> None:
        if self.path.is_file():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        atomic_json(self.path, self.data)
        os.chmod(self.path, 0o600)

    def get(self, user_id: str, *, enabled: bool = True) -> dict[str, Any]:
        entry = self.data.get(user_id)
        if not entry:
            raise ValueError("Runner 中不存在该用户")
        if enabled and not entry.get("enabled", False):
            raise ValueError("该用户已停用")
        return entry


registry = Registry(settings.runner_registry)
active_units: dict[str, str] = {}
cancelled_jobs: dict[str, float] = {}


def _prune_cancelled_jobs() -> None:
    cutoff = asyncio.get_running_loop().time() - 3600
    for job_id, cancelled_at in list(cancelled_jobs.items()):
        if cancelled_at < cutoff:
            cancelled_jobs.pop(job_id, None)


def _linux_name(user_id: str) -> str:
    return "jh_" + user_id.replace("-", "")[:12]


def _recursive_chown(path: Path, uid: int, gid: int) -> None:
    os.chown(path, uid, gid)
    for root, directories, files in os.walk(path):
        for name in directories:
            os.chown(Path(root) / name, uid, gid)
        for name in files:
            os.chown(Path(root) / name, uid, gid)


def _chown_path_to_workspace(
    path: Path,
    workspace: Path,
    uid: int,
    gid: int,
) -> None:
    current = path
    while current != workspace:
        os.chown(current, uid, gid)
        current = current.parent


def _drop_privileges(uid: int, gid: int):
    def apply() -> None:
        os.setgroups([])
        os.setgid(gid)
        os.setuid(uid)
        os.umask(0o077)

    return apply


def _run_as(entry: dict[str, Any], args: list[str], *, check: bool = True):
    user = pwd.getpwnam(entry["linux_username"])
    return subprocess.run(
        args,
        cwd=entry["workspace"],
        env={
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": entry["home"],
            "LANG": "C.UTF-8",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.hooksPath",
            "GIT_CONFIG_VALUE_0": "/dev/null",
        },
        preexec_fn=_drop_privileges(user.pw_uid, user.pw_gid),
        capture_output=True,
        text=True,
        check=check,
        timeout=120,
    )


async def _send(writer: asyncio.StreamWriter, payload: dict[str, Any]) -> None:
    writer.write((json.dumps(payload, ensure_ascii=False) + "\n").encode())
    await writer.drain()


async def _stderr_tail(
    stream: asyncio.StreamReader | None,
    limit: int = 4000,
) -> str:
    if stream is None:
        return ""
    tail = bytearray()
    while chunk := await stream.read(4096):
        tail.extend(chunk)
        if len(tail) > limit:
            del tail[:-limit]
    return tail.decode(errors="replace")


async def _provision(request: dict[str, Any]) -> dict[str, Any]:
    user_id = validate_user_id(request.get("user_id"))
    async with registry.lock:
        if user_id in registry.data:
            raise ValueError("用户已经开通")
        linux_name = _linux_name(user_id)
        if not SYSTEM_USER_RE.fullmatch(linux_name):
            raise ValueError("生成的 Linux 用户名无效")
        user_root = settings.users_root / user_id
        home = user_root / "home"
        workspace = user_root / "workspace"
        if user_root.exists():
            raise ValueError("用户目录已经存在")

        subprocess.run(
            [
                "useradd",
                "--system",
                "--user-group",
                "--no-create-home",
                "--home-dir",
                str(home),
                "--shell",
                "/usr/sbin/nologin",
                linux_name,
            ],
            check=True,
            timeout=30,
        )
        subprocess.run(["usermod", "--lock", linux_name], check=True, timeout=30)
        user = pwd.getpwnam(linux_name)
        try:
            home.mkdir(parents=True, mode=0o700)
            workspace.mkdir(parents=True, mode=0o700)
            hashes = copy_template(settings.template_root, workspace)
            (workspace / "uploads").mkdir(mode=0o700)
            _recursive_chown(user_root, user.pw_uid, user.pw_gid)
            os.chmod(user_root, 0o700)
            os.chmod(home, 0o700)
            os.chmod(workspace, 0o700)
            entry = {
                "linux_username": linux_name,
                "home": str(home),
                "workspace": str(workspace),
                "enabled": True,
                "template_version": template_version(settings.template_root),
                "template_hashes": hashes,
            }
            _run_as(entry, ["git", "init", "-q"])
            _run_as(entry, ["git", "config", "user.name", "Job Hunt System"])
            _run_as(
                entry,
                ["git", "config", "user.email", f"{linux_name}@localhost"],
            )
            _run_as(entry, ["git", "add", "."])
            _run_as(
                entry,
                ["git", "commit", "-q", "-m", "system: initialize workspace"],
            )
            registry.data[user_id] = entry
            registry.save()
        except Exception:
            shutil.rmtree(user_root, ignore_errors=True)
            subprocess.run(["userdel", linux_name], check=False)
            raise
    return {
        "ok": True,
        "linux_username": linux_name,
        "workspace_path": str(workspace),
        "template_version": entry["template_version"],
    }


async def _disable(request: dict[str, Any]) -> dict[str, Any]:
    user_id = validate_user_id(request.get("user_id"))
    async with registry.lock:
        entry = registry.get(user_id, enabled=False)
        entry["enabled"] = False
        registry.save()
    for job_id, unit in list(active_units.items()):
        if unit.startswith(f"jh-{user_id.replace('-', '')[:12]}-"):
            subprocess.run(["systemctl", "stop", unit], check=False)
            active_units.pop(job_id, None)
    return {"ok": True}


async def _enable(request: dict[str, Any]) -> dict[str, Any]:
    user_id = validate_user_id(request.get("user_id"))
    async with registry.lock:
        entry = registry.get(user_id, enabled=False)
        entry["enabled"] = True
        registry.save()
    return {"ok": True}


async def _health(_request: dict[str, Any]) -> dict[str, Any]:
    if settings.effort_level not in {"low", "medium", "high", "max"}:
        raise ValueError("Claude Code effort level 配置无效")
    try:
        version = await asyncio.to_thread(
            subprocess.run,
            [settings.claude_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        claude_version = version.stdout.strip() or version.stderr.strip()
        help_result = await asyncio.to_thread(
            subprocess.run,
            [settings.claude_bin, "--help"],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
    except Exception as exc:
        raise ValueError("Claude Code 不可用或版本检查失败") from exc
    if (
        settings.claude_version
        and settings.claude_version not in claude_version
    ):
        raise ValueError(
            "Claude Code 版本不符合固定版本要求："
            f"期望 {settings.claude_version}"
        )
    required_flags = {
        "--print",
        "--input-format",
        "--output-format",
        "--include-partial-messages",
        "--allowedTools",
        "--permission-mode",
        "--resume",
        "--setting-sources",
        "--tools",
        "--verbose",
    }
    missing_flags = sorted(
        flag for flag in required_flags if flag not in help_result.stdout
    )
    if missing_flags:
        raise ValueError(
            "Claude Code 缺少固定 Runner 所需参数："
            + ", ".join(missing_flags)
        )
    return {
        "ok": True,
        "active": len(active_units),
        "claude_version": claude_version[:160],
        "primary_model": settings.primary_model,
        "light_model": settings.light_model,
        "effort_level": settings.effort_level,
    }


async def _stop(request: dict[str, Any]) -> dict[str, Any]:
    job_id = validate_job_id(request.get("job_id"))
    unit = active_units.get(job_id)
    _prune_cancelled_jobs()
    cancelled_jobs[job_id] = asyncio.get_running_loop().time()
    if unit:
        subprocess.run(["systemctl", "stop", unit], check=False, timeout=30)
    return {"ok": True, "found": bool(unit)}


def _allowed_files(workspace: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    roots = ["master.md", "base", "tailored", "dist", "data", "uploads"]
    for root_name in roots:
        root = workspace / root_name
        if root.is_file():
            candidates = [root]
        elif root.is_dir():
            candidates = root.rglob("*")
        else:
            candidates = []
        for path in candidates:
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(workspace).as_posix()
            results.append(
                {
                    "relative_path": relative,
                    "size": path.stat().st_size,
                    "mime_type": mimetypes.guess_type(path.name)[0]
                    or "application/octet-stream",
                    "modified_ns": path.stat().st_mtime_ns,
                }
            )
            if len(results) >= 1000:
                return sorted(results, key=lambda item: item["relative_path"])
    return sorted(results, key=lambda item: item["relative_path"])


async def _file_list(request: dict[str, Any]) -> dict[str, Any]:
    user_id = validate_user_id(request.get("user_id"))
    entry = registry.get(user_id)
    return {
        "ok": True,
        "files": _allowed_files(Path(entry["workspace"])),
    }


async def _file_import(request: dict[str, Any]) -> dict[str, Any]:
    user_id = validate_user_id(request.get("user_id"))
    entry = registry.get(user_id)
    staging_name = str(request.get("staging_name") or "")
    if not STAGING_NAME_RE.fullmatch(staging_name):
        raise ValueError("无效暂存文件")
    upload_id = validate_job_id(request.get("upload_id"))
    filename = safe_filename(str(request.get("filename") or ""))
    extracted_staging_name = request.get("extracted_staging_name")
    extracted_filename = request.get("extracted_filename")

    def validated_staging(name: str) -> Path:
        if not STAGING_NAME_RE.fullmatch(name):
            raise ValueError("无效暂存文件")
        path = settings.staging_root / user_id / name
        path_stat = path.lstat() if path.exists() else None
        if (
            path_stat is None
            or not stat.S_ISREG(path_stat.st_mode)
            or path_stat.st_nlink != 1
        ):
            raise ValueError("暂存文件不存在")
        if path_stat.st_size > settings.max_upload_bytes:
            raise ValueError("文件超过大小限制")
        return path

    staging = validated_staging(staging_name)
    workspace = Path(entry["workspace"])
    relative_target = f"uploads/{upload_id}/{filename}"
    target = resolve_user_file(workspace, relative_target)
    if target.exists() or target.is_symlink():
        raise ValueError("目标文件已存在，禁止覆盖")
    extracted_staging = None
    extracted_target = None
    if extracted_staging_name not in (None, ""):
        extracted_staging = validated_staging(str(extracted_staging_name))
        clean_extracted_name = safe_filename(str(extracted_filename or ""))
        extracted_target = resolve_user_file(
            workspace,
            f"uploads/{upload_id}/{clean_extracted_name}",
        )
        if extracted_target.exists() or extracted_target.is_symlink():
            raise ValueError("提取文本目标已存在，禁止覆盖")
    target.parent.mkdir(parents=True, exist_ok=True)
    moved: list[tuple[Path, Path]] = []
    committed_paths = [target.relative_to(workspace).as_posix()]
    if extracted_target:
        committed_paths.append(extracted_target.relative_to(workspace).as_posix())
    try:
        shutil.move(staging, target)
        moved.append((target, staging))
        if extracted_staging and extracted_target:
            shutil.move(extracted_staging, extracted_target)
            moved.append((extracted_target, extracted_staging))
        os.chown(target.parent, 0, 0)
        os.chown(target, 0, 0)
        os.chmod(target, 0o444)
        if extracted_target:
            os.chown(extracted_target, 0, 0)
            os.chmod(extracted_target, 0o444)
        os.chmod(target.parent, 0o555)
        _run_as(entry, ["git", "add", "--", *committed_paths])
        _run_as(
            entry,
            [
                "git",
                "commit",
                "-q",
                "-m",
                f"user: upload {filename}",
                "--",
                *committed_paths,
            ],
        )
    except Exception:
        with contextlib.suppress(Exception):
            _run_as(
                entry,
                ["git", "reset", "-q", "--", *committed_paths],
                check=False,
            )
        with contextlib.suppress(Exception):
            os.chmod(target.parent, 0o700)
        for imported, original in reversed(moved):
            if imported.exists() and not original.exists():
                shutil.move(imported, original)
        raise
    return {
        "ok": True,
        "relative_path": target.relative_to(workspace).as_posix(),
        "size": target.stat().st_size,
        "extracted_relative_path": (
            extracted_target.relative_to(workspace).as_posix()
            if extracted_target
            else None
        ),
    }


async def _file_read(
    request: dict[str, Any], writer: asyncio.StreamWriter
) -> None:
    user_id = validate_user_id(request.get("user_id"))
    entry = registry.get(user_id)
    relative = safe_relative_path(request.get("relative_path"))
    target = resolve_user_file(Path(entry["workspace"]), relative)
    if target.is_symlink() or not target.is_file():
        raise ValueError("文件不存在")
    await _send(
        writer,
        {
            "type": "file",
            "size": target.stat().st_size,
            "mime_type": mimetypes.guess_type(target.name)[0]
            or "application/octet-stream",
        },
    )
    with target.open("rb") as handle:
        while chunk := handle.read(48 * 1024):
            await _send(
                writer,
                {
                    "type": "chunk",
                    "data": base64.b64encode(chunk).decode(),
                },
            )
    await _send(writer, {"type": "end"})


async def _upgrade(request: dict[str, Any]) -> dict[str, Any]:
    user_id = validate_user_id(request.get("user_id"))
    async with registry.lock:
        entry = registry.get(user_id)
        status_result = await asyncio.to_thread(
            _run_as,
            entry,
            ["git", "status", "--porcelain"],
        )
        if status_result.stdout.strip():
            raise ValueError("Git 工作区不干净，已停止升级")
        result = upgrade_template(
            settings.template_root,
            Path(entry["workspace"]),
            entry.get("template_hashes") or {},
        )
        version_slug = re.sub(
            r"[^a-zA-Z0-9_.-]", "-", str(result["version"])
        )[:64]
        timestamp = dt.datetime.now(dt.timezone.utc).strftime(
            "%Y%m%dT%H%M%S%fZ"
        )
        report_relative = (
            Path("data")
            / "template-upgrade-reports"
            / f"{version_slug}-{timestamp}.md"
        )
        report_path = Path(entry["workspace"]) / report_relative
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            "\n".join(
                [
                    f"# 模板升级报告：{result['version']}",
                    "",
                    f"- 时间（UTC）：{timestamp}",
                    f"- 已更新：{len(result['updated'])}",
                    f"- 冲突跳过：{len(result['conflicts'])}",
                    f"- 个人文件保留：{len(result['skipped'])}",
                    "",
                    "## 冲突文件",
                    "",
                    *(
                        [f"- `{item}`" for item in result["conflicts"]]
                        or ["- 无"]
                    ),
                    "",
                    "## 已更新文件",
                    "",
                    *(
                        [f"- `{item}`" for item in result["updated"]]
                        or ["- 无"]
                    ),
                    "",
                ]
            ),
            encoding="utf-8",
        )
        user = pwd.getpwnam(entry["linux_username"])
        workspace = Path(entry["workspace"])
        for relative in result["updated"]:
            _chown_path_to_workspace(
                workspace / str(relative),
                workspace,
                user.pw_uid,
                user.pw_gid,
            )
        _chown_path_to_workspace(
            report_path,
            workspace,
            user.pw_uid,
            user.pw_gid,
        )
        await asyncio.to_thread(_run_as, entry, ["git", "add", "."])
        await asyncio.to_thread(
            _run_as,
            entry,
            [
                "git",
                "commit",
                "-q",
                "-m",
                f"system: upgrade template {result['version']}",
            ],
        )
        entry["template_hashes"] = result["hashes"]
        entry["template_version"] = result["version"]
        registry.save()
    return {
        "ok": True,
        "version": result["version"],
        "updated": result["updated"],
        "conflicts": result["conflicts"],
        "report_path": report_relative.as_posix(),
    }


def _systemd_command(
    *,
    entry: dict[str, Any],
    user_id: str,
    job_id: str,
    session_id: str | None,
    proxy_token: str,
    long_run: bool,
) -> tuple[str, list[str]]:
    unit = f"jh-{user_id.replace('-', '')[:12]}-{job_id.replace('-', '')[:12]}"
    timeout = 1800 if long_run else 900
    writable = f"{entry['home']} {entry['workspace']}"
    policy_binds = [
        (
            settings.template_root / ".claude" / "settings.json",
            Path(entry["workspace"]) / ".claude" / "settings.json",
        ),
        *[
            (
                settings.template_root / script,
                Path(entry["workspace"]) / script,
            )
            for script in (
                "build_resumes.py",
                "resume_lint.py",
                "build_dashboard.py",
                "build_career_tree.py",
                "check_links.py",
            )
        ],
    ]
    command = [
        "systemd-run",
        "--quiet",
        "--pipe",
        "--wait",
        "--collect",
        f"--unit={unit}",
        f"--uid={entry['linux_username']}",
        f"--gid={entry['linux_username']}",
        f"--working-directory={entry['workspace']}",
        "--property=MemoryMax=2G",
        "--property=CPUQuota=100%",
        "--property=TasksMax=128",
        f"--property=RuntimeMaxSec={timeout}",
        "--property=PrivateTmp=yes",
        "--property=PrivateDevices=yes",
        "--property=NoNewPrivileges=yes",
        "--property=RestrictSUIDSGID=yes",
        "--property=LockPersonality=yes",
        "--property=ProtectKernelTunables=yes",
        "--property=ProtectKernelModules=yes",
        "--property=ProtectKernelLogs=yes",
        "--property=ProtectControlGroups=yes",
        "--property=CapabilityBoundingSet=",
        "--property=RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
        "--property=KillMode=control-group",
        "--property=BindsTo=jobhunt-runner.service jobhunt-web.service",
        "--property=After=jobhunt-runner.service jobhunt-web.service",
        "--property=ProtectSystem=strict",
        "--property=ProtectProc=invisible",
        f"--property=ReadWritePaths={writable}",
        f"--property=BindReadOnlyPaths={entry['workspace']}/.git/config",
        f"--setenv=HOME={entry['home']}",
        "--setenv=LANG=C.UTF-8",
        f"--setenv=ANTHROPIC_BASE_URL={settings.proxy_base_url}",
        f"--setenv=ANTHROPIC_AUTH_TOKEN={proxy_token}",
        f"--setenv=ANTHROPIC_API_KEY={proxy_token}",
        f"--setenv=ANTHROPIC_MODEL={settings.primary_model}",
        f"--setenv=ANTHROPIC_DEFAULT_OPUS_MODEL={settings.primary_model}",
        f"--setenv=ANTHROPIC_DEFAULT_SONNET_MODEL={settings.primary_model}",
        f"--setenv=ANTHROPIC_DEFAULT_HAIKU_MODEL={settings.light_model}",
        f"--setenv=CLAUDE_CODE_SUBAGENT_MODEL={settings.light_model}",
        f"--setenv=CLAUDE_CODE_EFFORT_LEVEL={settings.effort_level}",
        "--setenv=DISABLE_AUTOUPDATER=1",
        "--setenv=GIT_CONFIG_COUNT=1",
        "--setenv=GIT_CONFIG_KEY_0=core.hooksPath",
        "--setenv=GIT_CONFIG_VALUE_0=/dev/null",
    ]
    for source, destination in policy_binds:
        if source.is_file() and destination.is_file():
            command.append(
                f"--property=BindReadOnlyPaths={source}:{destination}"
            )
    command.extend(
        [
            settings.claude_bin,
            "--print",
            "--input-format",
            "text",
            "--output-format",
            "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--tools",
            "Read,Write,Edit,Glob,Grep,Task,WebSearch,WebFetch,Bash",
            "--setting-sources",
            "project",
            "--permission-mode",
            "acceptEdits",
            "--allowedTools",
            "Read,Write,Edit,Glob,Grep,Task,WebSearch,WebFetch,"
            "Bash(python3 build_resumes.py:*),"
            "Bash(python3 resume_lint.py:*),"
            "Bash(python3 build_dashboard.py:*),"
            "Bash(python3 build_career_tree.py:*),"
            "Bash(python3 check_links.py:*),"
            "Bash(git status:*),Bash(git log:*),Bash(git diff:*),"
            "Bash(git add:*),Bash(git commit:*)",
        ]
    )
    if session_id:
        command.extend(["--resume", session_id])
    return unit, command


async def _run(
    request: dict[str, Any], writer: asyncio.StreamWriter
) -> None:
    user_id = validate_user_id(request.get("user_id"))
    job_id = validate_job_id(request.get("job_id"))
    session_id = validate_session_id(request.get("claude_session_id"))
    prompt = str(request.get("prompt") or "")
    proxy_token = str(request.get("proxy_token") or "")
    if not prompt or len(prompt) > 100_000:
        raise ValueError("消息为空或过长")
    if len(proxy_token) > 4096 or "." not in proxy_token:
        raise ValueError("代理凭证无效")
    entry = registry.get(user_id)
    unit, command = _systemd_command(
        entry=entry,
        user_id=user_id,
        job_id=job_id,
        session_id=session_id,
        proxy_token=proxy_token,
        long_run=bool(request.get("long_run")),
    )
    active_units[job_id] = unit
    await _send(writer, {"type": "started", "unit": unit})
    process: asyncio.subprocess.Process | None = None
    stderr_task: asyncio.Task[str] | None = None
    turn_limit = LONG_TURN_LIMIT if bool(request.get("long_run")) else NORMAL_TURN_LIMIT
    turns = 0
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=CLAUDE_STREAM_LIMIT,
        )
        stderr_task = asyncio.create_task(_stderr_tail(process.stderr))
        if job_id in cancelled_jobs:
            subprocess.run(["systemctl", "stop", unit], check=False, timeout=30)
            process.terminate()
            await process.wait()
            await _send(writer, {"type": "exit", "code": 130, "stderr": ""})
            return
        assert process.stdin and process.stdout
        process.stdin.write(prompt.encode())
        await process.stdin.drain()
        process.stdin.close()
        while line := await process.stdout.readline():
            decoded = line.decode(errors="replace").rstrip()
            if counts_assistant_turn(decoded):
                turns += 1
                if turns > turn_limit:
                    subprocess.run(
                        ["systemctl", "stop", unit],
                        check=False,
                        timeout=30,
                    )
                    with contextlib.suppress(ProcessLookupError):
                        process.terminate()
                    await process.wait()
                    await stderr_task
                    await _send(
                        writer,
                        {
                            "type": "exit",
                            "code": 124,
                            "stderr": f"turn limit exceeded ({turn_limit})",
                        },
                    )
                    return
            await _send(
                writer,
                {
                    "type": "output",
                    "line": decoded,
                },
            )
        code = await process.wait()
        stderr = await stderr_task
        await _send(writer, {"type": "exit", "code": code, "stderr": stderr})
    finally:
        if process is not None and process.returncode is None:
            subprocess.run(["systemctl", "stop", unit], check=False, timeout=30)
            process.terminate()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(process.wait(), timeout=10)
        if stderr_task is not None and not stderr_task.done():
            stderr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stderr_task
        active_units.pop(job_id, None)
        cancelled_jobs.pop(job_id, None)


async def handle_client(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    try:
        line = await reader.readline()
        if not line or len(line) > MAX_REQUEST:
            raise ValueError("Runner 请求无效或过大")
        request = json.loads(line)
        operation = request.get("op")
        if operation == "run":
            await _run(request, writer)
        elif operation == "file_read":
            await _file_read(request, writer)
        else:
            handlers = {
                "provision": _provision,
                "disable": _disable,
                "enable": _enable,
                "stop": _stop,
                "upgrade": _upgrade,
                "file_list": _file_list,
                "file_import": _file_import,
                "health": _health,
            }
            handler = handlers.get(str(operation))
            if not handler:
                raise ValueError("不支持的 Runner 操作")
            response = await handler(request)
            await _send(writer, response)
    except Exception as exc:
        with contextlib.suppress(Exception):
            await _send(writer, {"ok": False, "type": "error", "error": str(exc)})
    finally:
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()


async def serve() -> None:
    if os.geteuid() != 0:
        raise SystemExit("jobhunt-runner 必须以 root 运行")
    settings.runner_socket.parent.mkdir(parents=True, exist_ok=True)
    settings.users_root.mkdir(parents=True, exist_ok=True)
    settings.runner_registry.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(FileNotFoundError):
        settings.runner_socket.unlink()
    registry.load()
    if not settings.runner_registry.exists():
        registry.save()
    await _health({})
    server = await asyncio.start_unix_server(
        handle_client,
        path=str(settings.runner_socket),
        limit=MAX_REQUEST,
    )
    os.chmod(settings.runner_socket, 0o660)
    group_name = os.getenv("JOBHUNT_WEB_GROUP", "jobhunt-web")
    try:
        group = grp.getgrnam(group_name)
        os.chown(settings.runner_socket, 0, group.gr_gid)
    except KeyError as exc:
        raise SystemExit(f"系统组不存在：{group_name}") from exc
    async with server:
        await server.serve_forever()


def run() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    run()
