"""Add enterprise workspace invitations.

Revision ID: 0002_workspace_invitations
Revises: 0001_foundation_baseline
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_workspace_invitations"
down_revision = "0001_foundation_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_workspace_member_role"), "workspace_member", type_="check")
    op.alter_column("workspace_member", "role", server_default=None)
    op.create_check_constraint(
        op.f("ck_workspace_member_role"),
        "workspace_member",
        "role IN ('OWNER', 'ADMIN', 'HR', 'INTERVIEWER', 'VIEWER')",
    )

    op.create_table(
        "workspace_invitation",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("invited_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "role IN ('ADMIN', 'HR', 'INTERVIEWER', 'VIEWER')",
            name=op.f("ck_workspace_invitation_role"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'ACCEPTED', 'EXPIRED', 'REVOKED')",
            name=op.f("ck_workspace_invitation_status"),
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by"], ["app_user.id"]),
        sa.ForeignKeyConstraint(["accepted_by"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_workspace_invitation_token_hash"),
    )
    op.create_index("idx_workspace_invitation_workspace_status", "workspace_invitation", ["workspace_id", "status"])
    op.create_index("idx_workspace_invitation_email_status", "workspace_invitation", ["email", "status"])


def downgrade() -> None:
    op.drop_table("workspace_invitation")
    op.drop_constraint(op.f("ck_workspace_member_role"), "workspace_member", type_="check")
    op.create_check_constraint(
        op.f("ck_workspace_member_role"),
        "workspace_member",
        "role IN ('OWNER', 'ADMIN', 'HR', 'INTERVIEWER', 'VIEWER', 'MEMBER')",
    )
    op.alter_column("workspace_member", "role", server_default="MEMBER")
