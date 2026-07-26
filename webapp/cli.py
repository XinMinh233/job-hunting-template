from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from .config import settings
from .db import init_db, session_scope
from .models import User
from .runner_client import RunnerError, runner_client
from .security import USERNAME_RE, password_hash


def _bootstrap_admin(args: argparse.Namespace) -> int:
    username = args.username.strip().lower()
    if not USERNAME_RE.fullmatch(username):
        print("用户名格式不正确", file=sys.stderr)
        return 2
    password = os.getenv(args.password_env) if args.password_env else None
    if not password:
        password = getpass.getpass("管理员密码（至少 12 个字符）: ")
        confirmation = getpass.getpass("再次输入密码: ")
        if password != confirmation:
            print("两次密码不一致", file=sys.stderr)
            return 2
    try:
        hashed = password_hash(password)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    init_db()
    created = False
    try:
        with session_scope() as db:
            existing = db.scalar(select(User).where(User.username == username))
            if existing:
                if existing.role != "admin":
                    print("同名普通用户已存在，拒绝覆盖", file=sys.stderr)
                    return 3
                admin = existing
                admin.password_hash = hashed
                admin.is_active = True
                admin.must_change_password = False
            else:
                admin = User(
                    username=username,
                    password_hash=hashed,
                    role="admin",
                    is_active=True,
                    must_change_password=False,
                    daily_job_limit=settings.default_daily_jobs,
                    daily_token_limit=settings.default_daily_tokens,
                )
                db.add(admin)
                db.flush()
                created = True
            if not admin.linux_username or not admin.workspace_path:
                provisioned = asyncio.run(
                    runner_client.request("provision", user_id=admin.id)
                )
                admin.linux_username = provisioned["linux_username"]
                admin.workspace_path = provisioned["workspace_path"]
                admin.template_version = provisioned["template_version"]
    except RunnerError as exc:
        print(f"管理员工作空间创建失败：{exc}", file=sys.stderr)
        return 4
    if created:
        print(f"已创建管理员 {username} 及其隔离工作空间")
    else:
        print(f"已更新管理员 {username} 的密码和工作空间状态")
    return 0


def _check_config(_args: argparse.Namespace) -> int:
    problems = []
    if settings.is_development_secret:
        problems.append("JOBHUNT_SECRET_KEY 仍为临时开发值")
    if not settings.deepseek_api_key:
        problems.append("DEEPSEEK_API_KEY 未配置")
    if not settings.public_base_url.startswith("https://"):
        problems.append("JOBHUNT_PUBLIC_BASE_URL 不是 HTTPS")
    if not settings.claude_version:
        problems.append("JOBHUNT_CLAUDE_VERSION 未固定")
    if settings.effort_level not in {"low", "medium", "high", "max"}:
        problems.append("JOBHUNT_EFFORT_LEVEL 无效")
    try:
        ZoneInfo(settings.quota_timezone)
    except ZoneInfoNotFoundError:
        problems.append("JOBHUNT_QUOTA_TIMEZONE 无效")
    if problems:
        for problem in problems:
            print(f"失败：{problem}")
        return 1
    print("核心生产配置检查通过")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="求职系统管理工具")
    subparsers = parser.add_subparsers(dest="command", required=True)
    bootstrap = subparsers.add_parser("bootstrap-admin", help="创建或更新超级管理员")
    bootstrap.add_argument("--username", default="admin")
    bootstrap.add_argument(
        "--password-env",
        help="从指定环境变量读取密码；未指定时安全交互输入",
    )
    bootstrap.set_defaults(handler=_bootstrap_admin)
    check = subparsers.add_parser("check-config", help="检查生产环境配置")
    check.set_defaults(handler=_check_config)
    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
