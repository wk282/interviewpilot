from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.db.models.interview import (
    InterviewAnswer,
    InterviewEvaluation,
    InterviewSession,
)
from app.db.models.recruitment import MessageThread, PlatformMessage


async def notify_enterprise_evaluation(
    session: AsyncSession,
    evaluation: InterviewEvaluation,
    interview: InterviewSession,
) -> None:
    if interview.application_id is None or evaluation.status not in {"COMPLETED", "FAILED"}:
        return

    thread = await session.scalar(
        select(MessageThread).where(
            MessageThread.application_id == interview.application_id
        )
    )
    if thread is None:
        logger.warning(
            f"Evaluation notification thread missing for interview {interview.id}"
        )
        return

    if evaluation.status == "COMPLETED":
        content = "候选人面试评估已完成，可以查看评估报告。"
        event = "INTERVIEW_EVALUATION_COMPLETED"
    else:
        content = "候选人面试评估生成失败，请进入报告页面重新生成。"
        event = "INTERVIEW_EVALUATION_FAILED"

    existing_message_id = await session.scalar(
        select(PlatformMessage.id).where(
            PlatformMessage.thread_id == thread.id,
            PlatformMessage.sender_type == "SYSTEM",
            PlatformMessage.message_type == "APPLICATION_STATUS",
            PlatformMessage.content == content,
        )
    )
    if existing_message_id is not None:
        return

    thread.updated_at = datetime.now(timezone.utc)
    session.add(
        PlatformMessage(
            thread_id=thread.id,
            sender_type="SYSTEM",
            sender_user_id=None,
            message_type="APPLICATION_STATUS",
            interview_session_id=None,
            content=content,
            message_metadata={
                "audience": "ENTERPRISE",
                "event": event,
                "interview_session_id": str(interview.id),
                "evaluation_id": str(evaluation.id),
                "evaluation_status": evaluation.status,
                "route": f"/enterprise/interviews/{interview.id}/report",
            },
        )
    )
    try:
        await session.commit()
    except Exception as error:
        await session.rollback()
        logger.warning(
            f"Evaluation notification failed for interview {interview.id}: {error}"
        )


async def enqueue_interview_evaluation(
    session: AsyncSession,
    interview: InterviewSession,
) -> InterviewEvaluation | None:
    if interview.status != "COMPLETED":
        return None

    evaluation = await session.scalar(
        select(InterviewEvaluation)
        .where(InterviewEvaluation.interview_session_id == interview.id)
        .with_for_update()
    )
    if evaluation is not None:
        if evaluation.status in {"COMPLETED", "FAILED"}:
            await notify_enterprise_evaluation(session, evaluation, interview)
        return evaluation

    evaluation = InterviewEvaluation(
        interview_session_id=interview.id,
        status="PENDING",
    )
    session.add(evaluation)
    await session.flush()

    answered_count = int(
        await session.scalar(
            select(func.count(InterviewAnswer.id)).where(
                InterviewAnswer.interview_session_id == interview.id
            )
        )
        or 0
    )
    if answered_count == 0:
        evaluation.status = "FAILED"
        evaluation.error_message = "面试没有可用于评估的回答"
        await session.commit()
        await notify_enterprise_evaluation(session, evaluation, interview)
        return evaluation

    await session.commit()
    await session.refresh(evaluation)
    try:
        from app.workers.interview_tasks import generate_interview_evaluation

        generate_interview_evaluation.delay(str(evaluation.id))
    except Exception as error:
        evaluation.status = "FAILED"
        evaluation.error_message = str(error)[:2000]
        await session.commit()
        logger.warning(
            f"Automatic evaluation queue failed for interview {interview.id}: {error}"
        )
        await notify_enterprise_evaluation(session, evaluation, interview)
    return evaluation
