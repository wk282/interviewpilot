"""Add dynamic interview decision metadata.

Revision ID: 0008_dynamic_interview_metadata
Revises: 0007_candidate_resume_document
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0008_dynamic_interview_metadata"
down_revision = "0007_candidate_resume_document"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interview_question",
        sa.Column(
            "decision_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("interview_question", "decision_metadata")
