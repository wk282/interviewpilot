import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import TimestampMixin


class JobApplication(TimestampMixin, Base):
    __tablename__ = "job_application"
    __table_args__ = (
        CheckConstraint(
            "status IN ('SUBMITTED', 'REVIEWING', 'INTERVIEW', 'REJECTED', "
            "'WITHDRAWN', 'HIRED')",
            name="job_application_status",
        ),
        UniqueConstraint(
            "job_position_id", "candidate_user_id", name="job_application_position_candidate"
        ),
        Index("idx_job_application_workspace_status", "workspace_id", "status"),
        Index("idx_job_application_candidate_status", "candidate_user_id", "status"),
        Index("idx_job_application_position_created", "job_position_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4()
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False
    )
    job_position_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_position.id", ondelete="CASCADE"), nullable=False
    )
    candidate_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    candidate_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidate_profile.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="SUBMITTED")
    cover_letter: Mapped[str | None] = mapped_column(Text)
    decision_note: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApplicationResume(Base):
    __tablename__ = "application_resume"
    __table_args__ = (
        UniqueConstraint("application_id", name="application_resume_application"),
        Index("idx_application_resume_snapshot_document", "snapshot_document_id"),
        Index("idx_application_resume_source_document", "source_document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4()
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_application.id", ondelete="CASCADE"), nullable=False
    )
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL")
    )
    snapshot_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL")
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MessageThread(TimestampMixin, Base):
    __tablename__ = "message_thread"
    __table_args__ = (
        UniqueConstraint("application_id", name="message_thread_application"),
        Index("idx_message_thread_candidate_updated", "candidate_user_id", "updated_at"),
        Index("idx_message_thread_workspace_updated", "workspace_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4()
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_application.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False
    )
    candidate_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)


class PlatformMessage(Base):
    __tablename__ = "platform_message"
    __table_args__ = (
        CheckConstraint(
            "sender_type IN ('CANDIDATE', 'ENTERPRISE', 'SYSTEM')",
            name="platform_message_sender_type",
        ),
        CheckConstraint(
            "message_type IN ('TEXT', 'INTERVIEW_INVITATION', 'APPLICATION_STATUS')",
            name="platform_message_type",
        ),
        CheckConstraint(
            "sender_type = 'SYSTEM' OR sender_user_id IS NOT NULL",
            name="platform_message_sender_user",
        ),
        UniqueConstraint(
            "thread_id",
            "interview_session_id",
            "message_type",
            name="platform_message_thread_interview_type",
        ),
        Index("idx_platform_message_thread_created", "thread_id", "created_at"),
        Index("idx_platform_message_interview", "interview_session_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4()
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("message_thread.id", ondelete="CASCADE"), nullable=False
    )
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sender_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    message_type: Mapped[str] = mapped_column(String(30), nullable=False, server_default="TEXT")
    interview_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_session.id", ondelete="SET NULL")
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MessageRead(Base):
    __tablename__ = "message_read"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="message_read_message_user"),
        Index("idx_message_read_user", "user_id", "read_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4()
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_message.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
