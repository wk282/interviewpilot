import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.ingestion import IngestionJob
    from app.db.models.knowledge_base import KnowledgeBase


class Document(TimestampMixin, Base):
    __tablename__ = "document"
    __table_args__ = (
        CheckConstraint(
            "status IN ('UPLOADED', 'PROCESSING', 'READY', 'FAILED', 'DELETED')",
            name="document_status",
        ),
        CheckConstraint("status = 'DELETED' OR deleted_at IS NULL", name="document_deleted_at"),
        Index("idx_document_knowledge_base", "knowledge_base_id"),
        Index("idx_document_knowledge_base_status", "knowledge_base_id", "status"),
        Index("idx_document_uploaded_by", "uploaded_by"),
        Index(
            "idx_document_active_in_knowledge_base",
            "knowledge_base_id",
            "created_at",
            postgresql_where=text("status <> 'DELETED'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4()
    )
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_base.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="UPLOADED")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    knowledge_base: Mapped["KnowledgeBase"] = relationship(back_populates="documents")
    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentVersion(Base):
    __tablename__ = "document_version"
    __table_args__ = (
        CheckConstraint("version_number > 0", name="document_version_number"),
        CheckConstraint("file_size >= 0", name="document_version_file_size"),
        CheckConstraint(
            "status IN ('UPLOADED', 'PROCESSING', 'READY', 'FAILED')",
            name="document_version_status",
        ),
        CheckConstraint("file_hash ~ '^[0-9a-fA-F]{64}$'", name="document_version_file_hash"),
        UniqueConstraint("document_id", "version_number", name="document_version_number"),
        Index("idx_document_version_document_hash", "document_id", "file_hash"),
        Index("idx_document_version_status", "status"),
        Index("idx_document_version_latest", "document_id", "version_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4()
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(150), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_name: Mapped[str | None] = mapped_column(String(100))
    parser_version: Mapped[str | None] = mapped_column(String(50))
    parsed_content_key: Mapped[str | None] = mapped_column(String(500))
    quality_report: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="UPLOADED")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped[Document] = relationship(back_populates="versions")
    ingestion_jobs: Mapped[list["IngestionJob"]] = relationship(
        back_populates="document_version", cascade="all, delete-orphan"
    )
