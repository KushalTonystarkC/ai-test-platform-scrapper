"""Pydantic schemas for MCQ generation and persistence."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


DifficultyLiteral = Literal["easy", "medium", "hard"]
QuestionTypeLiteral = Literal["standalone", "comprehension"]

# Many exams use 4 choices; some (e.g. banking) use 5 with "None of these".
# Schema accepts both; generation picks a count from the source material.
MIN_OPTIONS = 4
MAX_OPTIONS = 5
OPTION_LETTERS = ("A", "B", "C", "D", "E")
_LETTER_MAP = {letter: i for i, letter in enumerate(OPTION_LETTERS)}


def normalize_mcq_options(value: Any) -> list[str]:
    """Coerce messy LLM option payloads into 4 or 5 choice strings."""
    if value is None:
        raise ValueError("options is required")

    if isinstance(value, str):
        text = value.strip()
        # A) ... B) ... C) ... D) ... E) ...
        labeled = re.findall(
            r"(?:^|\s)(?:[A-Ea-e][\)\.]|\([A-Ea-e]\))\s*(.+?)(?=(?:\s(?:[A-Ea-e][\)\.]|\([A-Ea-e]\)))|$)",
            text,
            flags=re.DOTALL,
        )
        if len(labeled) >= MIN_OPTIONS:
            return [p.strip() for p in labeled[:MAX_OPTIONS]]
        parts = [p.strip() for p in re.split(r"[\n|;]+", text) if p.strip()]
        if len(parts) >= MIN_OPTIONS:
            return parts[:MAX_OPTIONS]
        raise ValueError("could not parse options string into 4 or 5 choices")

    if not isinstance(value, list):
        raise ValueError("options must be a list or string")

    cleaned = [str(v).strip() for v in value if str(v).strip()]
    if MIN_OPTIONS <= len(cleaned) <= MAX_OPTIONS:
        return cleaned

    # Prefer phrase-like choices (models sometimes emit word tokens)
    phrases = [o for o in cleaned if len(o.split()) >= 2 or len(o) >= 12]
    if len(phrases) >= MIN_OPTIONS:
        return phrases[:MAX_OPTIONS] if len(phrases) == MAX_OPTIONS else phrases[:MIN_OPTIONS]

    if len(cleaned) > MAX_OPTIONS:
        # Pack word tokens into 4 roughly equal groups
        groups: list[list[str]] = [[] for _ in range(MIN_OPTIONS)]
        for i, token in enumerate(cleaned):
            groups[i % MIN_OPTIONS].append(token)
        packed = [" ".join(g).strip() for g in groups]
        if all(packed):
            return packed

    raise ValueError(f"options must have 4 or 5 items, got {len(cleaned)}")


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


def _option_count(data: dict[str, Any]) -> int:
    options = data.get("options")
    if isinstance(options, list):
        count = len([o for o in options if str(o).strip()])
        if MIN_OPTIONS <= count <= MAX_OPTIONS:
            return count
    return MIN_OPTIONS


def _resolve_correct_index(data: dict[str, Any]) -> int | None:
    count = _option_count(data)
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
            if 0 <= value < count:
                return value
            if 1 <= value <= count:  # 1-based
                return value - 1
            continue
        text = str(value).strip()
        upper = text.upper()
        if upper in _LETTER_MAP and _LETTER_MAP[upper] < count:
            return _LETTER_MAP[upper]
        # Match against option text
        options = data.get("options")
        if isinstance(options, list):
            for i, opt in enumerate(options[:count]):
                if str(opt).strip().lower() == text.lower():
                    return i
        try:
            num = int(text)
            if 0 <= num < count:
                return num
            if 1 <= num <= count:
                return num - 1
        except ValueError:
            pass
    return None


class GenerateQuestionRequest(BaseModel):
    exam_id: uuid.UUID
    # If omitted, sample diverse chunks across the exam (whole syllabus mode)
    topic: str | None = Field(default=None, max_length=512)
    count: int = Field(default=1, ge=1)
    difficulty: DifficultyLiteral | None = None
    document_id: uuid.UUID | None = None
    subject: str | None = Field(default=None, max_length=255)
    # "auto" infers comprehension when the source chunks are passage / directions based.
    question_type: Literal["auto", "standalone", "comprehension"] = "auto"
    # Questions per shared-stimulus set (comprehension only).
    set_size: int = Field(default=3, ge=2, le=5)

    @field_validator("topic", mode="before")
    @classmethod
    def empty_topic_as_none(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("count")
    @classmethod
    def count_within_configured_max(cls, value: int) -> int:
        from app.core.config import get_settings

        max_count = get_settings().question_generate_max_count
        if value > max_count:
            raise ValueError(f"count must be <= {max_count}")
        return value


class GeneratedMCQ(BaseModel):
    """Single LLM-produced MCQ before / after validation."""

    stem: str = Field(..., min_length=1)
    options: list[str] = Field(..., min_length=MIN_OPTIONS, max_length=MAX_OPTIONS)
    correct_index: int = Field(default=0, ge=0, le=MAX_OPTIONS - 1)
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
        if not (MIN_OPTIONS <= len(cleaned) <= MAX_OPTIONS) or any(not o for o in cleaned):
            raise ValueError("options must be 4 or 5 non-empty strings")
        return cleaned

    @field_validator("correct_index", mode="before")
    @classmethod
    def coerce_correct_index(cls, value: Any) -> int:
        if value is None or value == "":
            return 0
        if isinstance(value, str):
            text = value.strip().upper()
            if text in _LETTER_MAP:
                return _LETTER_MAP[text]
            value = int(text)
        idx = int(value)
        if idx < 0 or idx >= MAX_OPTIONS:
            raise ValueError(f"correct_index must be 0..{MAX_OPTIONS - 1}")
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

    @model_validator(mode="after")
    def correct_index_within_options(self) -> GeneratedMCQ:
        if self.correct_index >= len(self.options):
            raise ValueError(
                f"correct_index {self.correct_index} is out of range "
                f"for {len(self.options)} options"
            )
        return self


class GeneratedQuestionSet(BaseModel):
    """A shared-stimulus (comprehension) set: directions + passage + linked MCQs."""

    directions: str = ""
    passage: str = Field(..., min_length=1)
    questions: list[GeneratedMCQ] = Field(..., min_length=1)

    @field_validator("directions", "passage", mode="before")
    @classmethod
    def coerce_text(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            return "\n".join(str(v).strip() for v in value if str(v).strip())
        return str(value).strip()


class QuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    exam_id: uuid.UUID
    subject_id: uuid.UUID | None = None
    question_type: QuestionTypeLiteral = "standalone"
    set_id: uuid.UUID | None = None
    set_index: int = 0
    directions: str = ""
    passage: str = ""
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

    @field_validator("question_type", mode="before")
    @classmethod
    def coerce_question_type(cls, value: Any) -> str:
        text = str(value or "").strip().lower()
        return text if text in {"standalone", "comprehension"} else "standalone"

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
                "question_type": getattr(obj, "question_type", "standalone"),
                "set_id": getattr(obj, "set_id", None),
                "set_index": getattr(obj, "set_index", 0) or 0,
                "directions": getattr(obj, "directions", "") or "",
                "passage": getattr(obj, "passage", "") or "",
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
    question_type: QuestionTypeLiteral = "standalone"
    requested_count: int
    generated_count: int
    context_used: int
    items: list[QuestionRead]


class QuestionListResponse(BaseModel):
    items: list[QuestionRead]
    total: int
    limit: int
    offset: int
