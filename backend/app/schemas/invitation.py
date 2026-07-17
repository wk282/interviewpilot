import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


EnterpriseRole = Literal["ADMIN", "HR", "INTERVIEWER", "VIEWER"]


class InvitationCreateRequest(BaseModel):
    email: EmailStr
    role: EnterpriseRole

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class InvitationCreateResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: EnterpriseRole
    expires_at: datetime
    invitation_token: str


class InvitationInfoResponse(BaseModel):
    workspace_name: str
    email: EmailStr
    role: EnterpriseRole
    expires_at: datetime


class InvitationAcceptRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        return value.strip()


class WorkspaceMemberResponse(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
    display_name: str | None
    role: str
    joined_at: datetime
