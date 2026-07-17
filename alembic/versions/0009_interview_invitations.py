"""Add candidate interview invitations.

Revision ID: 0009_interview_invitations
Revises: 0008_dynamic_interview_metadata
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0009_interview_invitations"
down_revision = "0008_dynamic_interview_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interview_invitation",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("access_code_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("max_access_count", sa.Integer(), server_default="5", nullable=False),
        sa.Column("access_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING', 'OPENED', 'VERIFIED', 'STARTED', 'COMPLETED', "
            "'EXPIRED', 'REVOKED')",
            name="interview_invitation_status",
        ),
        sa.CheckConstraint("email = LOWER(email)", name="interview_invitation_email_lowercase"),
        sa.CheckConstraint("max_access_count > 0", name="interview_invitation_max_access_count"),
        sa.CheckConstraint(
            "access_count >= 0 AND access_count <= max_access_count",
            name="interview_invitation_access_count",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["interview_session_id"], ["interview_session.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="interview_invitation_token_hash"),
    )
    op.create_index(
        "idx_interview_invitation_interview_status",
        "interview_invitation",
        ["interview_session_id", "status"],
    )
    op.create_index(
        "idx_interview_invitation_workspace_created",
        "interview_invitation",
        ["workspace_id", "created_at"],
    )
    op.create_index(
        "idx_interview_invitation_email", "interview_invitation", ["email"]
    )


def downgrade() -> None:
    op.drop_table("interview_invitation")
