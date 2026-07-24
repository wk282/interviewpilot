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
    trigram_similarity: float | None
    bm25_score: float | None
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


def compute_rrf_score(
    candidate_ids: list[uuid.UUID],
    vector_ranks: dict[uuid.UUID, int],
    bm25_ranks: dict[uuid.UUID, int],
    k: int = 60,
) -> dict[uuid.UUID, float]:
    """标准 RRF (Reciprocal Rank Fusion) 融合算法"""
    rrf_scores = {}
    for chunk_id in candidate_ids:
        score = 0.0
        if chunk_id in vector_ranks:
            score += 1.0 / (k + vector_ranks[chunk_id])
        if chunk_id in bm25_ranks:
            score += 1.0 / (k + bm25_ranks[chunk_id])
        rrf_scores[chunk_id] = score
    return rrf_scores
