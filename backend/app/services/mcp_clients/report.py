from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.mcp_clients.base import MCPToolError, call_mcp_tool
from app.services.mcp_security import create_mcp_auth_token


def _artifact_path(artifact_id: uuid.UUID) -> Path:
    root = Path(settings.MCP_ARTIFACT_STORAGE_ROOT).resolve()
    path = (root / f"{artifact_id}.pdf").resolve()
    if path.parent != root:
        raise MCPToolError("Invalid report artifact path")
    return path


async def render_interview_report_via_mcp(
    *,
    interview_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[bytes, dict[str, Any]]:
    payload = await call_mcp_tool(
        server_url=settings.MCP_REPORT_URL,
        tool_name="render_interview_report",
        arguments={
            "interview_id": str(interview_id),
            "template_version": "interview-report-v1",
            "locale": "zh-CN",
            "auth_token": create_mcp_auth_token(
                user_id=user_id,
                workspace_id=workspace_id,
            ),
        },
        timeout_seconds=settings.MCP_CALL_TIMEOUT_SECONDS,
    )
    artifact_id = uuid.UUID(str(payload.get("artifact_id")))
    path = _artifact_path(artifact_id)
    try:
        pdf = path.read_bytes()
    except OSError as error:
        raise MCPToolError(f"Cannot read report artifact {artifact_id}") from error
    finally:
        path.unlink(missing_ok=True)

    expected_digest = str(payload.get("sha256") or "")
    actual_digest = hashlib.sha256(pdf).hexdigest()
    if expected_digest and expected_digest != actual_digest:
        raise MCPToolError("Report artifact checksum mismatch")
    return pdf, payload
