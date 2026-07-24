import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


JobStatus = Literal["DRAFT", "ACTIVE", "CLOSED"]
CandidateStatus = Literal["ACTIVE", "ARCHIVED"]


class JobPositionCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    department: str | None = Field(default=None, max_length=150)
    description: str | None = None
    requirements: dict = Field(default_factory=dict)
    knowledge_base_id: uuid.UUID | None = None
    status: JobStatus = "DRAFT"


class JobPositionUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    department: str | None = Field(default=None, max_length=150)
    description: str | None = None
    requirements: dict | None = None
    knowledge_base_id: uuid.UUID | None = None
    status: JobStatus | None = None


class JobPositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    knowledge_base_id: uuid.UUID | None
    title: str
    department: str | None
    description: str | None
    requirements: dict
    status: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class CandidateProfileCreateRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    resume_document_id: uuid.UUID
    profile_data: dict = Field(default_factory=dict)


class CandidateProfileUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    resume_document_id: uuid.UUID | None = None
    profile_data: dict | None = None
    status: CandidateStatus | None = None


class CandidateProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None
    resume_knowledge_base_id: uuid.UUID | None
    resume_document_id: uuid.UUID | None
    full_name: str
    email: str | None
    phone: str | None
    source: str
    status: str
    profile_data: dict
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class InterviewSessionCreateRequest(BaseModel):
    job_position_id: uuid.UUID
    candidate_profile_id: uuid.UUID
    application_id: uuid.UUID | None = None
    interviewer_id: uuid.UUID | None = None
    scheduled_at: datetime | None = None
    configuration: dict = Field(default_factory=dict)
    reference_knowledge_base_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5)
    max_question_count: int = Field(default=10, ge=3, le=20)
    question_time_limit_minutes: int = Field(default=10, ge=0, le=60)


class InterviewSessionUpdateRequest(BaseModel):
    interviewer_id: uuid.UUID | None = None
    scheduled_at: datetime | None = None
    configuration: dict | None = None
    status: Literal["DRAFT", "CANCELLED"] | None = None


class InterviewSessionResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    job_position_id: uuid.UUID
    job_title: str
    candidate_profile_id: uuid.UUID
    candidate_name: str
    interviewer_id: uuid.UUID | None
    application_id: uuid.UUID | None
    mode: str
    status: str
    current_question_order: int
    configuration: dict
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class InterviewQuestionResponse(BaseModel):
    id: uuid.UUID
    order_no: int
    question_type: str
    content: str
    competency: str | None
    difficulty: str
    generated_by: str
    status: str
    max_score: float
    expected_points: list
    source_evidence: list
    decision_metadata: dict


class InterviewPlanResponse(BaseModel):
    id: uuid.UUID
    interview_session_id: uuid.UUID
    version: int
    status: str
    objectives: list
    sections: list
    model_name: str | None
    prompt_version: str | None
    generated_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    questions: list[InterviewQuestionResponse]


class AIStageMetricsResponse(BaseModel):
    sample_count: int
    average_latency_ms: int
    p50_latency_ms: int
    p95_latency_ms: int
    max_latency_ms: int


class InterviewObservabilityResponse(BaseModel):
    interview_id: uuid.UUID
    question_count: int
    measured_turn_count: int
    total_tokens: int
    fallback_event_count: int
    fallback_turn_count: int
    fallback_turn_rate: float
    bottleneck_stage: str | None
    stage_metrics: dict[str, AIStageMetricsResponse]
    route_counts: dict[str, int]


class InterviewRuntimeQuestionResponse(BaseModel):
    id: uuid.UUID
    order_no: int
    question_type: str
    content: str
    competency: str | None
    difficulty: str
    generated_by: str
    asked_at: datetime | None


class InterviewTurnCritiqueResponse(BaseModel):
    id: uuid.UUID
    interview_question_id: uuid.UUID
    score: float
    strengths: list[str]
    knowledge_gaps: list[str]
    answer_evidence: list[str]
    next_action: str
    difficulty_delta: int
    confidence: float
    reason: str
    decision_source: str
    model_name: str | None
    prompt_version: str
    created_at: datetime


class InterviewPlanRevisionResponse(BaseModel):
    id: uuid.UUID
    source_critique_id: uuid.UUID
    version: int
    action: str
    target_competency: str | None
    target_difficulty: str | None
    covered_competencies: list[str]
    priority_competencies: list[str]
    knowledge_gaps: list[str]
    rationale: str
    workflow_trace: list[dict]
    before_snapshot: dict
    after_snapshot: dict
    change_set: dict
    remaining_question_budget: int
    competency_budget: dict[str, int]
    created_at: datetime


class InterviewRuntimeResponse(BaseModel):
    interview_id: uuid.UUID
    status: str
    current_question: InterviewRuntimeQuestionResponse | None
    completed_question_count: int
    total_question_count: int
    max_question_count: int
    question_time_limit_seconds: int | None
    started_at: datetime | None
    completed_at: datetime | None
    follow_up_generated: bool = False
    question_timed_out: bool = False
    last_turn_feedback: InterviewTurnCritiqueResponse | None = None
    adaptive_plan_version: int | None = None
    evaluation_status: str | None = None
    decision: str | None = None
    decided_at: datetime | None = None


class InterviewAnswerSubmitRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    duration_seconds: int | None = Field(default=None, ge=0)
    client_metadata: dict = Field(default_factory=dict)


class InterviewEvaluationResponse(BaseModel):
    id: uuid.UUID
    interview_session_id: uuid.UUID
    status: str
    overall_score: float | None
    dimension_scores: dict
    strengths: list
    weaknesses: list
    evidence: list
    report_text: str | None
    recommendation: str | None
    model_name: str | None
    prompt_version: str | None
    error_message: str | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    turn_critiques: list[InterviewTurnCritiqueResponse] = Field(default_factory=list)
    plan_revisions: list[InterviewPlanRevisionResponse] = Field(default_factory=list)


class InterviewQualityAuditResponse(BaseModel):
    id: uuid.UUID
    interview_session_id: uuid.UUID
    audit_version: str
    passed: bool
    metrics: dict
    quality_gates: list[dict]
    warnings: list[str]
    generated_at: datetime
    created_at: datetime
