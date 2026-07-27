import uuid
import unittest
import hashlib
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import jwt

from app.core.config import settings
from app.services.interview_planner import collect_evidence
from app.services.mcp_security import (
    create_mcp_auth_token,
    verify_mcp_auth_token,
)
from app.services.mcp_clients.report import render_interview_report_via_mcp


class MCPSecurityTest(unittest.TestCase):
    def test_signed_context_preserves_tenant_identity(self) -> None:
        user_id = uuid.uuid4()
        workspace_id = uuid.uuid4()
        token = create_mcp_auth_token(
            user_id=user_id,
            workspace_id=workspace_id,
        )

        context = verify_mcp_auth_token(token)

        self.assertEqual(context.user_id, user_id)
        self.assertEqual(context.workspace_id, workspace_id)

    def test_token_signed_with_another_secret_is_rejected(self) -> None:
        token = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "workspace_id": str(uuid.uuid4()),
                "aud": "interviewpilot-mcp",
            },
            "wrong-secret-that-is-longer-than-thirty-two-bytes",
            algorithm="HS256",
        )

        with self.assertRaises(jwt.InvalidTokenError):
            verify_mcp_auth_token(token)


class MCPRetrievalFallbackTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.previous_enabled = settings.MCP_RETRIEVAL_ENABLED
        settings.MCP_RETRIEVAL_ENABLED = True
        self.addCleanup(
            setattr,
            settings,
            "MCP_RETRIEVAL_ENABLED",
            self.previous_enabled,
        )
        self.session = AsyncMock()
        self.interview = SimpleNamespace(
            id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            configuration={},
        )
        self.position = SimpleNamespace(
            title="AI Agent Engineer",
            department="AI",
            description="Build production agents",
            requirements={},
        )
        self.candidate = SimpleNamespace()
        self.user = SimpleNamespace(id=uuid.uuid4())

    @patch("app.services.interview_planner.collect_evidence_in_process")
    @patch("app.services.interview_planner.retrieve_interview_evidence_via_mcp")
    async def test_success_uses_mcp_without_local_pipeline(
        self,
        mcp_retrieve: AsyncMock,
        local_retrieve: AsyncMock,
    ) -> None:
        expected = [{"evidence_id": 1, "content": "MCP evidence"}]
        mcp_retrieve.return_value = (
            expected,
            {"protocol": "mcp", "result_count": 1},
        )
        trace: dict = {}

        actual = await collect_evidence(
            self.session,
            self.interview,
            self.position,
            self.candidate,
            self.user,
            observability=trace,
        )

        self.assertEqual(actual, expected)
        local_retrieve.assert_not_awaited()
        self.assertFalse(trace["mcp"]["fallback"])
        self.session.commit.assert_awaited_once()

    @patch("app.services.interview_planner.collect_evidence_in_process")
    @patch("app.services.interview_planner.retrieve_interview_evidence_via_mcp")
    async def test_transport_failure_uses_in_process_fallback(
        self,
        mcp_retrieve: AsyncMock,
        local_retrieve: AsyncMock,
    ) -> None:
        mcp_retrieve.side_effect = TimeoutError("MCP timed out")
        local_retrieve.return_value = [{"content": "local evidence"}]
        trace: dict = {}

        actual = await collect_evidence(
            self.session,
            self.interview,
            self.position,
            self.candidate,
            self.user,
            retrieval_query="Agent memory",
            observability=trace,
        )

        self.assertEqual(actual, [{"content": "local evidence"}])
        local_retrieve.assert_awaited_once()
        self.assertTrue(trace["mcp"]["fallback"])


class MCPReportArtifactTest(unittest.IsolatedAsyncioTestCase):
    @patch("app.services.mcp_clients.report.call_mcp_tool")
    async def test_artifact_is_verified_read_and_deleted(
        self,
        call_tool: AsyncMock,
    ) -> None:
        previous_root = settings.MCP_ARTIFACT_STORAGE_ROOT
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings.MCP_ARTIFACT_STORAGE_ROOT = temporary_directory
            self.addCleanup(
                setattr,
                settings,
                "MCP_ARTIFACT_STORAGE_ROOT",
                previous_root,
            )
            artifact_id = uuid.uuid4()
            pdf = b"%PDF-1.7 controlled-test-artifact"
            artifact_path = Path(temporary_directory) / f"{artifact_id}.pdf"
            artifact_path.write_bytes(pdf)
            call_tool.return_value = {
                "artifact_id": str(artifact_id),
                "sha256": hashlib.sha256(pdf).hexdigest(),
                "media_type": "application/pdf",
            }

            actual, metadata = await render_interview_report_via_mcp(
                interview_id=uuid.uuid4(),
                workspace_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
            )

            self.assertEqual(actual, pdf)
            self.assertEqual(metadata["artifact_id"], str(artifact_id))
            self.assertFalse(artifact_path.exists())


if __name__ == "__main__":
    unittest.main()
