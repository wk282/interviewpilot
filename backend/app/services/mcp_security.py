from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from pydantic import BaseModel

from app.core.config import settings


MCP_TOKEN_AUDIENCE = "interviewpilot-mcp"


class MCPAuthContext(BaseModel):
    user_id: uuid.UUID
    workspace_id: uuid.UUID


def _secret() -> str:
    # A dedicated secret is preferred in production. Reusing the API signing
    # secret keeps local development simple while preserving signed context.
    return settings.MCP_INTERNAL_SECRET or settings.JWT_SECRET_KEY


def create_mcp_auth_token(*, user_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "workspace_id": str(workspace_id),
        "aud": MCP_TOKEN_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(seconds=settings.MCP_AUTH_TOKEN_TTL_SECONDS),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def verify_mcp_auth_token(token: str) -> MCPAuthContext:
    payload = jwt.decode(
        token,
        _secret(),
        algorithms=["HS256"],
        audience=MCP_TOKEN_AUDIENCE,
    )
    return MCPAuthContext(
        user_id=uuid.UUID(str(payload["sub"])),
        workspace_id=uuid.UUID(str(payload["workspace_id"])),
    )
