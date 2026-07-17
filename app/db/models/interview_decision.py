import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import TimestampMixin


class InterviewDecision(TimestampMixin, Base):
    __tablename__ = "interview_decision"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('HIRED', 'REJECTED')",
            name="interview_decision_value",
        ),
        UniqueConstraint(
            "interview_session_id",
            name="interview_decision_session",
        ),
        Index("idx_interview_decision_decided_by", "decided_by"),
        Index("idx_interview_decision_decided_at", "decided_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4()
    )
    interview_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    internal_note: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
