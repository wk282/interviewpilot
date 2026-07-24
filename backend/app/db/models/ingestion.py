import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.document import DocumentVersion


class IngestionJob(Base):
    __tablename__ = "ingestion_job"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'WAITING_OCR', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ingestion_job_status",
        ),
        CheckConstraint(
            "current_stage IS NULL OR current_stage IN ('VALIDATION', 'PARSING', 'QUALITY_CHECK', "
            "'OCR', 'CLEANING', 'CHUNKING', 'EMBEDDING', 'INDEXING')",
            name="ingestion_job_current_stage",
        ),
        CheckConstraint("progress BETWEEN 0 AND 100", name="ingestion_job_progress"),
        CheckConstraint("retry_count >= 0", name="ingestion_job_retry_count"),
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="ingestion_job_time",
        ),
        CheckConstraint("status <> 'COMPLETED' OR progress = 100", name="ingestion_job_completed_progress"),
        Index("idx_ingestion_job_document_version", "document_version_id", "created_at"),
        Index("idx_ingestion_job_status_created", "status", "created_at"),
        Index("idx_ingestion_job_requested_by", "requested_by"),
        Index("idx_ingestion_job_status_stage", "status", "current_stage"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4()
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_version.id", ondelete="CASCADE"), nullable=False
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PENDING")
    current_stage: Mapped[str | None] = mapped_column(String(50))
    progress: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document_version: Mapped["DocumentVersion"] = relationship(back_populates="ingestion_jobs")
    stage_runs: Mapped[list["IngestionStageRun"]] = relationship(
        back_populates="ingestion_job", cascade="all, delete-orphan"
    )


class IngestionStageRun(Base):
    __tablename__ = "ingestion_stage_run"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('VALIDATION', 'PARSING', 'QUALITY_CHECK', 'CLEANING', "
            "'OCR', 'CHUNKING', 'EMBEDDING', 'INDEXING')",
            name="ingestion_stage_run_stage",
        ),
        CheckConstraint("attempt_no > 0", name="ingestion_stage_run_attempt"),
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'SKIPPED')",
            name="ingestion_stage_run_status",
        ),
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="ingestion_stage_run_time",
        ),
        UniqueConstraint("ingestion_job_id", "stage", "attempt_no", name="ingestion_stage_attempt"),
        Index("idx_ingestion_stage_run_status", "status"),
        Index("idx_ingestion_stage_run_job_created", "ingestion_job_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4()
    )
    ingestion_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingestion_job.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PENDING")
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    ingestion_job: Mapped[IngestionJob] = relationship(back_populates="stage_runs")
