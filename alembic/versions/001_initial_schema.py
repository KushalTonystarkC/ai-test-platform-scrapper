"""Initial schema: exams, subjects, documents, chunks, concepts + extensions.

Revision ID: 001_initial
Revises:
Create Date: 2026-07-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Must match Settings.embedding_dimension default / env at migrate time
EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    document_type = postgresql.ENUM(
        "BOOK",
        "PREVIOUS_YEAR_PAPER",
        "SYLLABUS",
        name="document_type",
        create_type=False,
    )
    document_status = postgresql.ENUM(
        "UPLOADED",
        "PROCESSING",
        "PROCESSED",
        "FAILED",
        name="document_status",
        create_type=False,
    )
    document_type.create(op.get_bind(), checkfirst=True)
    document_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "exams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("code", name="uq_exams_code"),
    )
    op.create_index("ix_exams_code", "exams", ["code"])

    op.create_table(
        "subjects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("exam_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["exam_id"], ["exams.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("exam_id", "code", name="uq_subjects_exam_code"),
    )

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("exam_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column(
            "document_type",
            postgresql.ENUM(
                "BOOK",
                "PREVIOUS_YEAR_PAPER",
                "SYLLABUS",
                name="document_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "UPLOADED",
                "PROCESSING",
                "PROCESSED",
                "FAILED",
                name="document_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("storage_path", sa.String(1024), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False, server_default="application/pdf"),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["exam_id"], ["exams.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_documents_exam_id", "documents", ["exam_id"])
    op.create_index("ix_documents_status", "documents", ["status"])

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_index"),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])

    # HNSW index for approximate nearest neighbor search
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_hnsw "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )
    # Trigram index for fuzzy keyword assist
    op.execute(
        "CREATE INDEX ix_document_chunks_content_trgm "
        "ON document_chunks USING gin (content gin_trgm_ops)"
    )
    # GIN FTS index
    op.execute(
        "CREATE INDEX ix_document_chunks_content_fts "
        "ON document_chunks USING gin (to_tsvector('english', content))"
    )

    op.create_table(
        "knowledge_concepts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("exam_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "aliases",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["exam_id"], ["exams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("exam_id", "name", name="uq_concepts_exam_name"),
    )
    op.create_index("ix_knowledge_concepts_exam_id", "knowledge_concepts", ["exam_id"])


def downgrade() -> None:
    op.drop_table("knowledge_concepts")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_fts")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_trgm")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("subjects")
    op.drop_table("exams")
    op.execute("DROP TYPE IF EXISTS document_status")
    op.execute("DROP TYPE IF EXISTS document_type")
