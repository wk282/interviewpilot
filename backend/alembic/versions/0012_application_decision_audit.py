"""Add application decision audit fields.

Revision ID: 0012_application_decision
Revises: 0011_invitation_credentials
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0012_application_decision"
down_revision = "0011_invitation_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("job_application", sa.Column("decision_note", sa.Text(), nullable=True))
    op.add_column(
        "job_application",
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "job_application",
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_job_application_decided_by",
        "job_application",
        "app_user",
        ["decided_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_job_application_decided_by",
        "job_application",
        ["decided_by"],
    )


def downgrade() -> None:
    op.drop_index("idx_job_application_decided_by", table_name="job_application")
    op.drop_constraint(
        "fk_job_application_decided_by",
        "job_application",
        type_="foreignkey",
    )
    op.drop_column("job_application", "decided_at")
    op.drop_column("job_application", "decided_by")
    op.drop_column("job_application", "decision_note")
