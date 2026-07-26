#!/usr/bin/env python3
"""在专用测试账号上执行真实 Claude/DeepSeek Web 验收流程。"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx

REQUIRED_STEPS = {"onboard", "continue", "match", "tailor", "pdf", "scout"}


def fail(message: str) -> None:
    raise RuntimeError(message)


def api(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    csrf: str = "",
    payload: dict[str, Any] | None = None,
) -> Any:
    headers = {"X-CSRF-Token": csrf} if csrf else {}
    response = client.request(method, path, headers=headers, json=payload)
    if response.status_code >= 400:
        fail(f"{method} {path} 失败：{response.status_code} {response.text[:500]}")
    return response.json()


def wait_for_job(client: httpx.Client, job_id: str) -> None:
    with client.stream("GET", f"/api/jobs/{job_id}/events") as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            envelope = json.loads(line[6:])
            event_type = envelope.get("type")
            data = envelope.get("data") or {}
            if event_type == "error":
                fail(f"任务 {job_id} 失败：{data.get('message', '未知错误')}")
            if event_type == "done":
                return
    fail(f"任务 {job_id} 的 SSE 在完成前关闭")


def assert_patterns(
    files: list[dict[str, Any]],
    patterns: list[str],
    changed_patterns: list[str],
    before: dict[str, int],
) -> None:
    paths = [str(item.get("relative_path") or "") for item in files]
    for pattern in patterns:
        if not any(fnmatch.fnmatch(path, pattern) for path in paths):
            fail(f"没有找到预期产物 {pattern}；当前共 {len(paths)} 个文件")
    modified = {
        str(item.get("relative_path") or ""): int(item.get("modified_ns") or 0)
        for item in files
    }
    for pattern in changed_patterns:
        if not any(
            fnmatch.fnmatch(path, pattern)
            and before.get(path) != modified.get(path)
            for path in paths
        ):
            fail(f"预期文件没有新建或更新：{pattern}")


def check_workspace(registry_path: Path, user_id: str) -> None:
    if not registry_path.is_file():
        print("跳过 Git 检查：Runner registry 不可读")
        return
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    entry = registry.get(user_id)
    if not entry:
        fail("Runner registry 中没有测试用户")
    workspace = Path(entry["workspace"])
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    if status.stdout:
        fail("真实流程结束后 Git 工作区不干净")
    print(f"通过：Git 工作区干净（{workspace}）")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument(
        "--password-env",
        default="JOBHUNT_LIVE_PASSWORD",
        help="读取测试账号密码的环境变量名",
    )
    parser.add_argument(
        "--commands",
        type=Path,
        required=True,
        help="验收步骤 JSON 文件",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("/var/lib/jobhunt-runner/registry.json"),
    )
    args = parser.parse_args()
    password = os.getenv(args.password_env)
    if not password:
        parser.error(f"环境变量 {args.password_env} 未设置")
    steps = json.loads(args.commands.read_text(encoding="utf-8"))
    if not isinstance(steps, list):
        parser.error("commands 顶层必须是数组")
    names = {str(item.get("name")) for item in steps if isinstance(item, dict)}
    if not REQUIRED_STEPS.issubset(names):
        parser.error(
            "commands 必须覆盖 onboard、continue、match、tailor、pdf、scout"
        )

    timeout = httpx.Timeout(connect=20, read=1900, write=30, pool=30)
    with httpx.Client(
        base_url=args.base_url.rstrip("/"),
        timeout=timeout,
        follow_redirects=False,
    ) as client:
        login = api(
            client,
            "POST",
            "/api/auth/login",
            payload={"username": args.username, "password": password},
        )
        if login.get("must_change_password"):
            fail("测试账号仍要求首次改密，请先在浏览器完成改密")
        csrf = str(login["csrf_token"])
        me = api(client, "GET", "/api/auth/me")
        chat = api(
            client,
            "POST",
            "/api/chats",
            csrf=csrf,
            payload={"title": "生产验收"},
        )
        chat_id = str(chat["id"])

        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict) or not str(step.get("message", "")).strip():
                fail(f"第 {index} 个步骤格式无效")
            name = str(step.get("name") or f"step-{index}")
            print(f"[{index}/{len(steps)}] 执行 {name}")
            before_files = api(client, "GET", "/api/files")
            before = {
                str(item.get("relative_path") or ""): int(
                    item.get("modified_ns") or 0
                )
                for item in before_files
            }
            result = api(
                client,
                "POST",
                f"/api/chats/{chat_id}/messages",
                csrf=csrf,
                payload={"content": str(step["message"])},
            )
            wait_for_job(client, str(result["job_id"]))
            files = api(client, "GET", "/api/files")
            assert_patterns(
                files,
                [str(item) for item in step.get("expect", [])],
                [str(item) for item in step.get("changed", [])],
                before,
            )
            print(f"通过：{name}")

        files = api(client, "GET", "/api/files")
        pdfs = [
            item["relative_path"]
            for item in files
            if str(item.get("relative_path", "")).lower().endswith(".pdf")
        ]
        if not pdfs:
            fail("流程完成但没有 PDF 产物")
        pdf = client.get(
            "/api/files/download",
            params={"path": pdfs[-1]},
        )
        pdf.raise_for_status()
        if not pdf.content.startswith(b"%PDF"):
            fail("下载的 PDF 产物没有有效 PDF 文件头")
        check_workspace(args.registry, str(me["id"]))
        api(client, "POST", "/api/auth/logout", csrf=csrf)
    print("真实 Web / Claude / DeepSeek 验收全部通过")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, httpx.HTTPError, OSError, json.JSONDecodeError) as exc:
        print(f"验收失败：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc
