from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedLine:
    session_id: str | None = None
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    done: bool = False
    failed: bool = False
    error: str | None = None


def _tool_label(name: str) -> str:
    labels = {
        "Read": "读取文件",
        "Write": "写入文件",
        "Edit": "编辑文件",
        "Bash": "执行项目命令",
        "WebSearch": "搜索职位信息",
        "WebFetch": "读取网页",
        "Task": "运行子任务",
    }
    return labels.get(name, "使用工具")


def counts_assistant_turn(line: str) -> bool:
    try:
        return json.loads(line).get("type") == "assistant"
    except (json.JSONDecodeError, AttributeError):
        return False


def _assistant_blocks(message: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    output: list[tuple[str, dict[str, Any]]] = []
    for block in message.get("content") or []:
        kind = block.get("type")
        if kind == "text" and block.get("text"):
            output.append(("text_delta", {"text": str(block["text"])}))
        elif kind == "tool_use":
            name = str(block.get("name") or "tool")
            output.append(
                (
                    "tool",
                    {
                        "name": name,
                        "label": _tool_label(name),
                        "status": "running",
                    },
                )
            )
        # thinking / redacted_thinking 永不发送到浏览器。
    return output


def parse_stream_line(line: str) -> ParsedLine:
    parsed = ParsedLine()
    try:
        item = json.loads(line)
    except json.JSONDecodeError:
        if line.strip():
            parsed.events.append(("status", {"message": "Claude 正在处理"}))
        return parsed

    item_type = item.get("type")
    if isinstance(item.get("session_id"), str):
        parsed.session_id = item["session_id"]

    if item_type == "system":
        if item.get("subtype") == "init":
            parsed.events.append(("status", {"message": "会话已启动"}))
        return parsed

    if item_type == "assistant":
        parsed.events.extend(_assistant_blocks(item.get("message") or {}))
        return parsed

    if item_type == "stream_event":
        event = item.get("event") or {}
        event_type = event.get("type")
        if event_type == "content_block_delta":
            delta = event.get("delta") or {}
            if delta.get("type") == "text_delta" and delta.get("text"):
                parsed.events.append(
                    ("text_delta", {"text": str(delta["text"])})
                )
        elif event_type == "content_block_start":
            block = event.get("content_block") or {}
            if block.get("type") == "tool_use":
                name = str(block.get("name") or "tool")
                parsed.events.append(
                    (
                        "tool",
                        {
                            "name": name,
                            "label": _tool_label(name),
                            "status": "running",
                        },
                    )
                )
        return parsed

    if item_type == "result":
        parsed.done = not bool(item.get("is_error"))
        parsed.failed = bool(item.get("is_error"))
        if parsed.failed:
            parsed.error = str(
                item.get("result") or item.get("error") or "Claude 执行失败"
            )
        return parsed

    return parsed


class ClaudeStreamParser:
    """Stateful parser that avoids repeating final assistant blocks after deltas."""

    def __init__(self) -> None:
        self._saw_partial_text = False

    def feed(self, line: str) -> ParsedLine:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            return parse_stream_line(line)
        if item.get("type") == "stream_event":
            event = item.get("event") or {}
            delta = event.get("delta") or {}
            if (
                event.get("type") == "content_block_delta"
                and delta.get("type") == "text_delta"
            ):
                self._saw_partial_text = True
            return parse_stream_line(line)
        if item.get("type") == "assistant" and self._saw_partial_text:
            parsed = ParsedLine(
                session_id=item.get("session_id")
                if isinstance(item.get("session_id"), str)
                else None
            )
            for event_type, data in _assistant_blocks(item.get("message") or {}):
                if event_type != "text_delta":
                    parsed.events.append((event_type, data))
            self._saw_partial_text = False
            return parsed
        return parse_stream_line(line)
