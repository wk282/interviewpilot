from time import perf_counter

from celery import Celery
from celery.signals import task_failure, task_postrun, task_prerun, task_retry, worker_ready

from app.core.config import settings
from app.core.event_loop import configure_windows_selector_event_loop
from app.core.logger import logger


configure_windows_selector_event_loop()


celery_app = Celery(
    "interviewpilot",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.ingestion_tasks", "app.workers.interview_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    worker_concurrency=settings.MAX_CONCURRENCY,
)


_task_started_at: dict[str, float] = {}


def _business_id(args) -> str | None:
    return str(args[0]) if args else None


@worker_ready.connect
def log_worker_ready(sender=None, **kwargs) -> None:
    logger.info(f"Celery worker ready | sender={sender}")


@task_prerun.connect
def log_task_started(task_id=None, task=None, args=None, **kwargs) -> None:
    if task_id:
        _task_started_at[str(task_id)] = perf_counter()
    logger.info(
        f"Celery task started | task={getattr(task, 'name', None)} | "
        f"task_id={task_id} | business_id={_business_id(args)}"
    )


@task_postrun.connect
def log_task_completed(
    task_id=None,
    task=None,
    args=None,
    state=None,
    **kwargs,
) -> None:
    started_at = _task_started_at.pop(str(task_id), None)
    latency_ms = int((perf_counter() - started_at) * 1000) if started_at else None
    logger.info(
        f"Celery task completed | task={getattr(task, 'name', None)} | "
        f"task_id={task_id} | business_id={_business_id(args)} | "
        f"state={state} | latency_ms={latency_ms}"
    )


@task_retry.connect
def log_task_retry(request=None, reason=None, **kwargs) -> None:
    request_args = getattr(request, "args", None)
    logger.warning(
        f"Celery task retry | task={getattr(request, 'task', None)} | "
        f"task_id={getattr(request, 'id', None)} | "
        f"business_id={_business_id(request_args)} | reason={reason}"
    )


@task_failure.connect
def log_task_failure(
    task_id=None,
    exception=None,
    sender=None,
    args=None,
    **kwargs,
) -> None:
    _task_started_at.pop(str(task_id), None)
    logger.error(
        f"Celery task failed | task={getattr(sender, 'name', None)} | "
        f"task_id={task_id} | business_id={_business_id(args)} | "
        f"error={type(exception).__name__}: {exception}"
    )
