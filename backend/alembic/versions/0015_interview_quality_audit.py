"""Add versioned interview business quality audits.

Revision ID: 0015_interview_quality_audit
Revises: 0014_answer_critic
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0015_interview_quality_audit"
down_revision = "0014_answer_critic"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interview_quality_audit",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("audit_version", sa.String(length=50), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("quality_gates", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("warnings", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["interview_session_id"],
            ["interview_session.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "interview_session_id",
            "audit_version",
            name="interview_quality_audit_session_version",
        ),
    )
    op.create_index(
        "idx_interview_quality_audit_session_generated",
        "interview_quality_audit",
        ["interview_session_id", "generated_at"],
    )
    op.create_index(
        "idx_interview_quality_audit_passed",
        "interview_quality_audit",
        ["passed", "generated_at"],
    )


def downgrade() -> None:
    op.drop_table("interview_quality_audit")
