"""Text utilities."""

from __future__ import annotations

import re

_WHITESPACE = re.compile(r"[ \t]+")
_MULTILINE_BLANK = re.compile(r"\n{3,}")
_SPACE_AROUND_NEWLINE = re.compile(r"[ \t]*\n[ \t]*")


def normalize_whitespace(text: str) -> str:
    """Collapse runs of spaces/tabs, normalize newlines, strip edges."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WHITESPACE.sub(" ", text)
    text = _SPACE_AROUND_NEWLINE.sub("\n", text)
    text = _MULTILINE_BLANK.sub("\n\n", text)
    return text.strip()


def word_count(text: str) -> int:
    if not text or not text.strip():
        return 0
    return len(text.split())
