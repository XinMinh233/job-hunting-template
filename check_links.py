#!/usr/bin/env python3
"""检查 Markdown 中的公网 HTTP(S) 链接，不允许访问本机或私网。"""

from __future__ import annotations

import argparse
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

URL_RE = re.compile(r"https?://[^\s<>()\]]+")
MAX_FILES = 20
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_LINKS = 100


def validate_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.rstrip(".,;:"))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("仅允许完整的 HTTP(S) 链接")
    if parsed.username or parsed.password:
        raise ValueError("链接不能包含认证信息")
    try:
        addresses = socket.getaddrinfo(
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ValueError("域名无法解析") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0].split("%", 1)[0])
        if not ip.is_global:
            raise ValueError("拒绝访问本机、私网或链路本地地址")
    return urllib.parse.urlunsplit(parsed)


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(
            req,
            fp,
            code,
            msg,
            headers,
            validate_url(newurl),
        )


def safe_file(value: str, root: Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        raise ValueError("文件必须位于当前工作区")
    current = root
    for part in candidate.parts:
        current /= part
        if current.is_symlink():
            raise ValueError("文件不存在或是符号链接")
    target = (root / candidate).resolve()
    if root != target and root not in target.parents:
        raise ValueError("文件路径越界")
    if not target.is_file():
        raise ValueError("文件不存在或是符号链接")
    if target.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("单个待检查文件超过 5 MB")
    return target


def status_for(opener: urllib.request.OpenerDirector, url: str) -> int:
    request = urllib.request.Request(
        validate_url(url),
        method="HEAD",
        headers={"User-Agent": "jobhunt-link-check/1"},
    )
    try:
        with opener.open(request, timeout=10) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        if exc.code not in {405, 501}:
            return int(exc.code)
    request = urllib.request.Request(
        validate_url(url),
        method="GET",
        headers={
            "User-Agent": "jobhunt-link-check/1",
            "Range": "bytes=0-0",
        },
    )
    try:
        with opener.open(request, timeout=10) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    if len(args.files) > MAX_FILES:
        parser.error(f"一次最多检查 {MAX_FILES} 个文件")

    root = Path.cwd().resolve()
    links: set[str] = set()
    try:
        for value in args.files:
            text = safe_file(value, root).read_text(
                encoding="utf-8",
                errors="replace",
            )
            links.update(match.rstrip(".,;:") for match in URL_RE.findall(text))
    except ValueError as exc:
        parser.error(str(exc))
    if len(links) > MAX_LINKS:
        parser.error(f"链接超过 {MAX_LINKS} 条")

    opener = urllib.request.build_opener(SafeRedirectHandler())
    failed = False
    for url in sorted(links):
        try:
            code = status_for(opener, url)
            print(f"{code}  {url}")
            hostname = str(urllib.parse.urlsplit(url).hostname)
            if code != 200 and not (
                code == 999
                and (
                    hostname == "linkedin.com"
                    or hostname.endswith(".linkedin.com")
                )
            ):
                failed = True
        except (OSError, ValueError, urllib.error.URLError) as exc:
            failed = True
            print(f"ERROR  {url}  {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
