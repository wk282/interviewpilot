from __future__ import annotations

import hashlib
import time
import uuid
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from app.core.config import settings
from app.core.permissions import require_workspace_role
from app.db.session import AsyncSessionFactory
from app.services.interview_report_data import (
    build_pdf_from_report_data,
    load_interview_report_data,
)
from app.services.mcp_security import verify_mcp_auth_token


READ_ROLES = {"OWNER", "ADMIN", "HR", "INTERVIEWER", "VIEWER"}
SUPPORTED_TEMPLATE = "interview-report-v1"
SUPPORTED_LOCALE = "zh-CN"

mcp = FastMCP(
    "InterviewPilot Report",
    host="0.0.0.0",
    port=8012,
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
)


def _artifact_root() -> Path:
    root = Path(settings.MCP_ARTIFACT_STORAGE_ROOT).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _remove_expired_artifacts(root: Path) -> None:
    cutoff = time.time() - settings.MCP_ARTIFACT_MAX_AGE_SECONDS
    for path in root.glob("*.pdf"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            continue


@mcp.tool()
async def render_interview_report(
    interview_id: str,
    template_version: str,
    locale: str,
    auth_token: str,
) -> dict:
    """Render one authorized completed interview to a controlled PDF artifact."""
    if template_version != SUPPORTED_TEMPLATE:
        raise ValueError("unsupported report template version")
    if locale != SUPPORTED_LOCALE:
        raise ValueError("unsupported report locale")

    auth = verify_mcp_auth_token(auth_token)
    parsed_interview_id = uuid.UUID(interview_id)
    async with AsyncSessionFactory() as session:
        await require_workspace_role(
            session,
            auth.workspace_id,
            auth.user_id,
            READ_ROLES,
        )
        data = await load_interview_report_data(
            session,
            workspace_id=auth.workspace_id,
            interview_id=parsed_interview_id,
        )
        pdf = build_pdf_from_report_data(data)
        await session.rollback()

    artifact_id = uuid.uuid4()
    root = _artifact_root()
    _remove_expired_artifacts(root)
    artifact_path = root / f"{artifact_id}.pdf"
    temporary_path = root / f".{artifact_id}.tmp"
    temporary_path.write_bytes(pdf)
    temporary_path.replace(artifact_path)
    return {
        "artifact_id": str(artifact_id),
        "media_type": "application/pdf",
        "size_bytes": len(pdf),
        "sha256": hashlib.sha256(pdf).hexdigest(),
        "template_version": template_version,
        "locale": locale,
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
