import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.document import Document
    from app.db.models.workspace import Workspace


class KnowledgeBase(TimestampMixin, Base):
    __tablename__ = "knowledge_base"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('RESUME', 'PERSONAL_LEARNING', 'PUBLIC_QUESTION_BANK', "
            "'ENTERPRISE_QUESTION_BANK', 'JOB_SPECIFIC', 'SCORING_RUBRIC', 'TECHNICAL_STANDARD')",
            name="knowledge_base_purpose",
        ),
        CheckConstraint(
            "visibility IN ('PRIVATE', 'WORKSPACE', 'PUBLIC')",
            name="knowledge_base_visibility",
        ),
        UniqueConstraint("workspace_id", "name", name="knowledge_base_workspace_name"),
        Index("idx_knowledge_base_workspace_purpose", "workspace_id", "purpose"),
        Index("idx_knowledge_base_created_by", "created_by"),
        Index("idx_knowledge_base_workspace_visibility", "workspace_id", "visibility"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4()
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PRIVATE")
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="knowledge_bases")
    documents: Mapped[list["Document"]] = relationship(
        back_populates="knowledge_base", cascade="all, delete-orphan"
    )
