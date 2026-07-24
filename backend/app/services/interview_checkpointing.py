from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import settings
from app.core.logger import logger


CHECKPOINT_SCOPES = ("plan", "runtime", "evaluation")


def checkpoint_database_url() -> str:
    configured = settings.LANGGRAPH_CHECKPOINT_DATABASE_URL or settings.DATABASE_URL
    return configured.replace("postgresql+asyncpg://", "postgresql://", 1)


def checkpoint_thread_id(interview_id: uuid.UUID, scope: str) -> str:
    if scope not in CHECKPOINT_SCOPES:
        raise ValueError(f"Unsupported interview checkpoint scope: {scope}")
    return f"{interview_id}:{scope}"


def checkpoint_config(interview_id: uuid.UUID, scope: str) -> dict:
    return {
        "configurable": {
            "thread_id": checkpoint_thread_id(interview_id, scope),
        }
    }


@asynccontextmanager
async def interview_checkpointer() -> AsyncIterator[AsyncPostgresSaver]:
    async with AsyncPostgresSaver.from_conn_string(
        checkpoint_database_url()
    ) as checkpointer:
        # Setup is idempotent and also covers independent Celery worker processes.
        await checkpointer.setup()
        yield checkpointer


async def delete_interview_checkpoints(interview_id: uuid.UUID) -> None:
    async def delete_threads() -> None:
        async with interview_checkpointer() as checkpointer:
            for scope in CHECKPOINT_SCOPES:
                await checkpointer.adelete_thread(
                    checkpoint_thread_id(interview_id, scope)
                )

    try:
        await asyncio.wait_for(delete_threads(), timeout=3.0)
    except Exception as error:
        logger.warning(
            f"Failed to delete LangGraph checkpoints for interview {interview_id}: {error}"
        )
