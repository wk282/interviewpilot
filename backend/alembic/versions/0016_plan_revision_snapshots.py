"""Add snapshots and question budgets to interview plan revisions.

Revision ID: 0016_plan_revision_snapshots
Revises: 0015_interview_quality_audit
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0016_plan_revision_snapshots"
down_revision = "0015_interview_quality_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interview_plan_revision",
        sa.Column(
            "before_snapshot",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "interview_plan_revision",
        sa.Column(
            "after_snapshot",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "interview_plan_revision",
        sa.Column(
            "change_set",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "interview_plan_revision",
        sa.Column(
            "remaining_question_budget",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "interview_plan_revision",
        sa.Column(
            "competency_budget",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "interview_plan_revision_remaining_budget",
        "interview_plan_revision",
        "remaining_question_budget >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "interview_plan_revision_remaining_budget",
        "interview_plan_revision",
        type_="check",
    )
    op.drop_column("interview_plan_revision", "competency_budget")
    op.drop_column("interview_plan_revision", "remaining_question_budget")
    op.drop_column("interview_plan_revision", "change_set")
    op.drop_column("interview_plan_revision", "after_snapshot")
    op.drop_column("interview_plan_revision", "before_snapshot")
