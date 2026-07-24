"""Add per-turn Answer Critic and adaptive plan revisions.

Revision ID: 0014_answer_critic
Revises: 0013_interview_decisions
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0014_answer_critic"
down_revision = "0013_interview_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interview_turn_critique",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("interview_question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("interview_answer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("strengths", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("knowledge_gaps", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("answer_evidence", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("next_action", sa.String(length=30), nullable=False),
        sa.Column("difficulty_delta", sa.Integer(), server_default="0", nullable=False),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("decision_source", sa.String(length=20), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="interview_turn_critique_score"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="interview_turn_critique_confidence"),
        sa.CheckConstraint(
            "next_action IN ('FOLLOW_UP', 'INCREASE_DIFFICULTY', "
            "'DECREASE_DIFFICULTY', 'SWITCH_TOPIC', 'END_INTERVIEW')",
            name="interview_turn_critique_action",
        ),
        sa.CheckConstraint("difficulty_delta IN (-1, 0, 1)", name="interview_turn_critique_difficulty_delta"),
        sa.CheckConstraint(
            "decision_source IN ('MODEL', 'FALLBACK_RULE')",
            name="interview_turn_critique_source",
        ),
        sa.ForeignKeyConstraint(["interview_session_id"], ["interview_session.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["interview_answer_id"], ["interview_answer.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["interview_question_id"], ["interview_question.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("interview_question_id", name="interview_turn_critique_question"),
        sa.UniqueConstraint("interview_answer_id", name="interview_turn_critique_answer"),
    )
    op.create_index(
        "idx_interview_turn_critique_session_created",
        "interview_turn_critique",
        ["interview_session_id", "created_at"],
    )
    op.create_index(
        "idx_interview_turn_critique_action",
        "interview_turn_critique",
        ["next_action"],
    )

    op.create_table(
        "interview_plan_revision",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_critique_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("target_competency", sa.String(length=150), nullable=True),
        sa.Column("target_difficulty", sa.String(length=20), nullable=True),
        sa.Column("covered_competencies", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("priority_competencies", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("knowledge_gaps", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("workflow_trace", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("version > 0", name="interview_plan_revision_version"),
        sa.CheckConstraint(
            "action IN ('FOLLOW_UP', 'INCREASE_DIFFICULTY', 'DECREASE_DIFFICULTY', "
            "'SWITCH_TOPIC', 'END_INTERVIEW')",
            name="interview_plan_revision_action",
        ),
        sa.CheckConstraint(
            "target_difficulty IS NULL OR target_difficulty IN ('EASY', 'MEDIUM', 'HARD')",
            name="interview_plan_revision_difficulty",
        ),
        sa.ForeignKeyConstraint(["interview_session_id"], ["interview_session.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_critique_id"], ["interview_turn_critique.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("interview_session_id", "version", name="interview_plan_revision_session_version"),
        sa.UniqueConstraint("source_critique_id", name="interview_plan_revision_critique"),
    )
    op.create_index(
        "idx_interview_plan_revision_session_version",
        "interview_plan_revision",
        ["interview_session_id", "version"],
    )


def downgrade() -> None:
    op.drop_table("interview_plan_revision")
    op.drop_table("interview_turn_critique")
