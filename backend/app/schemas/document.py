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
    ingestion_error_code: str | None
    ingestion_error_message: str | None
    created_at: datetime


class DocumentParsedContentResponse(BaseModel):
    document_id: uuid.UUID
    original_filename: str
    parser_name: str | None
    parser_version: str | None
    character_count: int
    block_count: int
    page_count: int | None
    page_kinds: list[str]
    ocr_processed_pages: list[int]
    native_block_count: int
    ocr_block_count: int
    plain_text: str
