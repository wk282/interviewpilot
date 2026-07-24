import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ApplicationStatus = Literal[
    "SUBMITTED", "REVIEWING", "INTERVIEW", "REJECTED", "WITHDRAWN", "HIRED"
]


class PublishedJobResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    workspace_name: str
    title: str
    department: str | None
    description: str | None
    requirements: dict
    created_at: datetime
    applied: bool = False


class JobApplicationCreateRequest(BaseModel):
    job_position_id: uuid.UUID
    resume_document_id: uuid.UUID
    cover_letter: str | None = Field(default=None, max_length=5000)
    consent: Literal[True]


class JobApplicationResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    workspace_name: str
    job_position_id: uuid.UUID
    job_title: str
    candidate_user_id: uuid.UUID
    candidate_profile_id: uuid.UUID
    candidate_name: str
    candidate_email: str
    candidate_phone: str | None
    candidate_profile_data: dict
    status: str
    cover_letter: str | None
    resume_document_id: uuid.UUID | None
    resume_filename: str
    resume_status: str | None
    interview_session_id: uuid.UUID | None
    interview_status: str | None
    interview_current_question_order: int | None
    interview_max_question_count: int | None
    thread_id: uuid.UUID
    submitted_at: datetime
    reviewed_at: datetime | None
    withdrawn_at: datetime | None
    decision_note: str | None
    decided_by: uuid.UUID | None
    decided_by_name: str | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApplicationStatusUpdateRequest(BaseModel):
    status: Literal["REVIEWING", "REJECTED", "HIRED"]
    decision_note: str | None = Field(default=None, max_length=5000)


class ApplicationInterviewCreateRequest(BaseModel):
    max_question_count: int = Field(default=10, ge=3, le=20)
    question_time_limit_minutes: int = Field(default=10, ge=0, le=60)
    scheduled_at: datetime | None = None
    reference_knowledge_base_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5)


class InterviewDecisionRequest(BaseModel):
    decision: Literal["HIRED", "REJECTED"]
    internal_note: str | None = Field(default=None, max_length=5000)


class InterviewDecisionResponse(BaseModel):
    interview_session_id: uuid.UUID
    application_id: uuid.UUID | None
    application_status: str | None
    decision: str | None
    internal_note: str | None
    decided_by: uuid.UUID | None
    decided_by_name: str | None
    decided_at: datetime | None


class MessageThreadResponse(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    workspace_id: uuid.UUID
    workspace_name: str
    job_title: str
    candidate_name: str
    subject: str
    application_status: str
    unread_count: int
    latest_message: str | None
    latest_message_at: datetime | None
    updated_at: datetime


class MessageResponse(BaseModel):
    id: uuid.UUID
    thread_id: uuid.UUID
    sender_type: str
    sender_user_id: uuid.UUID | None
    sender_name: str | None
    message_type: str
    interview_session_id: uuid.UUID | None
    content: str
    message_metadata: dict
    created_at: datetime


class MessageCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5000)
