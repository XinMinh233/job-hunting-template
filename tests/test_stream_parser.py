from __future__ import annotations

import json

from webapp.stream_parser import (
    ClaudeStreamParser,
    counts_assistant_turn,
    parse_stream_line,
)


def line(value: dict) -> str:
    return json.dumps(value)


def test_thinking_is_never_emitted():
    parsed = parse_stream_line(
        line(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "thinking", "thinking": "secret reasoning"},
                        {"type": "text", "text": "可见答案"},
                    ]
                },
            }
        )
    )
    assert parsed.events == [("text_delta", {"text": "可见答案"})]
    assert "secret reasoning" not in repr(parsed)


def test_partial_text_is_not_repeated_by_final_assistant_message():
    parser = ClaudeStreamParser()
    partial = parser.feed(
        line(
            {
                "type": "stream_event",
                "event": {
                    "type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": "你好"},
                },
            }
        )
    )
    final = parser.feed(
        line(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "你好"}]},
            }
        )
    )
    assert partial.events == [("text_delta", {"text": "你好"})]
    assert final.events == []


def test_tool_event_is_sanitized():
    parsed = parse_stream_line(
        line(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {"command": "cat /etc/shadow"},
                        }
                    ]
                },
            }
        )
    )
    assert parsed.events[0][0] == "tool"
    assert "command" not in parsed.events[0][1]
    assert "shadow" not in repr(parsed.events)


def test_only_assistant_records_count_toward_turn_limit():
    assert counts_assistant_turn(line({"type": "assistant", "message": {}}))
    assert not counts_assistant_turn(line({"type": "stream_event", "event": {}}))
    assert not counts_assistant_turn("not json")
