"""KnowledgeConcept — extracted concepts linked to exams/subjects."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.exam import Exam, Subject


class KnowledgeConcept(Base):
    """Canonical concept extracted across documents for an exam/subject."""

    __tablename__ = "knowledge_concepts"
    __table_args__ = (
        UniqueConstraint("exam_id", "name", name="uq_concepts_exam_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    exam_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    aliases: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    exam: Mapped[Exam] = relationship(back_populates="concepts")
    subject: Mapped[Subject | None] = relationship(back_populates="concepts")

    def __repr__(self) -> str:
        return f"<KnowledgeConcept name={self.name!r}>"
