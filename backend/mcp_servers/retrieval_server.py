from __future__ import annotations

import uuid
from time import perf_counter

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from app.core.config import settings
from app.core.permissions import require_workspace_role
from app.db.models.interview import CandidateProfile, InterviewSession, JobPosition
from app.db.models.user import AppUser
from app.db.session import AsyncSessionFactory
from app.services.ai_observability import elapsed_ms
from app.services.interview_planner import collect_evidence_in_process
from app.services.mcp_security import verify_mcp_auth_token


READ_ROLES = {"OWNER", "ADMIN", "HR", "INTERVIEWER", "VIEWER"}

mcp = FastMCP(
    "InterviewPilot Retrieval",
    host="0.0.0.0",
    port=8011,
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
async def hybrid_retrieve_interview_evidence(
    interview_id: str,
    query: str,
    auth_token: str,
) -> dict:
    """Retrieve tenant-scoped interview evidence using Vector+BM25+RRF.

    Authentication and all knowledge-source identifiers are derived from
    signed application context and persisted interview configuration. They are
    not accepted from an LLM tool call.
    """
    started_at = perf_counter()
    auth = verify_mcp_auth_token(auth_token)
    parsed_interview_id = uuid.UUID(interview_id)
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query cannot be empty")
    if len(normalized_query) > 1000:
        raise ValueError("query exceeds 1000 characters")

    async with AsyncSessionFactory() as session:
        await require_workspace_role(
            session,
            auth.workspace_id,
            auth.user_id,
            READ_ROLES,
        )
        interview = await session.scalar(
            select(InterviewSession).where(
                InterviewSession.id == parsed_interview_id,
                InterviewSession.workspace_id == auth.workspace_id,
            )
        )
        if interview is None:
            raise ValueError("interview does not exist in authenticated workspace")
        position = await session.scalar(
            select(JobPosition).where(
                JobPosition.id == interview.job_position_id,
                JobPosition.workspace_id == auth.workspace_id,
            )
        )
        candidate = await session.scalar(
            select(CandidateProfile).where(
                CandidateProfile.id == interview.candidate_profile_id,
                CandidateProfile.workspace_id == auth.workspace_id,
            )
        )
        user = await session.scalar(
            select(AppUser).where(
                AppUser.id == auth.user_id,
                AppUser.status == "ACTIVE",
            )
        )
        if position is None or candidate is None or user is None:
            raise ValueError("interview retrieval context is incomplete")

        observability: dict = {}
        evidence = await collect_evidence_in_process(
            session,
            interview,
            position,
            candidate,
            user,
            retrieval_query=normalized_query,
            observability=observability,
        )
        await session.rollback()

    return {
        "evidence": evidence,
        "metadata": {
            "protocol": "mcp",
            "tool": "hybrid_retrieve_interview_evidence",
            "retrieval_profile": settings.INTERVIEW_RETRIEVAL_PROFILE,
            "result_count": len(evidence),
            "server_latency_ms": elapsed_ms(started_at),
            "retrieval": observability,
        },
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
