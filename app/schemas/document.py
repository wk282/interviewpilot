import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    name: str
    status: str
    original_filename: str
    mime_type: str
    file_size: int
    file_hash: str
    version_number: int
    ingestion_job_id: uuid.UUID
    ingestion_status: str
    ingestion_stage: str | None
    ingestion_progress: int
    created_at: datetime
