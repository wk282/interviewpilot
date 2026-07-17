"""Add pgvector embeddings to document chunks.

Revision ID: 0004_chunk_embeddings
Revises: 0003_document_chunks
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision = "0004_chunk_embeddings"
down_revision = "0003_document_chunks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_chunk", sa.Column("embedding", Vector(1024), nullable=True))
    op.add_column("document_chunk", sa.Column("embedding_model", sa.String(length=100), nullable=True))
    op.add_column("document_chunk", sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "CREATE INDEX idx_document_chunk_embedding_hnsw "
        "ON document_chunk USING hnsw (embedding vector_cosine_ops) "
        "WHERE chunk_type = 'CHILD' AND embedding IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_document_chunk_embedding_hnsw")
    op.drop_column("document_chunk", "embedded_at")
    op.drop_column("document_chunk", "embedding_model")
    op.drop_column("document_chunk", "embedding")
