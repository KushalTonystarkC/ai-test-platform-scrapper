"""Generated MCQ question model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.exam import Exam, Subject


class Question(Base):
    """Persisted multiple-choice question (4-5 options, single correct).

    Comprehension questions share a stimulus: rows with the same ``set_id`` belong to
    one set and repeat the same ``directions`` / ``passage``, ordered by ``set_index``.
    """

    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    exam_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True
    )
    question_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="standalone", index=True
    )
    set_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    set_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    directions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    passage: Mapped[str] = mapped_column(Text, nullable=False, default="")
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    correct_index: Mapped[int] = mapped_column(Integer, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    subject: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    topic: Mapped[str] = mapped_column(String(512), nullable=False, default="", index=True)
    difficulty: Mapped[str] = mapped_column(String(32), nullable=False, default="medium", index=True)
    source_chunk_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    exam: Mapped[Exam] = relationship()
    subject_ref: Mapped[Subject | None] = relationship(foreign_keys=[subject_id])

    def __repr__(self) -> str:
        return f"<Question id={self.id} topic={self.topic!r}>"
