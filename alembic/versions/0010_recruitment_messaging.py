"""Add job applications, resume snapshots and platform messaging.

Revision ID: 0010_recruitment_messaging
Revises: 0009_interview_invitations
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0010_recruitment_messaging"
down_revision = "0009_interview_invitations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_application",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_position_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="SUBMITTED", nullable=False),
        sa.Column("cover_letter", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('SUBMITTED', 'REVIEWING', 'INTERVIEW', 'REJECTED', 'WITHDRAWN', 'HIRED')",
            name="job_application_status",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_position_id"], ["job_position.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_profile_id"], ["candidate_profile.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_position_id", "candidate_user_id", name="job_application_position_candidate"),
    )
    op.create_index("idx_job_application_workspace_status", "job_application", ["workspace_id", "status"])
    op.create_index("idx_job_application_candidate_status", "job_application", ["candidate_user_id", "status"])
    op.create_index("idx_job_application_position_created", "job_application", ["job_position_id", "created_at"])

    op.create_table(
        "application_resume",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("snapshot_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["job_application.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_document_id"], ["document.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["snapshot_document_id"], ["document.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id", name="application_resume_application"),
    )
    op.create_index("idx_application_resume_snapshot_document", "application_resume", ["snapshot_document_id"])
    op.create_index("idx_application_resume_source_document", "application_resume", ["source_document_id"])

    op.create_table(
        "message_thread",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["job_application.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id", name="message_thread_application"),
    )
    op.create_index("idx_message_thread_candidate_updated", "message_thread", ["candidate_user_id", "updated_at"])
    op.create_index("idx_message_thread_workspace_updated", "message_thread", ["workspace_id", "updated_at"])

    op.add_column("interview_session", sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_interview_session_application_id_job_application",
        "interview_session",
        "job_application",
        ["application_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_interview_session_application", "interview_session", ["application_id"])

    op.create_table(
        "platform_message",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_type", sa.String(length=20), nullable=False),
        sa.Column("sender_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message_type", sa.String(length=30), server_default="TEXT", nullable=False),
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("message_metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("sender_type IN ('CANDIDATE', 'ENTERPRISE', 'SYSTEM')", name="platform_message_sender_type"),
        sa.CheckConstraint("message_type IN ('TEXT', 'INTERVIEW_INVITATION', 'APPLICATION_STATUS')", name="platform_message_type"),
        sa.CheckConstraint("sender_type = 'SYSTEM' OR sender_user_id IS NOT NULL", name="platform_message_sender_user"),
        sa.ForeignKeyConstraint(["thread_id"], ["message_thread.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["interview_session_id"], ["interview_session.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id", "interview_session_id", "message_type", name="platform_message_thread_interview_type"),
    )
    op.create_index("idx_platform_message_thread_created", "platform_message", ["thread_id", "created_at"])
    op.create_index("idx_platform_message_interview", "platform_message", ["interview_session_id"])

    op.create_table(
        "message_read",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["platform_message.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "user_id", name="message_read_message_user"),
    )
    op.create_index("idx_message_read_user", "message_read", ["user_id", "read_at"])


def downgrade() -> None:
    op.drop_table("message_read")
    op.drop_table("platform_message")
    op.drop_index("idx_interview_session_application", table_name="interview_session")
    op.drop_constraint("fk_interview_session_application_id_job_application", "interview_session", type_="foreignkey")
    op.drop_column("interview_session", "application_id")
    op.drop_table("message_thread")
    op.drop_table("application_resume")
    op.drop_table("job_application")
