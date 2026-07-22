"""Tests for JSON parsing helpers used on messy LLM outputs."""

from __future__ import annotations

import pytest

from app.utils.json_utils import safe_parse_json


def test_safe_parse_clean_object() -> None:
    assert safe_parse_json('{"a": 1, "b": ["x"]}') == {"a": 1, "b": ["x"]}


def test_safe_parse_trailing_prose() -> None:
    raw = (
        '{"subject":"Banking","summary":"RBI regulates banks.","difficultyHint":"easy"}'
        "\n\nHere is an explanation of the fields above."
    )
    data = safe_parse_json(raw)
    assert data["subject"] == "Banking"
    assert data["difficultyHint"] == "easy"


def test_safe_parse_extra_json_after_object() -> None:
    # Matches the llama3.2:1b failure mode (Extra data at ~column 290)
    raw = (
        '{"subject":"Banking Awareness","chapter":"","topic":"RBI",'
        '"subtopics":["monetary policy"],"keywords":["RBI","banks"],'
        '"concepts":["regulation"],"learningObjectives":[],'
        '"summary":"RBI regulates banks and monetary policy in India.",'
        '"difficultyHint":"easy","sourceType":"BOOK"}'
        ' {"note":"ignore me"}'
    )
    data = safe_parse_json(raw)
    assert data["sourceType"] == "BOOK"
    assert "note" not in data


def test_safe_parse_fenced_and_leading_prose() -> None:
    raw = 'Sure!\n```json\n{"summary": "ok", "keywords": []}\n```\nDone.'
    assert safe_parse_json(raw)["summary"] == "ok"


def test_safe_parse_empty_raises() -> None:
    with pytest.raises(Exception):
        safe_parse_json("")
