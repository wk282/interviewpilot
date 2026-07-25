import asyncio
import json
import uuid
from time import perf_counter
from datetime import datetime, timezone

from openai import AsyncOpenAI
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.retrieval import create_query_embedding, retrieve_knowledge_base
from app.core.config import settings
from app.core.logger import logger
from app.db.models.interview import (
    CandidateProfile,
    InterviewPlan,
    InterviewSession,
    JobPosition,
)
from app.db.models.knowledge_base import KnowledgeBase
from app.db.models.user import AppUser
from app.schemas.retrieval import RetrievalSearchRequest
from app.services.reranker import ZhipuReranker
from app.services.ai_observability import elapsed_ms
from app.services.ai_concurrency import ai_concurrency_slot


PROMPT_VERSION = "interview-blueprint-v3"
EVIDENCE_PER_SOURCE = 5
GLOBAL_RERANK_POOL_SIZE = 20
FINAL_EVIDENCE_COUNT = 8
MAX_EVIDENCE_CONTENT_LENGTH = 2500


class GeneratedSection(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    competencies: list[str] = Field(min_length=1)
    difficulty: str = Field(min_length=1, max_length=100)
    target_question_count: int = Field(ge=1, le=20)

    @field_validator("competencies", mode="before")
    @classmethod
    def normalize_competencies(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return [normalized] if normalized else []
        return value


class GeneratedPlan(BaseModel):
    objectives: list[str] = Field(min_length=1)
    sections: list[GeneratedSection] = Field(min_length=1)

    @field_validator("objectives", mode="before")
    @classmethod
    def normalize_objectives(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return [normalized] if normalized else []
        return value

    @field_validator("sections", mode="before")
    @classmethod
    def normalize_sections(cls, value: object) -> object:
        if isinstance(value, dict):
            return [value]
        return value


def parse_json_content(content: str) -> dict:
    normalized = content.strip()
    if normalized.startswith("```"):
        normalized = normalized.removeprefix("```json").removeprefix("```")
        normalized = normalized.removesuffix("```").strip()
    return json.loads(normalized)


async def collect_evidence(
    session: AsyncSession,
    interview: InterviewSession,
    position: JobPosition,
    candidate: CandidateProfile,
    user: AppUser,
    retrieval_query: str | None = None,
    observability: dict | None = None,
) -> list[dict]:
    retrieval_sources: list[tuple[uuid.UUID, list[uuid.UUID] | None]] = []
    if candidate.resume_knowledge_base_id and candidate.resume_document_id:
        retrieval_sources.append(
            (candidate.resume_knowledge_base_id, [candidate.resume_document_id])
        )
    if position.knowledge_base_id:
        retrieval_sources.append((position.knowledge_base_id, None))
    configured_reference_ids = interview.configuration.get(
        "reference_knowledge_base_ids", []
    )
    reference_ids: list[uuid.UUID] = []
    for configured_id in configured_reference_ids:
        try:
            reference_ids.append(uuid.UUID(str(configured_id)))
        except (TypeError, ValueError):
            continue
    if reference_ids:
        validated_reference_ids = list(
            (
                await session.scalars(
                    select(KnowledgeBase.id).where(
                        KnowledgeBase.id.in_(reference_ids),
                        KnowledgeBase.workspace_id == interview.workspace_id,
                        KnowledgeBase.purpose != "RESUME",
                    )
                )
            ).all()
        )
        retrieval_sources.extend(
            (knowledge_base_id, None)
            for knowledge_base_id in validated_reference_ids
        )

    if retrieval_query is None:
        retrieval_query = "\n".join(
            part
            for part in (
                position.title,
                position.department or "",
                position.description or "",
                json.dumps(position.requirements, ensure_ascii=False),
            )
            if part
        )[:1000]
    unique_retrieval_sources = list(
        dict.fromkeys(
            (knowledge_base_id, tuple(document_ids or []))
            for knowledge_base_id, document_ids in retrieval_sources
        )
    )
    if not unique_retrieval_sources:
        return []

    embedding_started_at = perf_counter()
    try:
        query_embedding = await create_query_embedding(retrieval_query)
    except Exception as error:
        if observability is not None:
            observability["embedding"] = {
                "latency_ms": elapsed_ms(embedding_started_at),
                "model": settings.EMBEDDING_MODEL_NAME,
                "error": f"{type(error).__name__}: {error}"[:500],
            }
        logger.warning(f"Plan evidence query embedding failed: {error}")
        return []
    if observability is not None:
        observability["embedding"] = {
            "latency_ms": elapsed_ms(embedding_started_at),
            "model": settings.EMBEDDING_MODEL_NAME,
            "dimensions": settings.EMBEDDING_DIMENSIONS,
        }
        observability["retrieval_profile"] = settings.INTERVIEW_RETRIEVAL_PROFILE

    candidates: list[dict] = []
    source_observability: list[dict] = []
    for knowledge_base_id, document_ids in unique_retrieval_sources:
        source_started_at = perf_counter()
        try:
            response = await retrieve_knowledge_base(
                workspace_id=interview.workspace_id,
                knowledge_base_id=knowledge_base_id,
                request=RetrievalSearchRequest(
                    query=retrieval_query,
                    top_k=EVIDENCE_PER_SOURCE,
                    profile=settings.INTERVIEW_RETRIEVAL_PROFILE,
                    document_ids=list(document_ids) or None,
                ),
                current_user=user,
                session=session,
                query_embedding=query_embedding,
            )
        except Exception as error:
            source_observability.append(
                {
                    "knowledge_base_id": str(knowledge_base_id),
                    "latency_ms": elapsed_ms(source_started_at),
                    "result_count": 0,
                    "error": f"{type(error).__name__}: {error}"[:500],
                }
            )
            logger.warning(
                f"Plan evidence retrieval failed for knowledge base {knowledge_base_id}: {error}"
            )
            continue
        source_observability.append(
            {
                "knowledge_base_id": str(knowledge_base_id),
                "latency_ms": elapsed_ms(source_started_at),
                "result_count": len(response.results),
            }
        )
        for result in response.results:
            candidates.append(
                {
                    "knowledge_base_id": str(knowledge_base_id),
                    "chunk_id": str(result.chunk_id),
                    "document_id": str(result.document_id),
                    "filename": result.filename,
                    "content": result.context,
                    "fusion_score": result.fusion_score,
                    "fusion_rank": result.fusion_rank,
                    "vector_similarity": result.vector_similarity,
                    "vector_rank": result.vector_rank,
                    "bm25_score": result.bm25_score,
                    "bm25_rank": result.bm25_rank,
                    "retrieval_sources": result.retrieval_sources,
                    "retrieval_profile": response.retrieval_profile,
                }
            )
    if observability is not None:
        observability["knowledge_base_retrievals"] = source_observability

    deduplicated: list[dict] = []
    seen_contents: set[str] = set()
    for candidate_item in sorted(
        candidates,
        key=lambda item: item["fusion_score"],
        reverse=True,
    ):
        content_key = " ".join(candidate_item["content"].split())
        if not content_key or content_key in seen_contents:
            continue
        seen_contents.add(content_key)
        deduplicated.append(candidate_item)
        if len(deduplicated) >= GLOBAL_RERANK_POOL_SIZE:
            break

    if not deduplicated:
        return []

    selected: list[tuple[dict, float | None]] = []
    selected_indexes: set[int] = set()
    if settings.INTERVIEW_GLOBAL_RERANK_ENABLED:
        rerank_started_at = perf_counter()
        rerank_concurrency: dict = {}
        async with ai_concurrency_slot(
            "interview_evidence_rerank",
            settings.RERANK_MODEL_NAME,
            metrics_sink=rerank_concurrency,
        ):
            rerank_results = await asyncio.to_thread(
                ZhipuReranker().rerank,
                retrieval_query,
                [item["content"] for item in deduplicated],
                min(FINAL_EVIDENCE_COUNT, len(deduplicated)),
            )
        if observability is not None:
            observability["reranker"] = {
                "enabled": True,
                "latency_ms": elapsed_ms(rerank_started_at),
                "candidate_count": len(deduplicated),
                "result_count": len(rerank_results),
                **rerank_concurrency,
            }
        for rerank_result in rerank_results:
            result_index = rerank_result.get("index")
            if (
                not isinstance(result_index, int)
                or not 0 <= result_index < len(deduplicated)
                or result_index in selected_indexes
            ):
                continue
            selected_indexes.add(result_index)
            selected.append(
                (
                    deduplicated[result_index],
                    float(rerank_result.get("relevance_score", 0.0)),
                )
            )
    elif observability is not None:
        observability["reranker"] = {
            "enabled": False,
            "latency_ms": 0,
            "candidate_count": len(deduplicated),
            "result_count": 0,
        }
    for result_index, candidate_item in enumerate(deduplicated):
        if len(selected) >= FINAL_EVIDENCE_COUNT:
            break
        if result_index not in selected_indexes:
            selected.append(
                (
                    candidate_item,
                    0.0 if settings.INTERVIEW_GLOBAL_RERANK_ENABLED else None,
                )
            )

    evidence: list[dict] = []
    for rank, (candidate_item, rerank_score) in enumerate(selected, start=1):
        evidence.append(
            {
                **candidate_item,
                "evidence_id": rank,
                "content": candidate_item["content"][:MAX_EVIDENCE_CONTENT_LENGTH],
                "rerank_score": (
                    round(rerank_score, 6) if rerank_score is not None else None
                ),
                "rerank_rank": rank if rerank_score is not None else None,
            }
        )
    return evidence


async def generate_plan(
    session: AsyncSession,
    plan: InterviewPlan,
    interview: InterviewSession,
    position: JobPosition,
    candidate: CandidateProfile,
    user: AppUser,
) -> None:
    logger.info(f"Planner evidence collection started: plan_id={plan.id}")
    evidence = await collect_evidence(session, interview, position, candidate, user)
    logger.info(
        f"Planner evidence collection completed: plan_id={plan.id}, "
        f"evidence_count={len(evidence)}"
    )
    prompt_payload = {
        "mode": interview.mode,
        "position": {
            "title": position.title,
            "department": position.department,
            "description": position.description,
            "requirements": position.requirements,
        },
        "candidate": {
            "name": candidate.full_name,
            "profile_data": candidate.profile_data,
        },
        "max_question_count": int(interview.configuration.get("max_question_count", 10)),
        "retrieved_evidence": evidence,
    }
    system_prompt = (
        "你是技术面试规划器。请根据岗位、候选人和检索证据生成动态面试蓝图，不要生成具体问题。"
        "蓝图用于指导面试官逐轮出题，必须覆盖项目深挖、核心技术、系统设计或行为能力中的适用部分。"
        "不得虚构候选人经历。sections 每项应包含 name、competencies、difficulty、target_question_count。"
        "各 section 的 target_question_count 总和不能超过 max_question_count。"
        "objectives 必须是字符串数组，competencies 必须是字符串数组，sections 必须是对象数组。"
        "仅输出 JSON，禁止输出 questions。严格使用以下结构："
        '{"objectives":["评估目标"],"sections":[{"name":"能力主题",'
        '"competencies":["能力点"],"difficulty":"MEDIUM","target_question_count":3}]}。'
    )
    logger.info(f"Planner model request started: plan_id={plan.id}")
    async with AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        timeout=60.0,
        max_retries=0,
    ) as client:
        async with ai_concurrency_slot("planner", settings.LLM_MODEL):
            response = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
            )
    logger.info(f"Planner model response received: plan_id={plan.id}")
    content = response.choices[0].message.content or ""
    generated = GeneratedPlan.model_validate(parse_json_content(content))
    await session.refresh(plan, attribute_names=["status"])
    await session.refresh(interview, attribute_names=["status"])
    if plan.status != "DRAFT" or interview.status != "PLANNING":
        logger.info(f"Planner persistence skipped after cancellation: plan_id={plan.id}")
        return
    plan.objectives = generated.objectives
    plan.sections = [section.model_dump() for section in generated.sections]
    plan.model_name = settings.LLM_MODEL
    plan.prompt_version = PROMPT_VERSION
    plan.generated_at = datetime.now(timezone.utc)
    plan.status = "READY"
    plan.error_message = None
    interview.status = "READY"
    await session.commit()
    logger.info(f"Planner state persisted as READY: plan_id={plan.id}")
