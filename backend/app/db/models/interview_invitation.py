import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import TimestampMixin


class InterviewInvitation(TimestampMixin, Base):
    __tablename__ = "interview_invitation"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'OPENED', 'VERIFIED', 'STARTED', 'COMPLETED', "
            "'EXPIRED', 'REVOKED')",
            name="interview_invitation_status",
        ),
        CheckConstraint("email = LOWER(email)", name="interview_invitation_email_lowercase"),
        CheckConstraint("max_access_count > 0", name="interview_invitation_max_access_count"),
        CheckConstraint(
            "access_count >= 0 AND access_count <= max_access_count",
            name="interview_invitation_access_count",
        ),
        UniqueConstraint("token_hash", name="interview_invitation_token_hash"),
        Index("idx_interview_invitation_interview_status", "interview_session_id", "status"),
        Index("idx_interview_invitation_workspace_created", "workspace_id", "created_at"),
        Index("idx_interview_invitation_email", "email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4()
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False
    )
    interview_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    access_code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_token: Mapped[str | None] = mapped_column(Text)
    encrypted_access_code: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PENDING")
    max_access_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False
    )
