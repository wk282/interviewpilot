"""Mark the Docker foundation schema as the Alembic baseline.

Revision ID: 0001_foundation_baseline
Revises:
"""

revision = "0001_foundation_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Docker creates the eight foundation tables from docker/init.sql before
    # Alembic applies the versioned incremental migrations.
    pass


def downgrade() -> None:
    # A baseline downgrade must not delete externally initialized tables.
    pass
