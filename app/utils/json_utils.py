"""JSON helpers for LLM outputs."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def safe_parse_json(raw: str) -> dict[str, Any]:
    """Parse a JSON object from model output (fences / trailing junk / truncation)."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

    candidates = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start : end + 1])
    if start != -1:
        candidates.append(text[start:])

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError as exc:
            last_error = exc
            repaired = _repair_truncated_object(candidate)
            if repaired is not None:
                return repaired

    raise json.JSONDecodeError(
        f"Could not parse JSON object: {last_error}",
        text,
        0,
    )


def _repair_truncated_object(text: str) -> dict[str, Any] | None:
    """Best-effort close of truncated JSON objects from max-token cutoffs."""
    text = text.strip()
    if not text.startswith("{"):
        return None

    in_string = False
    escape = False
    stack: list[str] = ["}"]
    # Skip the opening brace already accounted for in stack
    for ch in text[1:]:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]":
            if stack and ch == stack[-1]:
                stack.pop()

    repaired = text
    if in_string:
        repaired += '"'
    repaired = re.sub(r",\s*$", "", repaired)
    while stack:
        repaired += stack.pop()

    try:
        data = json.loads(repaired)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None
