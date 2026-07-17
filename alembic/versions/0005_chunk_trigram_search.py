"""Add trigram search support for document chunks.

Revision ID: 0005_chunk_trigram_search
Revises: 0004_chunk_embeddings
"""

from alembic import op


revision = "0005_chunk_trigram_search"
down_revision = "0004_chunk_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX idx_document_chunk_content_trgm "
        "ON document_chunk USING gist (content gist_trgm_ops) "
        "WHERE chunk_type = 'CHILD'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_document_chunk_content_trgm")
