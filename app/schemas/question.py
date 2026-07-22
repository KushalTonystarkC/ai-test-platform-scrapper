"""Pydantic schemas for MCQ generation and persistence."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DifficultyLiteral = Literal["easy", "medium", "hard"]


class GenerateQuestionRequest(BaseModel):
    exam_id: uuid.UUID
    topic: str = Field(..., min_length=1, max_length=512)
    count: int = Field(default=1, ge=1, le=5)
    difficulty: DifficultyLiteral | None = None
    document_id: uuid.UUID | None = None
    subject: str | None = Field(default=None, max_length=255)


class GeneratedMCQ(BaseModel):
    """Single LLM-produced MCQ before / after validation."""

    stem: str = Field(..., min_length=1)
    options: list[str] = Field(..., min_length=4, max_length=4)
    correct_index: int = Field(..., ge=0, le=3)
    explanation: str = ""
    subject: str = ""
    topic: str = ""
    difficulty: DifficultyLiteral = "medium"

    @field_validator("options")
    @classmethod
    def options_nonempty(cls, value: list[str]) -> list[str]:
        cleaned = [str(v).strip() for v in value]
        if len(cleaned) != 4 or any(not o for o in cleaned):
            raise ValueError("options must be exactly 4 non-empty strings")
        return cleaned

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
    topic: str
    context_used: int
    items: list[QuestionRead]


class QuestionListResponse(BaseModel):
    items: list[QuestionRead]
    total: int
    limit: int
    offset: int
