"""Support comprehension (shared-stimulus) question sets.

Revision ID: 004_comprehension
Revises: 003_questions
Create Date: 2026-07-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_comprehension"
down_revision: str | None = "003_questions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "questions",
        sa.Column(
            "question_type",
            sa.String(32),
            nullable=False,
            server_default="standalone",
        ),
    )
    op.add_column(
        "questions",
        sa.Column("set_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "questions",
        sa.Column("set_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "questions",
        sa.Column("directions", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "questions",
        sa.Column("passage", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_questions_question_type", "questions", ["question_type"])
    op.create_index("ix_questions_set_id", "questions", ["set_id"])


def downgrade() -> None:
    op.drop_index("ix_questions_set_id", table_name="questions")
    op.drop_index("ix_questions_question_type", table_name="questions")
    op.drop_column("questions", "passage")
    op.drop_column("questions", "directions")
    op.drop_column("questions", "set_index")
    op.drop_column("questions", "set_id")
    op.drop_column("questions", "question_type")
