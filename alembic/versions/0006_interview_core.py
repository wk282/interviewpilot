"""Add interview domain core tables.

Revision ID: 0006_interview_core
Revises: 0005_chunk_trigram_search
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0006_interview_core"
down_revision = "0005_chunk_trigram_search"
branch_labels = None
depends_on = None


def timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "job_position",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("department", sa.String(length=150), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("requirements", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="DRAFT", nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'CLOSED')", name="job_position_status"),
        sa.CheckConstraint("LENGTH(BTRIM(title)) > 0", name="job_position_title"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_base.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "workspace_id", name="job_position_id_workspace"),
    )
    op.create_index("idx_job_position_workspace_status", "job_position", ["workspace_id", "status"])
    op.create_index("idx_job_position_created_by", "job_position", ["created_by"])
    op.create_index("idx_job_position_knowledge_base", "job_position", ["knowledge_base_id"])

    op.create_table(
        "candidate_profile",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resume_knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="ACTIVE", nullable=False),
        sa.Column("profile_data", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint("source IN ('PERSONAL_ACCOUNT', 'ENTERPRISE_IMPORT')", name="candidate_profile_source"),
        sa.CheckConstraint("status IN ('ACTIVE', 'ARCHIVED')", name="candidate_profile_status"),
        sa.CheckConstraint("LENGTH(BTRIM(full_name)) > 0", name="candidate_profile_name"),
        sa.CheckConstraint(
            "source <> 'PERSONAL_ACCOUNT' OR user_id IS NOT NULL",
            name="candidate_profile_personal_user",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resume_knowledge_base_id"], ["knowledge_base.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "user_id", name="candidate_profile_workspace_user"),
        sa.UniqueConstraint("id", "workspace_id", name="candidate_profile_id_workspace"),
    )
    op.create_index("idx_candidate_profile_workspace_status", "candidate_profile", ["workspace_id", "status"])
    op.create_index("idx_candidate_profile_email", "candidate_profile", ["workspace_id", "email"])
    op.create_index("idx_candidate_profile_resume_kb", "candidate_profile", ["resume_knowledge_base_id"])

    op.create_table(
        "interview_session",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_position_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("interviewer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="DRAFT", nullable=False),
        sa.Column("current_question_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("configuration", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint("mode IN ('MOCK', 'ENTERPRISE')", name="interview_session_mode"),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PLANNING', 'READY', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', 'FAILED')",
            name="interview_session_status",
        ),
        sa.CheckConstraint("current_question_order >= 0", name="interview_session_question_order"),
        sa.CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="interview_session_time",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["job_position_id", "workspace_id"],
            ["job_position.id", "job_position.workspace_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_profile_id", "workspace_id"],
            ["candidate_profile.id", "candidate_profile.workspace_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["interviewer_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_interview_session_workspace_status", "interview_session", ["workspace_id", "status"])
    op.create_index("idx_interview_session_candidate", "interview_session", ["candidate_profile_id", "created_at"])
    op.create_index("idx_interview_session_job", "interview_session", ["job_position_id", "created_at"])
    op.create_index("idx_interview_session_interviewer", "interview_session", ["interviewer_id"])

    op.create_table(
        "interview_plan",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="DRAFT", nullable=False),
        sa.Column("objectives", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("sections", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=50), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        *timestamp_columns(),
        sa.CheckConstraint("version > 0", name="interview_plan_version"),
        sa.CheckConstraint("status IN ('DRAFT', 'READY', 'FAILED')", name="interview_plan_status"),
        sa.ForeignKeyConstraint(["interview_session_id"], ["interview_session.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("interview_session_id", "version", name="interview_plan_session_version"),
        sa.UniqueConstraint("id", "interview_session_id", name="interview_plan_id_session"),
    )
    op.create_index("idx_interview_plan_session_status", "interview_plan", ["interview_session_id", "status"])

    op.create_table(
        "interview_question",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("interview_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parent_question_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("order_no", sa.Integer(), nullable=False),
        sa.Column("question_type", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("competency", sa.String(length=150), nullable=True),
        sa.Column("difficulty", sa.String(length=20), nullable=False),
        sa.Column("generated_by", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("max_score", sa.Numeric(precision=5, scale=2), server_default="10", nullable=False),
        sa.Column("expected_points", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("source_evidence", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("order_no > 0", name="interview_question_order"),
        sa.CheckConstraint(
            "question_type IN ('INTRODUCTION', 'TECHNICAL', 'PROJECT', 'SYSTEM_DESIGN', 'BEHAVIORAL', 'FOLLOW_UP', 'CANDIDATE_QUESTION')",
            name="interview_question_type",
        ),
        sa.CheckConstraint("difficulty IN ('EASY', 'MEDIUM', 'HARD')", name="interview_question_difficulty"),
        sa.CheckConstraint("generated_by IN ('PLAN', 'FOLLOW_UP', 'HUMAN')", name="interview_question_generated_by"),
        sa.CheckConstraint("status IN ('PENDING', 'ASKED', 'ANSWERED', 'SKIPPED')", name="interview_question_status"),
        sa.CheckConstraint("max_score > 0", name="interview_question_max_score"),
        sa.ForeignKeyConstraint(["interview_session_id"], ["interview_session.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["interview_plan_id", "interview_session_id"],
            ["interview_plan.id", "interview_plan.interview_session_id"],
        ),
        sa.ForeignKeyConstraint(
            ["parent_question_id", "interview_session_id"],
            ["interview_question.id", "interview_question.interview_session_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("interview_session_id", "order_no", name="interview_question_session_order"),
        sa.UniqueConstraint("id", "interview_session_id", name="interview_question_id_session"),
    )
    op.create_index("idx_interview_question_session_status", "interview_question", ["interview_session_id", "status"])
    op.create_index("idx_interview_question_parent", "interview_question", ["parent_question_id"])
    op.create_index("idx_interview_question_plan", "interview_question", ["interview_plan_id"])

    op.create_table(
        "interview_answer",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("interview_question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("input_type", sa.String(length=20), server_default="TEXT", nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("client_metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("input_type IN ('TEXT', 'VOICE')", name="interview_answer_input_type"),
        sa.CheckConstraint("duration_seconds IS NULL OR duration_seconds >= 0", name="interview_answer_duration"),
        sa.ForeignKeyConstraint(["interview_session_id"], ["interview_session.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["interview_question_id", "interview_session_id"],
            ["interview_question.id", "interview_question.interview_session_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("interview_question_id", name="interview_answer_question"),
    )
    op.create_index("idx_interview_answer_session_submitted", "interview_answer", ["interview_session_id", "submitted_at"])

    op.create_table(
        "interview_evaluation",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("overall_score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("dimension_scores", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("strengths", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("weaknesses", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("report_text", sa.Text(), nullable=True),
        sa.Column("recommendation", sa.String(length=30), nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        *timestamp_columns(),
        sa.CheckConstraint(
            "status IN ('PENDING', 'GENERATING', 'COMPLETED', 'FAILED')",
            name="interview_evaluation_status",
        ),
        sa.CheckConstraint(
            "overall_score IS NULL OR (overall_score >= 0 AND overall_score <= 100)",
            name="interview_evaluation_score",
        ),
        sa.CheckConstraint(
            "recommendation IS NULL OR recommendation IN ('STRONG_HIRE', 'HIRE', 'HOLD', 'NO_HIRE', 'NOT_APPLICABLE')",
            name="interview_evaluation_recommendation",
        ),
        sa.ForeignKeyConstraint(["interview_session_id"], ["interview_session.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("interview_session_id", name="interview_evaluation_session"),
    )
    op.create_index("idx_interview_evaluation_status", "interview_evaluation", ["status", "created_at"])
    op.create_index("idx_interview_evaluation_reviewed_by", "interview_evaluation", ["reviewed_by"])


def downgrade() -> None:
    op.drop_table("interview_evaluation")
    op.drop_table("interview_answer")
    op.drop_table("interview_question")
    op.drop_table("interview_plan")
    op.drop_table("interview_session")
    op.drop_table("candidate_profile")
    op.drop_table("job_position")
