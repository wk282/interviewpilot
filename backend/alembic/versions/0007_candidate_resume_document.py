"""Bind candidate profiles to a specific resume document.

Revision ID: 0007_candidate_resume_document
Revises: 0006_interview_core
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0007_candidate_resume_document"
down_revision = "0006_interview_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "candidate_profile",
        sa.Column("resume_document_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_candidate_profile_resume_document",
        "candidate_profile",
        "document",
        ["resume_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_candidate_profile_resume_document",
        "candidate_profile",
        ["resume_document_id"],
    )
    op.execute(
        """
        UPDATE candidate_profile AS candidate
        SET resume_document_id = (
            SELECT document.id
            FROM document
            WHERE document.knowledge_base_id = candidate.resume_knowledge_base_id
              AND document.status = 'READY'
            ORDER BY document.created_at DESC
            LIMIT 1
        )
        WHERE candidate.resume_knowledge_base_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("idx_candidate_profile_resume_document", table_name="candidate_profile")
    op.drop_constraint(
        "fk_candidate_profile_resume_document",
        "candidate_profile",
        type_="foreignkey",
    )
    op.drop_column("candidate_profile", "resume_document_id")
