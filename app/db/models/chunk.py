import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.db.base import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunk"
    __table_args__ = (
        CheckConstraint("chunk_type IN ('PARENT', 'CHILD')", name="document_chunk_type"),
        CheckConstraint("chunk_index >= 0", name="document_chunk_index"),
        CheckConstraint("char_count > 0", name="document_chunk_char_count"),
        UniqueConstraint(
            "document_version_id", "chunk_type", "chunk_index", name="document_chunk_version_type_index"
        ),
        Index("idx_document_chunk_workspace", "workspace_id"),
        Index("idx_document_chunk_knowledge_base", "knowledge_base_id"),
        Index("idx_document_chunk_document_version", "document_version_id"),
        Index("idx_document_chunk_parent", "parent_chunk_id"),
        Index("idx_document_chunk_content_hash", "content_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False
    )
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_base.id", ondelete="CASCADE"), nullable=False
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_version.id", ondelete="CASCADE"), nullable=False
    )
    parent_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunk.id", ondelete="CASCADE")
    )
    chunk_type: Mapped[str] = mapped_column(String(10), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
