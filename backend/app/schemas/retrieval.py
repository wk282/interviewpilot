import uuid
from typing import Literal

from pydantic import BaseModel, Field


RetrievalProfile = Literal[
    "VECTOR",
    "VECTOR_TRIGRAM",
    "VECTOR_RERANK",
    "VECTOR_TRIGRAM_RERANK",
    "VECTOR_BM25",
    "VECTOR_BM25_RERANK",
    "VECTOR_TRIGRAM_BM25",
    "VECTOR_TRIGRAM_BM25_RERANK",
    "VECTOR_BM25_RRF",
    "VECTOR_BM25_RRF_RERANK",
    "VECTOR_TRIGRAM_BM25_RRF",
    "VECTOR_TRIGRAM_BM25_RRF_RERANK",
]



class RetrievalSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    profile: RetrievalProfile = "VECTOR_TRIGRAM_BM25_RERANK"
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=20)


class RetrievalSearchResult(BaseModel):
    chunk_id: uuid.UUID
    parent_chunk_id: uuid.UUID | None
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    filename: str
    child_content: str
    context: str
    fusion_score: float
    fusion_rank: int
    vector_similarity: float | None
    vector_rank: int | None = None
    trigram_similarity: float | None
    trigram_rank: int | None = None
    bm25_score: float | None
    bm25_rank: int | None = None
    rerank_score: float | None
    rerank_rank: int | None
    retrieval_sources: list[str]
    chunk_index: int
    metadata: dict


class RetrievalSearchResponse(BaseModel):
    query: str
    embedding_model: str
    retrieval_profile: RetrievalProfile
    result_count: int
    results: list[RetrievalSearchResult]
