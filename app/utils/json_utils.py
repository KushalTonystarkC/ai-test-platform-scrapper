"""JSON helpers for LLM outputs."""

from __future__ import annotations

import json
import re
from typing import Any


def safe_parse_json(raw: str) -> dict[str, Any]:
    """Parse a JSON object from model output (fences / trailing junk / truncation).

    Small local models often append prose after a valid object ("Extra data").
    ``raw_decode`` accepts the first complete value and ignores the rest.
    """
    text = raw.strip()
    if not text:
        raise json.JSONDecodeError("Empty LLM response", text, 0)

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

    # Prefer first object starting at each `{` (handles leading prose)
    starts = [0]
    pos = text.find("{")
    if pos > 0:
        starts.append(pos)
    elif pos == 0 and 0 not in starts:
        starts.append(0)

    decoder = json.JSONDecoder()
    last_error: Exception | None = None
    seen: set[str] = set()

    for start in starts:
        fragment = text[start:].lstrip()
        if not fragment or fragment in seen:
            continue
        seen.add(fragment)
        try:
            data, _end = decoder.raw_decode(fragment)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError as exc:
            last_error = exc
            repaired = _repair_truncated_object(fragment)
            if repaired is not None:
                return repaired

    # Last resort: slice first `{` … last `}`
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        sliced = text[start : end + 1]
        if sliced not in seen:
            try:
                data = json.loads(sliced)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError as exc:
                last_error = exc
                repaired = _repair_truncated_object(sliced)
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
