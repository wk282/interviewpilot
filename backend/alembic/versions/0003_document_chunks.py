"""Add parent-child document chunks.

Revision ID: 0003_document_chunks
Revises: 0002_workspace_invitations
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0003_document_chunks"
down_revision = "0002_workspace_invitations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_chunk",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_chunk_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("chunk_type", sa.String(length=10), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("chunk_type IN ('PARENT', 'CHILD')", name=op.f("ck_document_chunk_type")),
        sa.CheckConstraint("chunk_index >= 0", name=op.f("ck_document_chunk_index")),
        sa.CheckConstraint("char_count > 0", name=op.f("ck_document_chunk_char_count")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_base.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_version.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_chunk_id"], ["document_chunk.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_version_id",
            "chunk_type",
            "chunk_index",
            name="uq_document_chunk_version_type_index",
        ),
    )
    op.create_index("idx_document_chunk_workspace", "document_chunk", ["workspace_id"])
    op.create_index("idx_document_chunk_knowledge_base", "document_chunk", ["knowledge_base_id"])
    op.create_index("idx_document_chunk_document_version", "document_chunk", ["document_version_id"])
    op.create_index("idx_document_chunk_parent", "document_chunk", ["parent_chunk_id"])
    op.create_index("idx_document_chunk_content_hash", "document_chunk", ["content_hash"])


def downgrade() -> None:
    op.drop_table("document_chunk")
