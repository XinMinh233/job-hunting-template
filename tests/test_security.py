from __future__ import annotations

import uuid

from webapp.security import (
    mint_proxy_token,
    password_hash,
    verify_password,
    verify_proxy_token,
)


def test_argon2_password_round_trip():
    encoded = password_hash("correct horse battery staple")
    assert encoded.startswith("$argon2id$")
    assert verify_password(encoded, "correct horse battery staple")
    assert not verify_password(encoded, "wrong password")


def test_password_minimum_length():
    try:
        password_hash("too-short")
    except ValueError as exc:
        assert "12" in str(exc)
    else:
        raise AssertionError("短密码不应被接受")


def test_proxy_token_is_signed_and_scoped():
    user_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    token = mint_proxy_token(user_id, job_id)
    payload = verify_proxy_token(token)
    assert payload and payload["sub"] == user_id
    assert payload["job"] == job_id
    body, signature = token.split(".", 1)
    assert verify_proxy_token(body + "." + signature[:-1] + "x") is None
