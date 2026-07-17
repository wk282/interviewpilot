"""Store recoverable encrypted invitation credentials.

Revision ID: 0011_invitation_credentials
Revises: 0010_recruitment_messaging
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_invitation_credentials"
down_revision = "0010_recruitment_messaging"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interview_invitation",
        sa.Column("encrypted_token", sa.Text(), nullable=True),
    )
    op.add_column(
        "interview_invitation",
        sa.Column("encrypted_access_code", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interview_invitation", "encrypted_access_code")
    op.drop_column("interview_invitation", "encrypted_token")
