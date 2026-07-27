from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.dialects.sqlite import insert

from .config import settings
from .db import session_scope
from .models import DailyUsage, Job, User
from .security import verify_proxy_token
from .time_utils import quota_day

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal/deepseek/anthropic", tags=["internal"])
ALLOWED_PATHS = {"v1/messages", "v1/messages/count_tokens", "v1/models"}
MAX_PROXY_BODY = 32 * 1024 * 1024


def _new_upstream_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=20.0))


def _bearer(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return request.headers.get("x-api-key", "")


def _usage_values(value: Any) -> tuple[int, int]:
    if not isinstance(value, dict):
        return 0, 0
    usage = value.get("usage")
    input_tokens = output_tokens = 0
    if isinstance(usage, dict):
        input_tokens = (
            int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
            + int(usage.get("cache_creation_input_tokens") or 0)
            + int(usage.get("cache_read_input_tokens") or 0)
        )
        output_tokens = int(
            usage.get("output_tokens") or usage.get("completion_tokens") or 0
        )
    for child in value.values():
        if isinstance(child, dict):
            child_in, child_out = _usage_values(child)
            input_tokens = max(input_tokens, child_in)
            output_tokens = max(output_tokens, child_out)
    return input_tokens, output_tokens


def _record_request(user_id: str) -> None:
    with session_scope() as db:
        db.execute(
            insert(DailyUsage)
            .values(
                user_id=user_id,
                day=quota_day(),
                jobs=0,
                api_requests=1,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
            )
            .on_conflict_do_update(
                index_elements=["user_id", "day"],
                set_={
                    "api_requests": DailyUsage.api_requests + 1,
                },
            )
        )


def _record_tokens(user_id: str, input_tokens: int, output_tokens: int) -> None:
    if input_tokens <= 0 and output_tokens <= 0:
        return
    with session_scope() as db:
        clean_input = max(0, input_tokens)
        clean_output = max(0, output_tokens)
        db.execute(
            insert(DailyUsage)
            .values(
                user_id=user_id,
                day=quota_day(),
                jobs=0,
                api_requests=0,
                input_tokens=clean_input,
                output_tokens=clean_output,
                total_tokens=clean_input + clean_output,
            )
            .on_conflict_do_update(
                index_elements=["user_id", "day"],
                set_={
                    "input_tokens": (
                        DailyUsage.input_tokens + clean_input
                    ),
                    "output_tokens": (
                        DailyUsage.output_tokens + clean_output
                    ),
                    "total_tokens": (
                        DailyUsage.total_tokens + clean_input + clean_output
                    ),
                },
            )
        )


def _authorize(request: Request) -> str:
    if request.client and request.client.host not in {
        "127.0.0.1",
        "::1",
        "localhost",
    }:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    payload = verify_proxy_token(_bearer(request))
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    user_id = str(payload["sub"])
    job_id = str(payload["job"])
    with session_scope() as db:
        user = db.get(User, user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        job = db.get(Job, job_id)
        if not job or job.user_id != user_id or job.state != "running":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="任务凭证已撤销",
            )
    return user_id


@router.api_route("/{api_path:path}", methods=["GET", "POST"])
async def proxy(api_path: str, request: Request):
    normalized = api_path.strip("/")
    if normalized not in ALLOWED_PATHS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if not settings.deepseek_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DeepSeek API key 未配置",
        )
    user_id = _authorize(request)
    body = await request.body()
    if len(body) > MAX_PROXY_BODY:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    if normalized in {"v1/messages", "v1/messages/count_tokens"}:
        try:
            body_json = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=400, detail="请求 JSON 无效") from exc
        received_model = body_json.get("model")
        allowed_models = {
            settings.primary_model,
            settings.light_model,
        }
        allowed_models.update(
            model.removesuffix("[1m]")
            for model in tuple(allowed_models)
            if model.endswith("[1m]")
        )
        if (
            not isinstance(received_model, str)
            or received_model not in allowed_models
        ):
            model_for_log = (
                received_model[:160]
                if isinstance(received_model, str)
                else type(received_model).__name__
            )
            logger.warning(
                "拒绝未允许模型：received=%r allowed=%s",
                model_for_log,
                sorted(allowed_models),
            )
            raise HTTPException(status_code=400, detail="模型不在固定允许清单")

    upstream = f"{settings.deepseek_base_url}/{normalized}"
    if request.url.query:
        upstream += "?" + request.url.query
    headers = {
        "content-type": request.headers.get("content-type", "application/json"),
        "accept": request.headers.get("accept", "application/json"),
        "x-api-key": settings.deepseek_api_key,
        "authorization": f"Bearer {settings.deepseek_api_key}",
        "anthropic-version": request.headers.get(
            "anthropic-version", "2023-06-01"
        ),
    }
    beta = request.headers.get("anthropic-beta")
    if beta:
        headers["anthropic-beta"] = beta

    client = _new_upstream_client()
    upstream_request = client.build_request(
        request.method, upstream, headers=headers, content=body
    )
    try:
        upstream_response = await client.send(upstream_request, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="无法连接 DeepSeek",
        ) from exc
    _record_request(user_id)

    response_headers = {}
    for name in ("content-type", "request-id", "x-request-id", "retry-after"):
        if value := upstream_response.headers.get(name):
            response_headers[name] = value

    content_type = upstream_response.headers.get("content-type", "")
    if "text/event-stream" not in content_type:
        content = await upstream_response.aread()
        await upstream_response.aclose()
        await client.aclose()
        try:
            input_tokens, output_tokens = _usage_values(json.loads(content))
            _record_tokens(user_id, input_tokens, output_tokens)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        return Response(
            content=content,
            status_code=upstream_response.status_code,
            headers=response_headers,
        )

    async def stream() -> AsyncIterator[bytes]:
        buffer = b""
        max_input = max_output = 0
        try:
            async for chunk in upstream_response.aiter_bytes():
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if line.startswith(b"data:"):
                        raw = line[5:].strip()
                        if raw and raw != b"[DONE]":
                            try:
                                input_tokens, output_tokens = _usage_values(
                                    json.loads(raw)
                                )
                                max_input = max(max_input, input_tokens)
                                max_output = max(max_output, output_tokens)
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                pass
                    yield line + b"\n"
            if buffer:
                yield buffer
        finally:
            _record_tokens(user_id, max_input, max_output)
            await upstream_response.aclose()
            await client.aclose()

    return StreamingResponse(
        stream(),
        status_code=upstream_response.status_code,
        headers=response_headers,
        media_type="text/event-stream",
    )
