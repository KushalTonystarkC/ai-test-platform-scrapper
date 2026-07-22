"""JSON helpers for LLM outputs."""

from __future__ import annotations

import json
import re
from typing import Any


def safe_parse_json(raw: str) -> dict[str, Any]:
    """Parse a JSON object from model output (fences / trailing junk / truncation).

    Small local models often append prose after a valid object ("Extra data"),
    hit max-token cutoffs mid-key/value, or emit raw newlines inside strings.
    """
    text = raw.strip()
    if not text:
        raise json.JSONDecodeError("Empty LLM response", text, 0)

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

    text = _escape_control_chars_in_strings(text)

    starts = [0]
    pos = text.find("{")
    if pos > 0:
        starts.append(pos)

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


def _escape_control_chars_in_strings(text: str) -> str:
    """Escape raw control characters inside JSON string literals (common LLM bug)."""
    out: list[str] = []
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                continue
            if ch == '"':
                in_string = False
                out.append(ch)
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                out.append("\\r")
                continue
            if ch == "\t":
                out.append("\\t")
                continue
            if ord(ch) < 0x20:
                out.append(f"\\u{ord(ch):04x}")
                continue
            out.append(ch)
            continue
        if ch == '"':
            in_string = True
        out.append(ch)
    return "".join(out)


def _repair_truncated_object(text: str) -> dict[str, Any] | None:
    """Best-effort close of truncated JSON objects from max-token cutoffs."""
    text = text.strip()
    if not text.startswith("{"):
        return None

    # Drop incomplete trailing key / key:value fragments, then close structures
    candidates = [
        text,
        _strip_incomplete_tail(text),
        _strip_incomplete_tail(_close_open_string(text)),
    ]

    for candidate in candidates:
        closed = _close_containers(_strip_trailing_comma(_close_open_string(candidate)))
        try:
            data = json.loads(closed)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue

    # Progressive cutback to last structural boundary
    for i in range(len(text) - 1, 0, -1):
        if text[i] not in ",}]":
            continue
        prefix = text[: i + 1] if text[i] in "}]" else text[:i]
        prefix = _strip_trailing_comma(prefix)
        closed = _close_containers(_close_open_string(prefix))
        try:
            data = json.loads(closed)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    return None


def _close_open_string(text: str) -> str:
    in_string = False
    escape = False
    for ch in text:
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
    return text + '"' if in_string else text


def _close_containers(text: str) -> str:
    in_string = False
    escape = False
    stack: list[str] = []
    for ch in text:
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
    return text + "".join(reversed(stack))


def _strip_trailing_comma(text: str) -> str:
    return re.sub(r",\s*$", "", text.rstrip())


def _strip_incomplete_tail(text: str) -> str:
    """Remove truncated keys/values like `, \"diffic` or `, \"k\": \"val`."""
    cleaned = text.rstrip()
    # Incomplete key only: ,"diffic
    cleaned = re.sub(r',\s*"[^"]*$', "", cleaned)
    # Key with colon but missing/incomplete value: ,"k": or ,"k": "par
    cleaned = re.sub(r',\s*"[^"]*"\s*:\s*("[^"]*)?$', "", cleaned)
    # Same without leading comma (first field truncated — rare)
    cleaned = re.sub(r'\{\s*"[^"]*$', "{", cleaned)
    cleaned = re.sub(r'\{\s*"[^"]*"\s*:\s*("[^"]*)?$', "{", cleaned)
    return _strip_trailing_comma(cleaned)
