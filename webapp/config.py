from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


@dataclass(frozen=True)
class Settings:
    app_name: str
    secret_key: str
    database_url: str
    cookie_secure: bool
    session_days: int
    runner_socket: Path
    runner_registry: Path
    users_root: Path
    staging_root: Path
    template_root: Path
    public_base_url: str
    deepseek_base_url: str
    deepseek_api_key: str
    proxy_base_url: str
    primary_model: str
    light_model: str
    effort_level: str
    global_concurrency: int
    default_daily_jobs: int
    default_daily_tokens: int
    quota_timezone: str
    max_upload_bytes: int
    max_user_storage_bytes: int
    claude_bin: str
    claude_version: str
    development_runner: bool
    development_root: Path

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(__file__).resolve().parent.parent
        runtime = Path(os.getenv("JOBHUNT_RUNTIME_ROOT", root / ".runtime"))
        secret = os.getenv("JOBHUNT_SECRET_KEY", "")
        if not secret:
            # 仅便于本地开发；生产健康检查会拒绝这一默认值。
            secret = "dev-" + secrets.token_urlsafe(32)
        return cls(
            app_name="求职工作台",
            secret_key=secret,
            database_url=os.getenv(
                "JOBHUNT_DATABASE_URL",
                f"sqlite:///{runtime / 'jobhunt.sqlite3'}",
            ),
            cookie_secure=_bool("JOBHUNT_COOKIE_SECURE", True),
            session_days=_int("JOBHUNT_SESSION_DAYS", 7),
            runner_socket=Path(
                os.getenv("JOBHUNT_RUNNER_SOCKET", "/run/jobhunt/runner.sock")
            ),
            runner_registry=Path(
                os.getenv(
                    "JOBHUNT_RUNNER_REGISTRY",
                    "/var/lib/jobhunt-runner/registry.json",
                )
            ),
            users_root=Path(
                os.getenv("JOBHUNT_USERS_ROOT", "/var/lib/jobhunt/users")
            ),
            staging_root=Path(
                os.getenv("JOBHUNT_STAGING_ROOT", "/var/lib/jobhunt-staging")
            ),
            template_root=Path(os.getenv("JOBHUNT_TEMPLATE_ROOT", root)),
            public_base_url=os.getenv(
                "JOBHUNT_PUBLIC_BASE_URL", "https://jobs.example.com"
            ).rstrip("/"),
            deepseek_base_url=os.getenv(
                "DEEPSEEK_ANTHROPIC_BASE_URL",
                "https://api.deepseek.com/anthropic",
            ).rstrip("/"),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            proxy_base_url=os.getenv(
                "JOBHUNT_PROXY_BASE_URL",
                "http://127.0.0.1:8000/internal/deepseek/anthropic",
            ).rstrip("/"),
            primary_model=os.getenv(
                "JOBHUNT_PRIMARY_MODEL", "deepseek-v4-pro[1m]"
            ),
            light_model=os.getenv("JOBHUNT_LIGHT_MODEL", "deepseek-v4-flash"),
            effort_level=os.getenv("JOBHUNT_EFFORT_LEVEL", "max").strip(),
            global_concurrency=_int("JOBHUNT_GLOBAL_CONCURRENCY", 3),
            default_daily_jobs=_int("JOBHUNT_DEFAULT_DAILY_JOBS", 30),
            default_daily_tokens=_int("JOBHUNT_DEFAULT_DAILY_TOKENS", 1_000_000),
            quota_timezone=os.getenv(
                "JOBHUNT_QUOTA_TIMEZONE",
                "Asia/Shanghai",
            ),
            max_upload_bytes=_int("JOBHUNT_MAX_UPLOAD_BYTES", 10 * 1024 * 1024),
            max_user_storage_bytes=_int(
                "JOBHUNT_MAX_USER_STORAGE_BYTES", 100 * 1024 * 1024
            ),
            claude_bin=os.getenv("JOBHUNT_CLAUDE_BIN", "claude"),
            claude_version=os.getenv("JOBHUNT_CLAUDE_VERSION", "").strip(),
            development_runner=_bool("JOBHUNT_DEVELOPMENT_RUNNER", False),
            development_root=Path(
                os.getenv("JOBHUNT_DEVELOPMENT_ROOT", runtime / "users")
            ),
        )

    @property
    def is_development_secret(self) -> bool:
        return self.secret_key.startswith("dev-")


settings = Settings.from_env()
