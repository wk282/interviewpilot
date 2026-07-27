from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.interview import (
    CandidateProfile,
    InterviewEvaluation,
    InterviewPlanRevision,
    InterviewQualityAudit,
    InterviewSession,
    InterviewTurnCritique,
    JobPosition,
)


class InterviewReportNotFoundError(LookupError):
    pass


class InterviewReportNotReadyError(RuntimeError):
    pass


@dataclass
class InterviewReportData:
    interview: InterviewSession
    evaluation: InterviewEvaluation
    candidate: CandidateProfile
    position: JobPosition
    critiques: list[InterviewTurnCritique]
    revisions: list[InterviewPlanRevision]
    quality_audit: InterviewQualityAudit | None


async def load_interview_report_data(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    interview_id: uuid.UUID,
) -> InterviewReportData:
    row = (
        await session.execute(
            select(InterviewSession, InterviewEvaluation, CandidateProfile, JobPosition)
            .join(
                InterviewEvaluation,
                InterviewEvaluation.interview_session_id == InterviewSession.id,
            )
            .join(
                CandidateProfile,
                CandidateProfile.id == InterviewSession.candidate_profile_id,
            )
            .join(JobPosition, JobPosition.id == InterviewSession.job_position_id)
            .where(
                InterviewSession.id == interview_id,
                InterviewSession.workspace_id == workspace_id,
            )
        )
    ).one_or_none()
    if row is None:
        raise InterviewReportNotFoundError("评估报告不存在")

    interview, evaluation, candidate, position = row
    if evaluation.status != "COMPLETED":
        raise InterviewReportNotReadyError("评估报告完成后才能下载")

    critiques = list(
        (
            await session.scalars(
                select(InterviewTurnCritique)
                .where(InterviewTurnCritique.interview_session_id == interview.id)
                .order_by(InterviewTurnCritique.created_at)
            )
        ).all()
    )
    revisions = list(
        (
            await session.scalars(
                select(InterviewPlanRevision)
                .where(InterviewPlanRevision.interview_session_id == interview.id)
                .order_by(InterviewPlanRevision.version)
            )
        ).all()
    )
    quality_audit = await session.scalar(
        select(InterviewQualityAudit).where(
            InterviewQualityAudit.interview_session_id == interview.id
        )
    )
    return InterviewReportData(
        interview=interview,
        evaluation=evaluation,
        candidate=candidate,
        position=position,
        critiques=critiques,
        revisions=revisions,
        quality_audit=quality_audit,
    )


def build_pdf_from_report_data(data: InterviewReportData) -> bytes:
    # Local import avoids a circular dependency and keeps data loading usable
    # by APIs, workers and the standalone MCP server.
    from app.services.interview_report_pdf import build_interview_report_pdf

    return build_interview_report_pdf(
        evaluation=data.evaluation,
        candidate_name=data.candidate.full_name,
        job_title=data.position.title,
        completed_at=data.interview.completed_at,
        critiques=data.critiques,
        revisions=data.revisions,
        quality_audit=data.quality_audit,
    )
