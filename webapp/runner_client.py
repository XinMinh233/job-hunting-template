from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import mimetypes
import os
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Any, AsyncIterator

from .config import settings
from .runner_protocol import (
    LONG_TURN_LIMIT,
    NORMAL_TURN_LIMIT,
    resolve_user_file,
    safe_filename,
)
from .stream_parser import counts_assistant_turn
from .template_files import copy_template, template_version


class RunnerError(RuntimeError):
    pass


RUNNER_RESPONSE_LIMIT = 4 * 1024 * 1024
CLAUDE_STREAM_LIMIT = 1024 * 1024


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


class RunnerClient:
    def __init__(self) -> None:
        self._development_processes: dict[str, asyncio.subprocess.Process] = {}

    async def _connect(self):
        try:
            return await asyncio.wait_for(
                asyncio.open_unix_connection(
                    str(settings.runner_socket),
                    limit=RUNNER_RESPONSE_LIMIT,
                ),
                timeout=5,
            )
        except (
            FileNotFoundError,
            ConnectionRefusedError,
            PermissionError,
            TimeoutError,
        ) as exc:
            raise RunnerError("系统 Runner 不可用，请联系管理员") from exc

    async def request(self, operation: str, **payload: Any) -> dict[str, Any]:
        if settings.development_runner:
            return await self._development_request(operation, payload)
        reader, writer = await self._connect()
        writer.write(
            (
                json.dumps({"op": operation, **payload}, ensure_ascii=False)
                + "\n"
            ).encode()
        )
        await writer.drain()
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=180)
        except TimeoutError as exc:
            raise RunnerError("Runner 操作超时") from exc
        finally:
            writer.close()
            await writer.wait_closed()
        if not line:
            raise RunnerError("Runner 未返回结果")
        response = json.loads(line)
        if not response.get("ok", False):
            raise RunnerError(str(response.get("error") or "Runner 操作失败"))
        return response

    async def stream_run(
        self,
        *,
        user_id: str,
        job_id: str,
        prompt: str,
        claude_session_id: str | None,
        proxy_token: str,
        long_run: bool,
    ) -> AsyncIterator[dict[str, Any]]:
        if settings.development_runner:
            async for event in self._development_run(
                user_id=user_id,
                job_id=job_id,
                prompt=prompt,
                claude_session_id=claude_session_id,
                proxy_token=proxy_token,
                long_run=long_run,
            ):
                yield event
            return

        reader, writer = await self._connect()
        writer.write(
            (
                json.dumps(
                    {
                        "op": "run",
                        "user_id": user_id,
                        "job_id": job_id,
                        "prompt": prompt,
                        "claude_session_id": claude_session_id,
                        "proxy_token": proxy_token,
                        "long_run": long_run,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            ).encode()
        )
        await writer.drain()
        try:
            while line := await reader.readline():
                event = json.loads(line)
                if event.get("type") == "error":
                    raise RunnerError(str(event.get("error") or "Runner 执行失败"))
                yield event
        finally:
            writer.close()
            await writer.wait_closed()

    async def read_file(
        self, user_id: str, relative_path: str
    ) -> AsyncIterator[bytes]:
        if settings.development_runner:
            workspace = settings.development_root / user_id / "workspace"
            target = resolve_user_file(workspace, relative_path)
            if not target.is_file() or target.is_symlink():
                raise RunnerError("文件不存在")
            with target.open("rb") as handle:
                while chunk := handle.read(64 * 1024):
                    yield chunk
            return

        reader, writer = await self._connect()
        writer.write(
            (
                json.dumps(
                    {
                        "op": "file_read",
                        "user_id": user_id,
                        "relative_path": relative_path,
                    }
                )
                + "\n"
            ).encode()
        )
        await writer.drain()
        try:
            while line := await reader.readline():
                event = json.loads(line)
                if event.get("type") == "error":
                    raise RunnerError(str(event.get("error") or "读取失败"))
                if event.get("type") == "chunk":
                    yield base64.b64decode(event["data"])
                if event.get("type") == "end":
                    break
        finally:
            writer.close()
            await writer.wait_closed()

    async def _development_request(
        self, operation: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        user_id = str(payload.get("user_id") or "")
        root = settings.development_root / user_id
        workspace = root / "workspace"
        if operation == "health":
            process = await asyncio.create_subprocess_exec(
                settings.claude_bin,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _stderr = await process.communicate()
            if process.returncode != 0:
                raise RunnerError("Claude Code 版本检查失败")
            version = stdout.decode(errors="replace").strip()
            if settings.claude_version and settings.claude_version not in version:
                raise RunnerError("Claude Code 版本不符合固定版本要求")
            return {
                "ok": True,
                "mode": "development",
                "claude_version": version,
                "primary_model": settings.primary_model,
                "light_model": settings.light_model,
                "effort_level": settings.effort_level,
            }
        if operation == "provision":
            if root.exists():
                raise RunnerError("开发用户目录已存在")
            copy_template(settings.template_root, workspace)
            (root / "home").mkdir(parents=True)
            git_env = {
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "HOME": str(root / "home"),
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "core.hooksPath",
                "GIT_CONFIG_VALUE_0": "/dev/null",
            }
            subprocess.run(
                ["git", "init", "-q"],
                cwd=workspace,
                env=git_env,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Job Hunt Development"],
                cwd=workspace,
                env=git_env,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "jobhunt@localhost"],
                cwd=workspace,
                env=git_env,
                check=True,
            )
            subprocess.run(
                ["git", "add", "."],
                cwd=workspace,
                env=git_env,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-q", "-m", "system: initialize workspace"],
                cwd=workspace,
                env=git_env,
                check=True,
            )
            return {
                "ok": True,
                "linux_username": f"dev_{user_id[:8]}",
                "workspace_path": str(workspace),
                "template_version": template_version(settings.template_root),
            }
        if operation in {"disable", "enable"}:
            return {"ok": True}
        if operation == "file_list":
            files = []
            if workspace.exists():
                for path in workspace.rglob("*"):
                    if path.is_file() and not path.is_symlink():
                        relative = path.relative_to(workspace).as_posix()
                        if relative.split("/", 1)[0] in {
                            "base",
                            "tailored",
                            "dist",
                            "data",
                            "uploads",
                        } or relative == "master.md":
                            files.append(
                                {
                                    "relative_path": relative,
                                    "size": path.stat().st_size,
                                    "mime_type": mimetypes.guess_type(path.name)[0]
                                    or "application/octet-stream",
                                    "modified_ns": path.stat().st_mtime_ns,
                                }
                            )
            return {"ok": True, "files": files[:1000]}
        if operation == "file_import":
            staging = settings.staging_root / user_id / str(payload["staging_name"])
            filename = safe_filename(str(payload["filename"]))
            destination = workspace / "uploads" / str(payload["upload_id"]) / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            extracted_name = payload.get("extracted_staging_name")
            extracted_destination = None
            extracted_staging = None
            if extracted_name:
                extracted_staging = (
                    settings.staging_root / user_id / str(extracted_name)
                )
                extracted_destination = (
                    destination.parent
                    / safe_filename(str(payload["extracted_filename"]))
                )
            moved: list[tuple[Path, Path]] = []
            committed_paths = [destination.relative_to(workspace).as_posix()]
            if extracted_destination:
                committed_paths.append(
                    extracted_destination.relative_to(workspace).as_posix()
                )
            try:
                shutil.move(str(staging), destination)
                moved.append((destination, staging))
                destination.chmod(0o444)
                if extracted_staging and extracted_destination:
                    shutil.move(str(extracted_staging), extracted_destination)
                    moved.append((extracted_destination, extracted_staging))
                    extracted_destination.chmod(0o444)
                destination.parent.chmod(0o555)
                git_env = {
                    "PATH": "/usr/local/bin:/usr/bin:/bin",
                    "HOME": str(root / "home"),
                    "GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "core.hooksPath",
                    "GIT_CONFIG_VALUE_0": "/dev/null",
                }
                subprocess.run(
                    ["git", "add", "--", *committed_paths],
                    cwd=workspace,
                    env=git_env,
                    check=True,
                )
                subprocess.run(
                    [
                        "git",
                        "commit",
                        "-q",
                        "-m",
                        f"user: upload {filename}",
                        "--",
                        *committed_paths,
                    ],
                    cwd=workspace,
                    env=git_env,
                    check=True,
                )
            except Exception:
                subprocess.run(
                    ["git", "reset", "-q", "--", *committed_paths],
                    cwd=workspace,
                    env={
                        "PATH": "/usr/local/bin:/usr/bin:/bin",
                        "HOME": str(root / "home"),
                    },
                    check=False,
                )
                destination.parent.chmod(0o700)
                for imported, original in reversed(moved):
                    if imported.exists() and not original.exists():
                        shutil.move(str(imported), original)
                raise
            return {
                "ok": True,
                "relative_path": destination.relative_to(workspace).as_posix(),
                "extracted_relative_path": (
                    extracted_destination.relative_to(workspace).as_posix()
                    if extracted_destination
                    else None
                ),
            }
        if operation == "upgrade":
            raise RunnerError("开发模式暂未启用模板升级")
        if operation == "stop":
            process = self._development_processes.get(str(payload.get("job_id")))
            if process and process.returncode is None:
                os.killpg(process.pid, signal.SIGTERM)
            return {"ok": True, "found": bool(process)}
        raise RunnerError("开发 Runner 不支持该操作")

    async def _development_run(
        self,
        *,
        user_id: str,
        job_id: str,
        prompt: str,
        claude_session_id: str | None,
        proxy_token: str,
        long_run: bool,
    ) -> AsyncIterator[dict[str, Any]]:
        workspace = settings.development_root / user_id / "workspace"
        home = settings.development_root / user_id / "home"
        command = [
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
        if claude_session_id:
            command.extend(["--resume", claude_session_id])
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(home),
            "ANTHROPIC_BASE_URL": settings.proxy_base_url,
            "ANTHROPIC_AUTH_TOKEN": proxy_token,
            "ANTHROPIC_API_KEY": proxy_token,
            "ANTHROPIC_MODEL": settings.primary_model,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": settings.primary_model,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": settings.primary_model,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": settings.light_model,
            "CLAUDE_CODE_SUBAGENT_MODEL": settings.light_model,
            "CLAUDE_CODE_EFFORT_LEVEL": settings.effort_level,
            "DISABLE_AUTOUPDATER": "1",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.hooksPath",
            "GIT_CONFIG_VALUE_0": "/dev/null",
        }
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=workspace,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            limit=CLAUDE_STREAM_LIMIT,
        )
        self._development_processes[job_id] = process
        assert process.stdin and process.stdout
        stderr_task = asyncio.create_task(_stderr_tail(process.stderr))
        process.stdin.write(prompt.encode())
        await process.stdin.drain()
        process.stdin.close()
        yield {"type": "started", "unit": f"dev-{job_id}"}
        turn_limit = LONG_TURN_LIMIT if long_run else NORMAL_TURN_LIMIT
        turns = 0
        while line := await process.stdout.readline():
            decoded = line.decode(errors="replace").rstrip()
            if counts_assistant_turn(decoded):
                turns += 1
                if turns > turn_limit:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGTERM)
                    await process.wait()
                    await stderr_task
                    yield {
                        "type": "exit",
                        "code": 124,
                        "stderr": f"turn limit exceeded ({turn_limit})",
                    }
                    return
            yield {"type": "output", "line": decoded}
        try:
            code = await process.wait()
            stderr = await stderr_task
            yield {"type": "exit", "code": code, "stderr": stderr[-4000:]}
        finally:
            if not stderr_task.done():
                stderr_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await stderr_task
            self._development_processes.pop(job_id, None)


runner_client = RunnerClient()
