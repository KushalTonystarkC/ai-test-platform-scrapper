"""Pydantic schemas for MCQ generation and persistence."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


DifficultyLiteral = Literal["easy", "medium", "hard"]


def normalize_mcq_options(value: Any) -> list[str]:
    """Coerce messy LLM option payloads into exactly 4 choice strings."""
    if value is None:
        raise ValueError("options is required")

    if isinstance(value, str):
        text = value.strip()
        # A) ... B) ... C) ... D) ...
        labeled = re.findall(
            r"(?:^|\s)(?:[A-Da-d][\)\.]|\([A-Da-d]\))\s*(.+?)(?=(?:\s(?:[A-Da-d][\)\.]|\([A-Da-d]\)))|$)",
            text,
            flags=re.DOTALL,
        )
        if len(labeled) >= 4:
            return [p.strip() for p in labeled[:4]]
        parts = [p.strip() for p in re.split(r"[\n|;]+", text) if p.strip()]
        if len(parts) >= 4:
            return parts[:4]
        raise ValueError("could not parse options string into 4 choices")

    if not isinstance(value, list):
        raise ValueError("options must be a list or string")

    cleaned = [str(v).strip() for v in value if str(v).strip()]
    if len(cleaned) == 4:
        return cleaned

    # Prefer phrase-like choices (models sometimes emit word tokens)
    phrases = [o for o in cleaned if len(o.split()) >= 2 or len(o) >= 12]
    if len(phrases) >= 4:
        return phrases[:4]

    if len(cleaned) > 4:
        # Pack word tokens into 4 roughly equal groups
        groups: list[list[str]] = [[] for _ in range(4)]
        for i, token in enumerate(cleaned):
            groups[i % 4].append(token)
        packed = [" ".join(g).strip() for g in groups]
        if all(packed):
            return packed

    if 1 <= len(cleaned) < 4:
        # Pad with placeholders so validation can still fail clearly upstream if needed
        raise ValueError(f"options must have 4 items, got {len(cleaned)}")

    raise ValueError(f"options must have 4 items, got {len(cleaned)}")


def normalize_mcq_item(item: dict[str, Any]) -> dict[str, Any]:
    """Map common LLM field aliases and fill missing correct_index."""
    data = dict(item)

    if not data.get("stem"):
        for key in ("question", "question_text", "prompt", "text"):
            if data.get(key):
                data["stem"] = data[key]
                break

    if data.get("options") is None:
        for key in ("choices", "answers", "options_list"):
            if data.get(key) is not None:
                data["options"] = data[key]
                break

    if data.get("correct_index") is None:
        resolved = _resolve_correct_index(data)
        data["correct_index"] = 0 if resolved is None else resolved

    return data


def _resolve_correct_index(data: dict[str, Any]) -> int | None:
    for key in (
        "correct_index",
        "correctIndex",
        "answer_index",
        "answerIndex",
        "correct",
        "answer",
        "correct_answer",
        "correctAnswer",
        "correct_option",
        "correctOption",
    ):
        if key not in data or data[key] is None or data[key] == "":
            continue
        value = data[key]
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            if 0 <= value <= 3:
                return value
            if 1 <= value <= 4:  # 1-based
                return value - 1
            continue
        text = str(value).strip()
        letter_map = {"A": 0, "B": 1, "C": 2, "D": 3}
        upper = text.upper()
        if upper in letter_map:
            return letter_map[upper]
        # Match against option text
        options = data.get("options")
        if isinstance(options, list):
            for i, opt in enumerate(options[:4]):
                if str(opt).strip().lower() == text.lower():
                    return i
        try:
            num = int(text)
            if 0 <= num <= 3:
                return num
            if 1 <= num <= 4:
                return num - 1
        except ValueError:
            pass
    return None


class GenerateQuestionRequest(BaseModel):
    exam_id: uuid.UUID
    # If omitted, sample diverse chunks across the exam (whole syllabus mode)
    topic: str | None = Field(default=None, max_length=512)
    count: int = Field(default=1, ge=1, le=10)
    difficulty: DifficultyLiteral | None = None
    document_id: uuid.UUID | None = None
    subject: str | None = Field(default=None, max_length=255)

    @field_validator("topic", mode="before")
    @classmethod
    def empty_topic_as_none(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class GeneratedMCQ(BaseModel):
    """Single LLM-produced MCQ before / after validation."""

    stem: str = Field(..., min_length=1)
    options: list[str] = Field(..., min_length=4, max_length=4)
    correct_index: int = Field(default=0, ge=0, le=3)
    explanation: str = ""
    subject: str = ""
    topic: str = ""
    difficulty: DifficultyLiteral = "medium"

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return normalize_mcq_item(value)
        return value

    @field_validator("options", mode="before")
    @classmethod
    def options_nonempty(cls, value: Any) -> list[str]:
        cleaned = normalize_mcq_options(value)
        if len(cleaned) != 4 or any(not o for o in cleaned):
            raise ValueError("options must be exactly 4 non-empty strings")
        return cleaned

    @field_validator("correct_index", mode="before")
    @classmethod
    def coerce_correct_index(cls, value: Any) -> int:
        if value is None or value == "":
            return 0
        if isinstance(value, str):
            text = value.strip().upper()
            letter_map = {"A": 0, "B": 1, "C": 2, "D": 3}
            if text in letter_map:
                return letter_map[text]
            value = int(text)
        idx = int(value)
        if idx < 0 or idx > 3:
            raise ValueError("correct_index must be 0..3")
        return idx

    @field_validator("difficulty", mode="before")
    @classmethod
    def normalize_difficulty(cls, value: Any) -> str:
        if value is None or value == "":
            return "medium"
        text = str(value).strip().lower()
        if text not in {"easy", "medium", "hard"}:
            return "medium"
        return text


class QuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    exam_id: uuid.UUID
    subject_id: uuid.UUID | None = None
    stem: str
    options: list[str]
    correct_index: int
    explanation: str
    subject: str
    topic: str
    difficulty: str
    source_chunk_ids: list[uuid.UUID]
    document_id: uuid.UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @field_validator("source_chunk_ids", mode="before")
    @classmethod
    def coerce_chunk_ids(cls, value: Any) -> list[uuid.UUID]:
        if not value:
            return []
        result: list[uuid.UUID] = []
        for item in value:
            result.append(item if isinstance(item, uuid.UUID) else uuid.UUID(str(item)))
        return result

    @field_validator("metadata", mode="before")
    @classmethod
    def coerce_metadata(cls, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @classmethod
    def model_validate(cls, obj: Any, **kwargs: Any) -> QuestionRead:  # type: ignore[override]
        if hasattr(obj, "extra_metadata"):
            data = {
                "id": obj.id,
                "exam_id": obj.exam_id,
                "subject_id": obj.subject_id,
                "stem": obj.stem,
                "options": obj.options,
                "correct_index": obj.correct_index,
                "explanation": obj.explanation or "",
                "subject": obj.subject or "",
                "topic": obj.topic or "",
                "difficulty": obj.difficulty or "medium",
                "source_chunk_ids": obj.source_chunk_ids or [],
                "document_id": obj.document_id,
                "metadata": obj.extra_metadata or {},
                "created_at": obj.created_at,
            }
            return super().model_validate(data, **kwargs)
        return super().model_validate(obj, **kwargs)


class GenerateQuestionResponse(BaseModel):
    exam_id: uuid.UUID
    topic: str | None = None
    mode: Literal["topic", "full_syllabus"]
    requested_count: int
    generated_count: int
    context_used: int
    items: list[QuestionRead]


class QuestionListResponse(BaseModel):
    items: list[QuestionRead]
    total: int
    limit: int
    offset: int
