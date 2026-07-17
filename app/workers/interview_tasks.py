import asyncio
import uuid

from sqlalchemy import select

from app.db.models.interview import CandidateProfile, InterviewEvaluation, InterviewPlan, InterviewSession, JobPosition
from app.db.models.user import AppUser
from app.db.session import AsyncSessionFactory, engine
from app.services.interview_planner import generate_plan
from app.services.interview_evaluator import evaluate_interview
from app.services.evaluation_lifecycle import notify_enterprise_evaluation
from app.workers.celery_app import celery_app


async def process_plan(plan_id: uuid.UUID) -> None:
    async with AsyncSessionFactory() as session:
        plan = await session.scalar(
            select(InterviewPlan).where(InterviewPlan.id == plan_id).with_for_update()
        )
        if plan is None or plan.status == "READY":
            return
        interview = await session.get(InterviewSession, plan.interview_session_id)
        position = await session.get(JobPosition, interview.job_position_id) if interview else None
        candidate = (
            await session.get(CandidateProfile, interview.candidate_profile_id)
            if interview
            else None
        )
        user = await session.get(AppUser, interview.created_by) if interview else None
        if not all((interview, position, candidate, user)):
            plan.status = "FAILED"
            plan.error_message = "Interview planning context is incomplete"
            if interview:
                interview.status = "FAILED"
            await session.commit()
            return

        await generate_plan(session, plan, interview, position, candidate, user)


async def mark_plan_failed(plan_id: uuid.UUID, error: Exception) -> None:
    async with AsyncSessionFactory() as session:
        plan = await session.get(InterviewPlan, plan_id)
        interview = (
            await session.get(InterviewSession, plan.interview_session_id)
            if plan
            else None
        )
        if plan and plan.status != "READY":
            plan.status = "FAILED"
            plan.error_message = str(error)[:2000]
        if interview and interview.status != "READY":
            interview.status = "FAILED"
        await session.commit()


def is_retryable_model_error(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    if status_code in {408, 409, 429} or (
        isinstance(status_code, int) and status_code >= 500
    ):
        return True
    error_name = error.__class__.__name__.lower()
    if any(name in error_name for name in ("timeout", "connection", "ratelimit")):
        return True
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "retryable': true",
            'retryable": true',
            "bad gateway",
            "error code: 502",
            "error code: 503",
            "error code: 504",
            "connection error",
            "timed out",
        )
    )


@celery_app.task(bind=True, name="interview.generate_plan", max_retries=3)
def generate_interview_plan(self, plan_id: str) -> None:
    parsed_plan_id = uuid.UUID(plan_id)

    async def run() -> None:
        try:
            await process_plan(parsed_plan_id)
        finally:
            await engine.dispose()

    try:
        asyncio.run(run())
    except Exception as error:
        if is_retryable_model_error(error) and self.request.retries < self.max_retries:
            countdown = 60 * (2 ** self.request.retries)
            raise self.retry(exc=error, countdown=countdown)

        async def fail() -> None:
            try:
                await mark_plan_failed(parsed_plan_id, error)
            finally:
                await engine.dispose()

        asyncio.run(fail())
        raise


async def process_evaluation(evaluation_id: uuid.UUID) -> None:
    async with AsyncSessionFactory() as session:
        evaluation = await session.scalar(
            select(InterviewEvaluation)
            .where(InterviewEvaluation.id == evaluation_id)
            .with_for_update()
        )
        if evaluation is None:
            return
        interview = await session.get(
            InterviewSession, evaluation.interview_session_id
        )
        if evaluation.status == "COMPLETED":
            if interview is not None:
                await notify_enterprise_evaluation(session, evaluation, interview)
            return
        if interview is None or interview.status != "COMPLETED":
            evaluation.status = "FAILED"
            evaluation.error_message = "Interview is not completed"
            await session.commit()
            if interview is not None:
                await notify_enterprise_evaluation(session, evaluation, interview)
            return

        evaluation.status = "GENERATING"
        evaluation.error_message = None
        await session.commit()
        try:
            await evaluate_interview(session, evaluation, interview)
        except Exception as error:
            await session.rollback()
            evaluation = await session.get(InterviewEvaluation, evaluation_id)
            if evaluation:
                evaluation.status = "FAILED"
                evaluation.error_message = str(error)[:2000]
                await session.commit()
            raise
        evaluation = await session.get(InterviewEvaluation, evaluation_id)
        if evaluation is not None:
            await notify_enterprise_evaluation(session, evaluation, interview)


async def mark_evaluation_retry_pending(
    evaluation_id: uuid.UUID,
    error: Exception,
) -> None:
    async with AsyncSessionFactory() as session:
        evaluation = await session.get(InterviewEvaluation, evaluation_id)
        if evaluation is not None and evaluation.status != "COMPLETED":
            evaluation.status = "PENDING"
            evaluation.error_message = f"自动重试中：{str(error)[:1900]}"
            await session.commit()


async def notify_final_evaluation_failure(evaluation_id: uuid.UUID) -> None:
    async with AsyncSessionFactory() as session:
        evaluation = await session.get(InterviewEvaluation, evaluation_id)
        interview = (
            await session.get(InterviewSession, evaluation.interview_session_id)
            if evaluation is not None
            else None
        )
        if evaluation is not None and interview is not None:
            await notify_enterprise_evaluation(session, evaluation, interview)


@celery_app.task(bind=True, name="interview.generate_evaluation", max_retries=3)
def generate_interview_evaluation(self, evaluation_id: str) -> None:
    parsed_evaluation_id = uuid.UUID(evaluation_id)

    async def run() -> None:
        try:
            await process_evaluation(parsed_evaluation_id)
        finally:
            await engine.dispose()

    try:
        asyncio.run(run())
    except Exception as error:
        if is_retryable_model_error(error) and self.request.retries < self.max_retries:
            async def prepare_retry() -> None:
                try:
                    await mark_evaluation_retry_pending(parsed_evaluation_id, error)
                finally:
                    await engine.dispose()

            asyncio.run(prepare_retry())
            countdown = 60 * (2 ** self.request.retries)
            raise self.retry(exc=error, countdown=countdown)

        async def notify_failure() -> None:
            try:
                await notify_final_evaluation_failure(parsed_evaluation_id)
            finally:
                await engine.dispose()

        asyncio.run(notify_failure())
        raise
