import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    and_,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin

class JobPosition(TimestampMixin, Base):
    __tablename__ = "job_position"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'CLOSED')", name="job_position_status"),
        CheckConstraint("LENGTH(BTRIM(title)) > 0", name="job_position_title"),
        Index("idx_job_position_workspace_status", "workspace_id", "status"),
        Index("idx_job_position_created_by", "created_by"),
        Index("idx_job_position_knowledge_base", "knowledge_base_id"),
        UniqueConstraint("id", "workspace_id", name="job_position_id_workspace"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4()
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False
    )
    knowledge_base_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_base.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[str | None] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    requirements: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="DRAFT")
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False
    )

    sessions: Mapped[list["InterviewSession"]] = relationship(
        back_populates="job_position",
        cascade="all, delete-orphan",
        primaryjoin=lambda: and_(
            JobPosition.id == foreign(InterviewSession.job_position_id),
            JobPosition.workspace_id == InterviewSession.workspace_id,
        ),
    )


class CandidateProfile(TimestampMixin, Base):
    __tablename__ = "candidate_profile"
    __table_args__ = (
        CheckConstraint(
            "source IN ('PERSONAL_ACCOUNT', 'ENTERPRISE_IMPORT')",
            name="candidate_profile_source",
        ),
        CheckConstraint("status IN ('ACTIVE', 'ARCHIVED')", name="candidate_profile_status"),
        CheckConstraint("LENGTH(BTRIM(full_name)) > 0", name="candidate_profile_name"),
        CheckConstraint(
            "source <> 'PERSONAL_ACCOUNT' OR user_id IS NOT NULL",
            name="candidate_profile_personal_user",
        ),
        UniqueConstraint("workspace_id", "user_id", name="candidate_profile_workspace_user"),
        UniqueConstraint("id", "workspace_id", name="candidate_profile_id_workspace"),
        Index("idx_candidate_profile_workspace_status", "workspace_id", "status"),
        Index("idx_candidate_profile_email", "workspace_id", "email"),
        Index("idx_candidate_profile_resume_kb", "resume_knowledge_base_id"),
        Index("idx_candidate_profile_resume_document", "resume_document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4()
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    resume_knowledge_base_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_base.id", ondelete="SET NULL")
    )
    resume_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL")
    )
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ACTIVE")
    profile_data: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False
    )

    sessions: Mapped[list["InterviewSession"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
        primaryjoin=lambda: and_(
            CandidateProfile.id == foreign(InterviewSession.candidate_profile_id),
            CandidateProfile.workspace_id == InterviewSession.workspace_id,
        ),
    )


class InterviewSession(TimestampMixin, Base):
    __tablename__ = "interview_session"
    __table_args__ = (
        CheckConstraint("mode IN ('MOCK', 'ENTERPRISE')", name="interview_session_mode"),
        CheckConstraint(
            "status IN ('DRAFT', 'PLANNING', 'READY', 'IN_PROGRESS', 'COMPLETED', "
            "'CANCELLED', 'FAILED')",
            name="interview_session_status",
        ),
        CheckConstraint("current_question_order >= 0", name="interview_session_question_order"),
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="interview_session_time",
        ),
        ForeignKeyConstraint(
            ["job_position_id", "workspace_id"],
            ["job_position.id", "job_position.workspace_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["candidate_profile_id", "workspace_id"],
            ["candidate_profile.id", "candidate_profile.workspace_id"],
            ondelete="CASCADE",
        ),
        Index("idx_interview_session_workspace_status", "workspace_id", "status"),
        Index("idx_interview_session_candidate", "candidate_profile_id", "created_at"),
        Index("idx_interview_session_job", "job_position_id", "created_at"),
        Index("idx_interview_session_interviewer", "interviewer_id"),
        Index("idx_interview_session_application", "application_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4()
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False
    )
    job_position_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    candidate_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    interviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_application.id", ondelete="SET NULL")
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="DRAFT")
    current_question_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    configuration: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False
    )

    job_position: Mapped[JobPosition] = relationship(
        back_populates="sessions",
        primaryjoin=lambda: and_(
            JobPosition.id == foreign(InterviewSession.job_position_id),
            JobPosition.workspace_id == InterviewSession.workspace_id,
        ),
    )
    candidate: Mapped[CandidateProfile] = relationship(
        back_populates="sessions",
        primaryjoin=lambda: and_(
            CandidateProfile.id == foreign(InterviewSession.candidate_profile_id),
            CandidateProfile.workspace_id == InterviewSession.workspace_id,
        ),
    )
    plans: Mapped[list["InterviewPlan"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    questions: Mapped[list["InterviewQuestion"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        foreign_keys="InterviewQuestion.interview_session_id",
    )
    evaluation: Mapped["InterviewEvaluation | None"] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )


class InterviewPlan(TimestampMixin, Base):
    __tablename__ = "interview_plan"
    __table_args__ = (
        CheckConstraint("version > 0", name="interview_plan_version"),
        CheckConstraint("status IN ('DRAFT', 'READY', 'FAILED')", name="interview_plan_status"),
        UniqueConstraint("interview_session_id", "version", name="interview_plan_session_version"),
        UniqueConstraint("id", "interview_session_id", name="interview_plan_id_session"),
        Index("idx_interview_plan_session_status", "interview_session_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4()
    )
    interview_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_session.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="DRAFT")
    objectives: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    sections: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    model_name: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    session: Mapped[InterviewSession] = relationship(back_populates="plans")
    questions: Mapped[list["InterviewQuestion"]] = relationship(
        back_populates="plan", foreign_keys="InterviewQuestion.interview_plan_id"
    )


class InterviewQuestion(Base):
    __tablename__ = "interview_question"
    __table_args__ = (
        CheckConstraint("order_no > 0", name="interview_question_order"),
        CheckConstraint(
            "question_type IN ('INTRODUCTION', 'TECHNICAL', 'PROJECT', 'SYSTEM_DESIGN', "
            "'BEHAVIORAL', 'FOLLOW_UP', 'CANDIDATE_QUESTION')",
            name="interview_question_type",
        ),
        CheckConstraint("difficulty IN ('EASY', 'MEDIUM', 'HARD')", name="interview_question_difficulty"),
        CheckConstraint("generated_by IN ('PLAN', 'FOLLOW_UP', 'HUMAN')", name="interview_question_generated_by"),
        CheckConstraint("status IN ('PENDING', 'ASKED', 'ANSWERED', 'SKIPPED')", name="interview_question_status"),
        CheckConstraint("max_score > 0", name="interview_question_max_score"),
        ForeignKeyConstraint(
            ["interview_plan_id", "interview_session_id"],
            ["interview_plan.id", "interview_plan.interview_session_id"],
        ),
        ForeignKeyConstraint(
            ["parent_question_id", "interview_session_id"],
            ["interview_question.id", "interview_question.interview_session_id"],
        ),
        UniqueConstraint("interview_session_id", "order_no", name="interview_question_session_order"),
        UniqueConstraint("id", "interview_session_id", name="interview_question_id_session"),
        Index("idx_interview_question_session_status", "interview_session_id", "status"),
        Index("idx_interview_question_parent", "parent_question_id"),
        Index("idx_interview_question_plan", "interview_plan_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4()
    )
    interview_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_session.id", ondelete="CASCADE"), nullable=False
    )
    interview_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True)
    )
    parent_question_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True)
    )
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)
    question_type: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    competency: Mapped[str | None] = mapped_column(String(150))
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    generated_by: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PENDING")
    max_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default="10"
    )
    expected_points: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    source_evidence: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    decision_metadata: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    asked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped[InterviewSession] = relationship(
        back_populates="questions", foreign_keys=[interview_session_id]
    )
    plan: Mapped[InterviewPlan | None] = relationship(
        back_populates="questions", foreign_keys=[interview_plan_id]
    )
    answer: Mapped["InterviewAnswer | None"] = relationship(
        back_populates="question", cascade="all, delete-orphan", uselist=False
    )


class InterviewAnswer(Base):
    __tablename__ = "interview_answer"
    __table_args__ = (
        CheckConstraint("input_type IN ('TEXT', 'VOICE')", name="interview_answer_input_type"),
        CheckConstraint("duration_seconds IS NULL OR duration_seconds >= 0", name="interview_answer_duration"),
        ForeignKeyConstraint(
            ["interview_question_id", "interview_session_id"],
            ["interview_question.id", "interview_question.interview_session_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("interview_question_id", name="interview_answer_question"),
        Index("idx_interview_answer_session_submitted", "interview_session_id", "submitted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4()
    )
    interview_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_session.id", ondelete="CASCADE"), nullable=False
    )
    interview_question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    input_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="TEXT")
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    client_metadata: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    question: Mapped[InterviewQuestion] = relationship(back_populates="answer")


class InterviewEvaluation(TimestampMixin, Base):
    __tablename__ = "interview_evaluation"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'GENERATING', 'COMPLETED', 'FAILED')",
            name="interview_evaluation_status",
        ),
        CheckConstraint(
            "overall_score IS NULL OR (overall_score >= 0 AND overall_score <= 100)",
            name="interview_evaluation_score",
        ),
        CheckConstraint(
            "recommendation IS NULL OR recommendation IN "
            "('STRONG_HIRE', 'HIRE', 'HOLD', 'NO_HIRE', 'NOT_APPLICABLE')",
            name="interview_evaluation_recommendation",
        ),
        UniqueConstraint("interview_session_id", name="interview_evaluation_session"),
        Index("idx_interview_evaluation_status", "status", "created_at"),
        Index("idx_interview_evaluation_reviewed_by", "reviewed_by"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4()
    )
    interview_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_session.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PENDING")
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    dimension_scores: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    strengths: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    weaknesses: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    evidence: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    report_text: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(String(30))
    model_name: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    session: Mapped[InterviewSession] = relationship(back_populates="evaluation")
