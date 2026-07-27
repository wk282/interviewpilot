from __future__ import annotations

import uuid
from typing import Any

from app.core.config import settings
from app.services.mcp_clients.base import call_mcp_tool
from app.services.mcp_security import create_mcp_auth_token


async def retrieve_interview_evidence_via_mcp(
    *,
    interview_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    query: str,
) -> tuple[list[dict], dict[str, Any]]:
    payload = await call_mcp_tool(
        server_url=settings.MCP_RETRIEVAL_URL,
        tool_name="hybrid_retrieve_interview_evidence",
        arguments={
            "interview_id": str(interview_id),
            "query": query,
            "auth_token": create_mcp_auth_token(
                user_id=user_id,
                workspace_id=workspace_id,
            ),
        },
        timeout_seconds=settings.MCP_CALL_TIMEOUT_SECONDS,
    )
    evidence = payload.get("evidence")
    if not isinstance(evidence, list):
        raise ValueError("Retrieval MCP response does not contain an evidence list")
    metadata = payload.get("metadata")
    return evidence, metadata if isinstance(metadata, dict) else {}
