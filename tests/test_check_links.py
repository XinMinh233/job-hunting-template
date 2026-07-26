from __future__ import annotations

import socket
from pathlib import Path

import pytest

import check_links


def address(value: str):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (value, 443))]


def test_link_checker_rejects_private_network(monkeypatch):
    monkeypatch.setattr(
        check_links.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: address("127.0.0.1"),
    )
    with pytest.raises(ValueError, match="私网"):
        check_links.validate_url("http://localhost/internal")


def test_link_checker_accepts_public_https(monkeypatch):
    monkeypatch.setattr(
        check_links.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: address("93.184.216.34"),
    )
    assert (
        check_links.validate_url("https://example.com/resume")
        == "https://example.com/resume"
    )


def test_link_checker_rejects_path_traversal_and_symlink(tmp_path: Path):
    outside = tmp_path.parent / "outside-resume.md"
    outside.write_text("secret", encoding="utf-8")
    with pytest.raises(ValueError, match="越界"):
        check_links.safe_file("../outside-resume.md", tmp_path)
    link = tmp_path / "resume.md"
    link.symlink_to(outside)
    with pytest.raises(ValueError, match="符号链接"):
        check_links.safe_file("resume.md", tmp_path)
