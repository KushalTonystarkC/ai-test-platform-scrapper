"""Add questions table for persisted IBPS-style MCQs.

Revision ID: 003_questions
Revises: 002_embedding_dim_384
Create Date: 2026-07-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_questions"
down_revision: str | None = "002_embedding_dim_384"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("exam_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stem", sa.Text(), nullable=False),
        sa.Column(
            "options",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("correct_index", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
        sa.Column("subject", sa.String(255), nullable=False, server_default=""),
        sa.Column("topic", sa.String(512), nullable=False, server_default=""),
        sa.Column("difficulty", sa.String(32), nullable=False, server_default="medium"),
        sa.Column(
            "source_chunk_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["exam_id"], ["exams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_questions_exam_id", "questions", ["exam_id"])
    op.create_index("ix_questions_topic", "questions", ["topic"])
    op.create_index("ix_questions_difficulty", "questions", ["difficulty"])


def downgrade() -> None:
    op.drop_index("ix_questions_difficulty", table_name="questions")
    op.drop_index("ix_questions_topic", table_name="questions")
    op.drop_index("ix_questions_exam_id", table_name="questions")
    op.drop_table("questions")
