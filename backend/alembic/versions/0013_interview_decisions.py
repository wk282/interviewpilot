"""Add decisions for all enterprise interviews.

Revision ID: 0013_interview_decisions
Revises: 0012_application_decision
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0013_interview_decisions"
down_revision = "0012_application_decision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interview_decision",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("internal_note", sa.Text(), nullable=True),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "decision IN ('HIRED', 'REJECTED')",
            name="interview_decision_value",
        ),
        sa.ForeignKeyConstraint(
            ["interview_session_id"],
            ["interview_session.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["decided_by"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("interview_session_id", name="interview_decision_session"),
    )
    op.create_index("idx_interview_decision_decided_by", "interview_decision", ["decided_by"])
    op.create_index("idx_interview_decision_decided_at", "interview_decision", ["decided_at"])
    op.execute(
        """
        INSERT INTO interview_decision (
            interview_session_id, decision, internal_note, decided_by, decided_at
        )
        SELECT interview.id, application.status, application.decision_note,
               application.decided_by, COALESCE(application.decided_at, NOW())
        FROM job_application AS application
        JOIN LATERAL (
            SELECT interview_session.id
            FROM interview_session
            WHERE interview_session.application_id = application.id
              AND interview_session.status = 'COMPLETED'
            ORDER BY interview_session.created_at DESC
            LIMIT 1
        ) AS interview ON TRUE
        WHERE application.status IN ('HIRED', 'REJECTED')
        ON CONFLICT (interview_session_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("interview_decision")
