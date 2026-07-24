import asyncio
import uuid
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, status
from openai import AsyncOpenAI
from sqlalchemy import Float, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.logger import logger
from app.core.permissions import require_workspace_role
from app.db.models.chunk import DocumentChunk
from app.db.models.document import Document, DocumentVersion
from app.db.models.knowledge_base import KnowledgeBase
from app.db.models.user import AppUser
from app.db.session import get_db_session
from app.schemas.retrieval import (
    RetrievalSearchRequest,
    RetrievalSearchResponse,
    RetrievalSearchResult,
)
from app.services.bm25_store import OpenSearchBM25Store
from app.services.reranker import ZhipuReranker
from app.services.ai_concurrency import ai_concurrency_slot


router = APIRouter(
    prefix="/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}/retrieval",
    tags=["知识库检索"],
)

ALL_ROLES = {"OWNER", "ADMIN", "HR", "INTERVIEWER", "VIEWER"}
MANAGER_ROLES = {"OWNER", "ADMIN"}
MIN_TRIGRAM_SIMILARITY = 0.1
FUSION_WEIGHTS = {"VECTOR": 0.50, "TRIGRAM": 0.10, "BM25": 0.40}
TRIGRAM_PROFILES = {
    "VECTOR_TRIGRAM",
    "VECTOR_TRIGRAM_RERANK",
    "VECTOR_TRIGRAM_BM25",
    "VECTOR_TRIGRAM_BM25_RERANK",
    "VECTOR_TRIGRAM_BM25_RRF",
    "VECTOR_TRIGRAM_BM25_RRF_RERANK",
}
BM25_PROFILES = {
    "VECTOR_BM25",
    "VECTOR_BM25_RERANK",
    "VECTOR_TRIGRAM_BM25",
    "VECTOR_TRIGRAM_BM25_RERANK",
    "VECTOR_BM25_RRF",
    "VECTOR_BM25_RRF_RERANK",
    "VECTOR_TRIGRAM_BM25_RRF",
    "VECTOR_TRIGRAM_BM25_RRF_RERANK",
}
RERANK_PROFILES = {
    "VECTOR_RERANK",
    "VECTOR_TRIGRAM_RERANK",
    "VECTOR_BM25_RERANK",
    "VECTOR_TRIGRAM_BM25_RERANK",
    "VECTOR_BM25_RRF_RERANK",
    "VECTOR_TRIGRAM_BM25_RRF_RERANK",
}
RRF_PROFILES = {
    "VECTOR_BM25_RRF",
    "VECTOR_BM25_RRF_RERANK",
    "VECTOR_TRIGRAM_BM25_RRF",
    "VECTOR_TRIGRAM_BM25_RRF_RERANK",
}



@dataclass
class CandidateScore:
    fusion_score: float = 0.0
    vector_similarity: float | None = None
    trigram_similarity: float | None = None
    bm25_score: float | None = None


async def require_accessible_knowledge_base(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    user: AppUser,
) -> None:
    _, membership = await require_workspace_role(
        session, workspace_id, user.id, ALL_ROLES
    )
    knowledge_base = await session.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.workspace_id == workspace_id,
        )
    )
    if knowledge_base is None or (
        knowledge_base.visibility == "PRIVATE"
        and membership.role not in MANAGER_ROLES
        and knowledge_base.created_by != user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在",
        )


async def create_query_embedding(query: str) -> list[float]:
    try:
        async with AsyncOpenAI(
            api_key=settings.EMBEDDING_API_KEY or settings.OPENAI_API_KEY,
            base_url=settings.EMBEDDING_BASE_URL or settings.OPENAI_BASE_URL,
        ) as client:
            async with ai_concurrency_slot(
                "query_embedding",
                settings.EMBEDDING_MODEL_NAME,
            ):
                response = await client.embeddings.create(
                    model=settings.EMBEDDING_MODEL_NAME,
                    input=[query],
                    dimensions=settings.EMBEDDING_DIMENSIONS,
                )
    except Exception as error:
        logger.warning(f"Failed to embed retrieval query: {error}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="查询向量生成失败，请稍后重试",
        ) from error

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Embedding 服务未返回查询向量",
        )
    embedding = response.data[0].embedding
    if len(embedding) != settings.EMBEDDING_DIMENSIONS:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Embedding 服务返回的向量维度不正确",
        )
    return embedding


def normalize_scores(
    scores: dict[uuid.UUID, float],
    candidate_ids: list[uuid.UUID],
) -> dict[uuid.UUID, float]:
    if not candidate_ids:
        return {}
    values = [scores.get(chunk_id, 0.0) for chunk_id in candidate_ids]
    minimum = min(values)
    maximum = max(values)
    if maximum - minimum < 1e-9:
        normalized_value = 1.0 if maximum > 0 else 0.0
        return {chunk_id: normalized_value for chunk_id in candidate_ids}
    return {
        chunk_id: (scores.get(chunk_id, 0.0) - minimum) / (maximum - minimum)
        for chunk_id in candidate_ids
    }


def trigram_similarity_from_distance(distance: float) -> float:
    similarity = max(0.0, min(1.0, 1.0 - distance))
    return similarity if similarity >= MIN_TRIGRAM_SIMILARITY else 0.0


async def retrieve_knowledge_base(
    workspace_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    request: RetrievalSearchRequest,
    current_user: AppUser,
    session: AsyncSession,
    query_embedding: list[float] | None = None,
) -> RetrievalSearchResponse:
    await require_accessible_knowledge_base(
        session, workspace_id, knowledge_base_id, current_user
    )

    query = request.query.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="检索问题不能为空",
        )
    if query_embedding is None:
        query_embedding = await create_query_embedding(query)
    elif len(query_embedding) != settings.EMBEDDING_DIMENSIONS:
        raise ValueError("Query embedding dimension does not match configuration")
    document_filters = (
        [Document.id.in_(request.document_ids)] if request.document_ids else []
    )

    candidate_pool_size = min(request.top_k * 4, 80)
    vector_distance = DocumentChunk.embedding.cosine_distance(query_embedding).label(
        "vector_distance"
    )
    vector_rows = (
        await session.execute(
            select(
                DocumentChunk.id,
                vector_distance,
            )
            .join(
                DocumentVersion,
                DocumentVersion.id == DocumentChunk.document_version_id,
            )
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                DocumentChunk.workspace_id == workspace_id,
                DocumentChunk.knowledge_base_id == knowledge_base_id,
                DocumentChunk.chunk_type == "CHILD",
                DocumentChunk.embedding.is_not(None),
                DocumentChunk.embedding_model == settings.EMBEDDING_MODEL_NAME,
                Document.status == "READY",
                DocumentVersion.status == "READY",
                *document_filters,
            )
            .order_by(vector_distance)
            .limit(candidate_pool_size)
        )
    ).all()

    trigram_rows = []
    if request.profile in TRIGRAM_PROFILES:
        trigram_distance = DocumentChunk.content.op(
            "<->>", return_type=Float
        )(query).label("trigram_distance")
        trigram_rows = (
            await session.execute(
                select(DocumentChunk.id, trigram_distance)
                .join(
                    DocumentVersion,
                    DocumentVersion.id == DocumentChunk.document_version_id,
                )
                .join(Document, Document.id == DocumentVersion.document_id)
                .where(
                    DocumentChunk.workspace_id == workspace_id,
                    DocumentChunk.knowledge_base_id == knowledge_base_id,
                    DocumentChunk.chunk_type == "CHILD",
                    Document.status == "READY",
                    DocumentVersion.status == "READY",
                    *document_filters,
                )
                .order_by(trigram_distance)
                .limit(candidate_pool_size)
            )
        ).all()

    bm25_rows: list[tuple[uuid.UUID, float]] = []
    if request.profile in BM25_PROFILES:
        if not settings.OPENSEARCH_URL:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="BM25 检索尚未配置 OpenSearch",
            )
        try:
            bm25_rows = await asyncio.to_thread(
                OpenSearchBM25Store().search,
                query,
                workspace_id,
                knowledge_base_id,
                candidate_pool_size,
                request.document_ids,
            )
        except Exception as error:
            logger.warning(f"BM25 retrieval failed: {error}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="BM25 检索服务不可用",
            ) from error

    trigram_candidate_ids = [
        chunk_id
        for chunk_id, chunk_distance in trigram_rows
        if trigram_similarity_from_distance(float(chunk_distance)) > 0.0
    ]
    candidate_ids = list(
        dict.fromkeys(
            [chunk_id for chunk_id, _ in vector_rows]
            + trigram_candidate_ids
            + [chunk_id for chunk_id, _ in bm25_rows]
        )
    )

    parent_chunk = aliased(DocumentChunk)
    detail_rows = []
    if candidate_ids:
        detail_rows = (
            await session.execute(
                select(
                    DocumentChunk,
                    parent_chunk.content.label("parent_content"),
                    Document.id.label("document_id"),
                    DocumentVersion.original_filename,
                )
                .join(
                    DocumentVersion,
                    DocumentVersion.id == DocumentChunk.document_version_id,
                )
                .join(Document, Document.id == DocumentVersion.document_id)
                .outerjoin(parent_chunk, parent_chunk.id == DocumentChunk.parent_chunk_id)
                .where(
                    DocumentChunk.id.in_(candidate_ids),
                    DocumentChunk.embedding.is_not(None),
                    DocumentChunk.embedding_model == settings.EMBEDDING_MODEL_NAME,
                    Document.status == "READY",
                    DocumentVersion.status == "READY",
                    *document_filters,
                )
            )
        ).all()
    details_by_id = {
        chunk.id: (chunk, parent_content, document_id, original_filename)
        for chunk, parent_content, document_id, original_filename in detail_rows
    }
    valid_ids = [chunk_id for chunk_id in candidate_ids if chunk_id in details_by_id]

    vector_rescore_distance = DocumentChunk.embedding.cosine_distance(
        query_embedding
    ).label("vector_rescore_distance")
    vector_rescore_rows = []
    if valid_ids:
        vector_rescore_rows = (
            await session.execute(
                select(DocumentChunk.id, vector_rescore_distance).where(
                    DocumentChunk.id.in_(valid_ids)
                )
            )
        ).all()
    vector_scores = {
        chunk_id: max(0.0, min(1.0, 1.0 - float(chunk_distance)))
        for chunk_id, chunk_distance in vector_rescore_rows
    }

    trigram_scores: dict[uuid.UUID, float] = {}
    if request.profile in TRIGRAM_PROFILES and valid_ids:
        trigram_rescore_distance = DocumentChunk.content.op(
            "<->>", return_type=Float
        )(query).label("trigram_rescore_distance")
        trigram_rescore_rows = (
            await session.execute(
                select(DocumentChunk.id, trigram_rescore_distance).where(
                    DocumentChunk.id.in_(valid_ids)
                )
            )
        ).all()
        trigram_scores = {
            chunk_id: trigram_similarity_from_distance(float(chunk_distance))
            for chunk_id, chunk_distance in trigram_rescore_rows
        }

    bm25_scores: dict[uuid.UUID, float] = {}
    if request.profile in BM25_PROFILES and valid_ids:
        try:
            bm25_scores = await asyncio.to_thread(
                OpenSearchBM25Store().score_candidates,
                query,
                workspace_id,
                knowledge_base_id,
                valid_ids,
            )
        except Exception as error:
            logger.warning(f"BM25 candidate scoring failed: {error}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="BM25 候选评分失败",
            ) from error

    normalized_scores = {"VECTOR": normalize_scores(vector_scores, valid_ids)}
    active_channels = ["VECTOR"]
    if request.profile in TRIGRAM_PROFILES:
        normalized_scores["TRIGRAM"] = normalize_scores(trigram_scores, valid_ids)
        active_channels.append("TRIGRAM")
    if request.profile in BM25_PROFILES:
        normalized_scores["BM25"] = normalize_scores(bm25_scores, valid_ids)
        active_channels.append("BM25")

    # 【判定融合策略】：若 Profile 显式指定 RRF 则走 RRF 排名倒数求和，否则走 Min-Max 加权求和
    is_rrf = request.profile in RRF_PROFILES
    if is_rrf:
        k_rrf = 60
        channel_ranks: dict[str, dict[uuid.UUID, int]] = {}
        if "VECTOR" in active_channels:
            v_order = sorted(valid_ids, key=lambda cid: vector_scores.get(cid, 0.0), reverse=True)
            channel_ranks["VECTOR"] = {cid: rank for rank, cid in enumerate(v_order, start=1)}
        if "TRIGRAM" in active_channels:
            t_order = sorted(valid_ids, key=lambda cid: trigram_scores.get(cid, 0.0), reverse=True)
            channel_ranks["TRIGRAM"] = {cid: rank for rank, cid in enumerate(t_order, start=1)}
        if "BM25" in active_channels:
            b_order = sorted(valid_ids, key=lambda cid: bm25_scores.get(cid, 0.0), reverse=True)
            channel_ranks["BM25"] = {cid: rank for rank, cid in enumerate(b_order, start=1)}
    else:
        total_weight = sum(FUSION_WEIGHTS[channel] for channel in active_channels)

    candidate_scores: dict[uuid.UUID, CandidateScore] = {}
    for chunk_id in valid_ids:
        candidate = CandidateScore(
            vector_similarity=vector_scores.get(chunk_id, 0.0),
            trigram_similarity=(
                trigram_scores.get(chunk_id, 0.0)
                if "TRIGRAM" in active_channels
                else None
            ),
            bm25_score=(
                bm25_scores.get(chunk_id, 0.0)
                if "BM25" in active_channels
                else None
            ),
        )
        if is_rrf:
            # RRF 融合得分: RRF_score = sum(1.0 / (60 + rank))
            candidate.fusion_score = sum(
                1.0 / (k_rrf + channel_ranks[channel][chunk_id])
                for channel in active_channels
            )
        else:
            # 加权归一化得分: sum(weight * norm_score)
            candidate.fusion_score = sum(
                (FUSION_WEIGHTS[channel] / total_weight)
                * normalized_scores[channel].get(chunk_id, 0.0)
                for channel in active_channels
            )
        candidate_scores[chunk_id] = candidate


    ranked_ids = sorted(
        valid_ids,
        key=lambda chunk_id: candidate_scores[chunk_id].fusion_score,
        reverse=True,
    )
    result_pool_size = (
        min(max(request.top_k * 4, request.top_k), 20)
        if request.profile in RERANK_PROFILES
        else request.top_k
    )
    selected_ids: list[uuid.UUID] = []
    seen_parent_ids: set[uuid.UUID] = set()
    for chunk_id in ranked_ids:
        chunk = details_by_id[chunk_id][0]
        context_id = chunk.parent_chunk_id or chunk.id
        if context_id in seen_parent_ids:
            continue
        seen_parent_ids.add(context_id)
        selected_ids.append(chunk_id)
        if len(selected_ids) >= result_pool_size:
            break
    fusion_ranks = {
        chunk_id: rank for rank, chunk_id in enumerate(selected_ids, start=1)
    }

    final_ids = selected_ids[: request.top_k]
    rerank_scores: dict[uuid.UUID, float] = {}
    rerank_ranks: dict[uuid.UUID, int] = {}
    if request.profile in RERANK_PROFILES and selected_ids:
        rerank_ids = [chunk_id for chunk_id in selected_ids if chunk_id in details_by_id]
        rerank_documents = [
            details_by_id[chunk_id][0].content
            for chunk_id in rerank_ids
        ]
        async with ai_concurrency_slot(
            "retrieval_test_rerank",
            settings.RERANK_MODEL_NAME,
        ):
            rerank_results = await asyncio.to_thread(
                ZhipuReranker().rerank,
                query,
                rerank_documents,
                request.top_k,
            )
        for rerank_result in rerank_results:
            result_index = rerank_result.get("index")
            if not isinstance(result_index, int) or not 0 <= result_index < len(rerank_ids):
                continue
            chunk_id = rerank_ids[result_index]
            rerank_scores[chunk_id] = float(
                rerank_result.get("relevance_score", 0.0)
            )
        ordered_ids = sorted(
            selected_ids,
            key=lambda chunk_id: (
                rerank_scores.get(chunk_id, 0.0),
                candidate_scores[chunk_id].fusion_score,
            ),
            reverse=True,
        )
        final_ids = ordered_ids[: request.top_k]
        rerank_ranks = {
            chunk_id: rank for rank, chunk_id in enumerate(final_ids, start=1)
        }

    results: list[RetrievalSearchResult] = []
    for chunk_id in final_ids:
        details = details_by_id.get(chunk_id)
        if details is None:
            continue
        chunk, parent_content, document_id, original_filename = details
        candidate = candidate_scores[chunk_id]
        results.append(
            RetrievalSearchResult(
                chunk_id=chunk.id,
                parent_chunk_id=chunk.parent_chunk_id,
                document_id=document_id,
                document_version_id=chunk.document_version_id,
                filename=original_filename,
                child_content=chunk.content,
                context=parent_content or chunk.content,
                fusion_score=round(candidate.fusion_score, 6),
                fusion_rank=fusion_ranks[chunk_id],
                vector_similarity=(
                    round(candidate.vector_similarity, 6)
                    if candidate.vector_similarity is not None
                    else None
                ),
                trigram_similarity=(
                    round(candidate.trigram_similarity, 6)
                    if candidate.trigram_similarity is not None
                    else None
                ),
                bm25_score=(
                    round(candidate.bm25_score, 6)
                    if candidate.bm25_score is not None
                    else None
                ),
                rerank_score=(
                    round(rerank_scores.get(chunk_id, 0.0), 6)
                    if request.profile in RERANK_PROFILES
                    else None
                ),
                rerank_rank=(
                    rerank_ranks.get(chunk_id)
                    if request.profile in RERANK_PROFILES
                    else None
                ),
                retrieval_sources=[
                    source for source in active_channels
                ],
                chunk_index=chunk.chunk_index,
                metadata=chunk.chunk_metadata or {},
            )
        )
    return RetrievalSearchResponse(
        query=query,
        embedding_model=settings.EMBEDDING_MODEL_NAME,
        retrieval_profile=request.profile,
        result_count=len(results),
        results=results,
    )


@router.post("/search", response_model=RetrievalSearchResponse)
async def search_knowledge_base(
    workspace_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    request: RetrievalSearchRequest,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> RetrievalSearchResponse:
    return await retrieve_knowledge_base(
        workspace_id=workspace_id,
        knowledge_base_id=knowledge_base_id,
        request=request,
        current_user=current_user,
        session=session,
    )


@router.post("/bm25/reindex")
async def reindex_knowledge_base_bm25(
    workspace_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, int]:
    await require_workspace_role(session, workspace_id, current_user.id, MANAGER_ROLES)
    knowledge_base = await session.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.workspace_id == workspace_id,
        )
    )
    if knowledge_base is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    if not settings.OPENSEARCH_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="BM25 检索尚未配置 OpenSearch",
        )

    rows = (
        await session.execute(
            select(DocumentChunk, Document.id)
            .join(
                DocumentVersion,
                DocumentVersion.id == DocumentChunk.document_version_id,
            )
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                DocumentChunk.workspace_id == workspace_id,
                DocumentChunk.knowledge_base_id == knowledge_base_id,
                DocumentChunk.chunk_type == "CHILD",
                Document.status == "READY",
                DocumentVersion.status == "READY",
            )
        )
    ).all()
    records = [
        {
            "chunk_id": str(chunk.id),
            "workspace_id": str(chunk.workspace_id),
            "knowledge_base_id": str(chunk.knowledge_base_id),
            "document_id": str(document_id),
            "document_version_id": str(chunk.document_version_id),
            "chunk_type": chunk.chunk_type,
            "content": chunk.content,
        }
        for chunk, document_id in rows
    ]
    try:
        await asyncio.to_thread(OpenSearchBM25Store().index_chunks, records)
    except Exception as error:
        logger.warning(f"BM25 reindex failed for knowledge base {knowledge_base_id}: {error}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="BM25 索引重建失败",
        ) from error
    return {"indexed_count": len(records)}
