from celery import Celery

from ocr_worker.config import settings


celery_app = Celery(
    "interviewpilot-ocr",
    broker=settings.broker_url,
    backend=settings.result_backend,
    include=["ocr_worker.tasks"],
)

celery_app.conf.update(
    task_default_queue=settings.ocr_queue,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
