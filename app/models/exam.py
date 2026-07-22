"""Exam and Subject models — hierarchical taxonomy for exam materials."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.knowledge import KnowledgeConcept


class Exam(Base):
    __tablename__ = "exams"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    subjects: Mapped[list[Subject]] = relationship(
        back_populates="exam", cascade="all, delete-orphan"
    )
    documents: Mapped[list[Document]] = relationship(back_populates="exam")
    concepts: Mapped[list[KnowledgeConcept]] = relationship(back_populates="exam")

    def __repr__(self) -> str:
        return f"<Exam code={self.code!r}>"


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (UniqueConstraint("exam_id", "code", name="uq_subjects_exam_code"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    exam_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exams.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    exam: Mapped[Exam] = relationship(back_populates="subjects")
    concepts: Mapped[list[KnowledgeConcept]] = relationship(back_populates="subject")

    def __repr__(self) -> str:
        return f"<Subject code={self.code!r} exam_id={self.exam_id}>"
