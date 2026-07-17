"""Mark the init.sql foundation schema as the Alembic baseline.

Revision ID: 0001_foundation_baseline
Revises:
"""

revision = "0001_foundation_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The eight foundation tables are created by init.sql in existing environments.
    pass


def downgrade() -> None:
    # A baseline downgrade must not delete externally initialized tables.
    pass
