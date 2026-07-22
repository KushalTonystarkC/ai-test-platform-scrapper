"""Resize embedding column for local sentence-transformers (384-dim).

Revision ID: 002_embedding_dim_384
Revises: 001_initial
Create Date: 2026-07-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "002_embedding_dim_384"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Must match Settings.embedding_dimension default for BAAI/bge-small-en-v1.5
NEW_DIM = 384
OLD_DIM = 1536


def upgrade() -> None:
    # Existing vectors are incompatible — clear them; re-process documents after migrate
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.execute("UPDATE document_chunks SET embedding = NULL")
    op.execute(
        f"ALTER TABLE document_chunks "
        f"ALTER COLUMN embedding TYPE vector({NEW_DIM}) "
        f"USING NULL"
    )
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_hnsw "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.execute("UPDATE document_chunks SET embedding = NULL")
    op.execute(
        f"ALTER TABLE document_chunks "
        f"ALTER COLUMN embedding TYPE vector({OLD_DIM}) "
        f"USING NULL"
    )
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_hnsw "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )
