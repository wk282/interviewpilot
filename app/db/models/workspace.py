import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.knowledge_base import KnowledgeBase
    from app.db.models.user import AppUser


class Workspace(TimestampMixin, Base):
    __tablename__ = "workspace"
    __table_args__ = (
        CheckConstraint("type IN ('PERSONAL', 'ORGANIZATION')", name="workspace_type"),
        Index("idx_workspace_created_by", "created_by"),
        Index(
            "uq_workspace_personal_creator",
            "created_by",
            unique=True,
            postgresql_where=text("type = 'PERSONAL'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4()
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False
    )

    creator: Mapped["AppUser"] = relationship(back_populates="created_workspaces")
    members: Mapped[list["WorkspaceMember"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    knowledge_bases: Mapped[list["KnowledgeBase"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class WorkspaceMember(Base):
    __tablename__ = "workspace_member"
    __table_args__ = (
        CheckConstraint(
            "role IN ('OWNER', 'ADMIN', 'HR', 'INTERVIEWER', 'VIEWER')",
            name="workspace_member_role",
        ),
        UniqueConstraint("workspace_id", "user_id", name="workspace_member"),
        Index("idx_workspace_member_user_id", "user_id"),
        Index("idx_workspace_member_workspace_role", "workspace_id", "role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4()
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    workspace: Mapped[Workspace] = relationship(back_populates="members")
    user: Mapped["AppUser"] = relationship(back_populates="memberships")
