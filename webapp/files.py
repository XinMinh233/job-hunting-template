from __future__ import annotations

import asyncio
import mimetypes
import os
import sys
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .audit import audit
from .config import settings
from .dependencies import (
    Principal,
    get_db,
    get_ready_principal,
    require_ready_csrf,
)
from .jobs import user_job_locks
from .models import FileRecord, Job
from .runner_client import RunnerError, runner_client
from .runner_protocol import safe_filename, safe_relative_path

router = APIRouter(prefix="/api/files", tags=["files"])
ALLOWED_SUFFIXES = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".pdf", ".docx"}
MARKDOWN_SUFFIXES = {".md", ".markdown"}
MAX_MARKDOWN_PREVIEW_BYTES = 2 * 1024 * 1024


async def _save_staging(
    upload: UploadFile, user_id: str, suffix: str
) -> tuple[str, Path, int]:
    user_staging = settings.staging_root / user_id
    user_staging.mkdir(parents=True, exist_ok=True)
    staging_name = uuid.uuid4().hex + suffix
    path = user_staging / staging_name
    total = 0
    try:
        with path.open("xb") as handle:
            while chunk := await upload.read(64 * 1024):
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="文件超过 10 MB")
                handle.write(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return staging_name, path, total


async def _extract_in_subprocess(
    source: Path,
    suffix: str,
    output: Path,
) -> None:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "webapp.file_extract",
        str(source),
        suffix,
        str(output),
        env={"LANG": "C.UTF-8", "PATH": os.defpath},
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=30,
        )
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        raise ValueError("文件文本提取超过 30 秒，已停止") from exc
    if process.returncode != 0:
        message = stderr.decode(errors="replace").strip().splitlines()
        detail = "文件格式无效或无法安全提取文本"
        if message and any(
            marker in message[-1]
            for marker in (
                "PDF 页数超过",
                "DOCX 内部文件数量异常",
                "DOCX 解压后体积过大",
                "DOCX 压缩比例异常",
            )
        ):
            detail = message[-1].split(":", 1)[-1].strip()[:300]
        raise ValueError(detail)


@router.get("")
async def list_files(principal: Principal = Depends(get_ready_principal)):
    try:
        result = await runner_client.request(
            "file_list", user_id=principal.user.id
        )
    except RunnerError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return result["files"]


@router.post("/upload")
async def upload_file(
    upload: UploadFile = File(...),
    principal: Principal = Depends(require_ready_csrf),
    db: Session = Depends(get_db),
):
    async with user_job_locks[principal.user.id]:
        active_job = db.scalar(
            select(Job.id).where(
                Job.user_id == principal.user.id,
                Job.state.in_(("queued", "running")),
            )
        )
        if active_job:
            raise HTTPException(
                status_code=409,
                detail="请等待当前任务结束后再上传文件",
            )
        return await _upload_file_impl(upload, principal, db)


async def _upload_file_impl(
    upload: UploadFile,
    principal: Principal,
    db: Session,
):
    filename = safe_filename(upload.filename or "upload")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail="仅支持 TXT、Markdown、CSV、JSON、YAML、PDF 和 DOCX",
        )
    used = db.scalar(
        select(func.coalesce(func.sum(FileRecord.size_bytes), 0)).where(
            FileRecord.user_id == principal.user.id
        )
    )
    if (used or 0) >= settings.max_user_storage_bytes:
        raise HTTPException(status_code=413, detail="个人上传空间已满")

    staging_name, staging_path, size = await _save_staging(
        upload, principal.user.id, suffix
    )
    if (used or 0) + size > settings.max_user_storage_bytes:
        staging_path.unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail="上传后将超过个人空间限制")

    extracted_name = None
    extracted_staging = None
    try:
        if suffix in {".pdf", ".docx"}:
            extracted_name = uuid.uuid4().hex + ".txt"
            extracted_staging = (
                settings.staging_root / principal.user.id / extracted_name
            )
            await _extract_in_subprocess(
                staging_path,
                suffix,
                extracted_staging,
            )
            extracted_size = extracted_staging.stat().st_size
            if (
                (used or 0) + size + extracted_size
                > settings.max_user_storage_bytes
            ):
                raise ValueError("原文件与提取文本将超过个人空间限制")
        else:
            extracted_size = 0
        upload_id = str(uuid.uuid4())
        original = await runner_client.request(
            "file_import",
            user_id=principal.user.id,
            staging_name=staging_name,
            upload_id=upload_id,
            filename=filename,
            extracted_staging_name=extracted_name,
            extracted_filename=(
                filename + ".extracted.txt" if extracted_name else None
            ),
        )
        extracted_path = original.get("extracted_relative_path")
    except (RunnerError, ValueError) as exc:
        staging_path.unlink(missing_ok=True)
        if extracted_staging:
            extracted_staging.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record = FileRecord(
        id=upload_id,
        user_id=principal.user.id,
        relative_path=original["relative_path"],
        original_name=filename,
        mime_type=upload.content_type
        or mimetypes.guess_type(filename)[0]
        or "application/octet-stream",
        size_bytes=size + extracted_size,
        extracted_path=extracted_path,
    )
    db.add(record)
    audit(
        db,
        "file.uploaded",
        actor_user_id=principal.user.id,
        target=record.id,
        detail={"path": record.relative_path},
    )
    db.commit()
    return {
        "id": record.id,
        "relative_path": record.relative_path,
        "extracted_path": record.extracted_path,
        "message": (
            "文件已保存。可在对话中让 Claude 读取 "
            f"`{record.extracted_path or record.relative_path}`。"
        ),
    }


@router.get("/download")
async def download_file(
    path: str = Query(..., max_length=500),
    inline: bool = Query(False),
    principal: Principal = Depends(get_ready_principal),
):
    try:
        relative = safe_relative_path(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filename = Path(relative).name
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    headers = {
        "Content-Disposition": (
            (
                "inline"
                if inline and mime in {"application/pdf", "text/html"}
                else "attachment"
            )
            + "; "
            f"filename*=UTF-8''{quote(filename)}"
        ),
        "X-Content-Type-Options": "nosniff",
    }
    if mime == "text/html":
        headers["Content-Security-Policy"] = (
            "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:"
        )
    metadata = await _owned_file_metadata(principal, relative)
    mime = metadata.get("mime_type") or mime
    stream = runner_client.read_file(principal.user.id, relative)
    return StreamingResponse(stream, media_type=mime, headers=headers)


async def _owned_file_metadata(
    principal: Principal,
    relative: str,
) -> dict:
    try:
        listed = await runner_client.request(
            "file_list", user_id=principal.user.id
        )
    except RunnerError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    metadata = next(
        (
            item
            for item in listed.get("files", [])
            if item.get("relative_path") == relative
        ),
        None,
    )
    if not metadata:
        raise HTTPException(status_code=404, detail="文件不存在")
    return metadata


@router.get("/preview")
async def preview_markdown_file(
    path: str = Query(..., max_length=500),
    principal: Principal = Depends(get_ready_principal),
):
    try:
        relative = safe_relative_path(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if Path(relative).suffix.lower() not in MARKDOWN_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail="该文件类型不支持在线预览",
        )

    metadata = await _owned_file_metadata(principal, relative)
    if int(metadata.get("size") or 0) > MAX_MARKDOWN_PREVIEW_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Markdown 文件超过 2 MB，请下载后查看",
        )

    chunks = bytearray()
    try:
        async for chunk in runner_client.read_file(
            principal.user.id,
            relative,
        ):
            chunks.extend(chunk)
            if len(chunks) > MAX_MARKDOWN_PREVIEW_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="Markdown 文件超过 2 MB，请下载后查看",
                )
    except RunnerError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        content = chunks.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=422,
            detail="Markdown 文件不是有效的 UTF-8 文本",
        ) from exc
    return JSONResponse(
        {"relative_path": relative, "content": content},
        headers={"Cache-Control": "no-store"},
    )
