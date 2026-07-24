import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


KnowledgeBasePurpose = Literal[
    "RESUME",
    "PERSONAL_LEARNING",
    "ENTERPRISE_QUESTION_BANK",
    "JOB_SPECIFIC",
    "SCORING_RUBRIC",
    "TECHNICAL_STANDARD",
]
KnowledgeBaseVisibility = Literal["PRIVATE", "WORKSPACE"]


class KnowledgeBaseCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    purpose: KnowledgeBasePurpose
    visibility: KnowledgeBaseVisibility = "PRIVATE"


class KnowledgeBaseUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    purpose: KnowledgeBasePurpose | None = None
    visibility: KnowledgeBaseVisibility | None = None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "KnowledgeBaseUpdateRequest":
        if self.name is None and self.purpose is None and self.visibility is None:
            raise ValueError("At least one field must be provided")
        return self


class KnowledgeBaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    purpose: str
    visibility: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
