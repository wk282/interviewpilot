import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class InterviewInvitationCreateRequest(BaseModel):
    email: EmailStr
    expires_in_days: int = Field(default=7, ge=1, le=30)
    max_access_count: int = Field(default=5, ge=1, le=20)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class InterviewInvitationResponse(BaseModel):
    id: uuid.UUID
    interview_session_id: uuid.UUID
    email: EmailStr
    status: str
    max_access_count: int
    access_count: int
    expires_at: datetime
    opened_at: datetime | None
    verified_at: datetime | None
    consented_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    invitation_token: str | None = None
    access_code: str | None = None


class InterviewInvitationCreateResponse(InterviewInvitationResponse):
    invitation_token: str
    access_code: str


class PublicInterviewInvitationResponse(BaseModel):
    invitation_id: uuid.UUID
    workspace_name: str
    job_title: str
    candidate_name: str
    masked_email: str
    scheduled_at: datetime | None
    expires_at: datetime
    status: str
    evaluation_status: str | None = None
    decision: str | None = None
    decided_at: datetime | None = None


class InterviewInvitationVerifyRequest(BaseModel):
    email: EmailStr
    access_code: str = Field(min_length=6, max_length=12)
    consent: bool

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("access_code")
    @classmethod
    def normalize_access_code(cls, value: str) -> str:
        return value.strip()


class InterviewCandidateAccessResponse(BaseModel):
    invitation_id: uuid.UUID
    interview_session_id: uuid.UUID
    access_token: str
    token_type: str = "candidate_interview"
    expires_at: datetime
