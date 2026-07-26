from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import re
import secrets
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from .config import settings

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
USERNAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{2,31}$")
SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{8,128}$")
USER_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def password_hash(password: str) -> str:
    if len(password) < 12:
        raise ValueError("密码至少需要 12 个字符")
    return _hasher.hash(password)


def verify_password(encoded: str, password: str) -> bool:
    try:
        return _hasher.verify(encoded, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def generate_password() -> str:
    return secrets.token_urlsafe(18)


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def identity_hash(username: str, ip: str) -> str:
    normalized = f"{username.strip().lower()}|{ip}"
    return hmac.new(
        settings.secret_key.encode(), normalized.encode(), hashlib.sha256
    ).hexdigest()


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def mint_proxy_token(
    user_id: str,
    job_id: str,
    ttl_seconds: int = 3600,
) -> str:
    payload = {
        "sub": user_id,
        "job": job_id,
        "exp": int(dt.datetime.now(dt.timezone.utc).timestamp()) + ttl_seconds,
        "nonce": secrets.token_hex(8),
    }
    body = _b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    )
    signature = hmac.new(
        settings.secret_key.encode(), body.encode(), hashlib.sha256
    ).digest()
    return f"{body}.{_b64encode(signature)}"


def verify_proxy_token(token: str) -> dict[str, Any] | None:
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(
            settings.secret_key.encode(), body.encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, _b64decode(signature)):
            return None
        payload = json.loads(_b64decode(body))
        if int(payload["exp"]) <= int(
            dt.datetime.now(dt.timezone.utc).timestamp()
        ):
            return None
        if not USER_ID_RE.fullmatch(str(payload["sub"])):
            return None
        if not USER_ID_RE.fullmatch(str(payload["job"])):
            return None
        return payload
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
