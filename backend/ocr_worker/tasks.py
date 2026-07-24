from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ocr_worker.celery_app import celery_app
from ocr_worker.config import settings
from ocr_worker.logging_config import logger
from ocr_worker.pdf_processor import (
    PaddleOCRBackend,
    PdfOCRQualityError,
    process_pdf,
)


_ocr_backend: PaddleOCRBackend | None = None


def get_ocr_backend() -> PaddleOCRBackend:
    global _ocr_backend
    if _ocr_backend is None:
        _ocr_backend = PaddleOCRBackend(render_scale=settings.render_scale)
    return _ocr_backend


def start_ocr_attempt(job_id: uuid.UUID) -> tuple[dict[str, Any], uuid.UUID] | None:
    with psycopg.connect(settings.database_url, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT
                job.id AS job_id,
                job.status AS job_status,
                version.id AS version_id,
                version.storage_key,
                document.id AS document_id
            FROM ingestion_job AS job
            JOIN document_version AS version ON version.id = job.document_version_id
            JOIN document ON document.id = version.document_id
            WHERE job.id = %s
            FOR UPDATE OF job
            """,
            (job_id,),
        ).fetchone()
        if row is None or row["job_status"] != "WAITING_OCR":
            logger.info(
                "OCR attempt skipped | job_id=%s | status=%s",
                job_id,
                row["job_status"] if row else "NOT_FOUND",
            )
            return None
        attempt_no = connection.execute(
            """
            SELECT COALESCE(MAX(attempt_no), 0) + 1 AS next_attempt_no
            FROM ingestion_stage_run
            WHERE ingestion_job_id = %s AND stage = 'OCR'
            """,
            (job_id,),
        ).fetchone()["next_attempt_no"]
        stage_id = connection.execute(
            """
            INSERT INTO ingestion_stage_run (
                ingestion_job_id, stage, attempt_no, status, started_at
            ) VALUES (%s, 'OCR', %s, 'RUNNING', NOW())
            RETURNING id AS stage_id
            """,
            (job_id, attempt_no),
        ).fetchone()["stage_id"]
        connection.execute(
            """
            UPDATE ingestion_job
            SET status = 'RUNNING', current_stage = 'OCR', progress = 30,
                started_at = COALESCE(started_at, NOW()), error_code = NULL,
                error_message = NULL, completed_at = NULL
            WHERE id = %s
            """,
            (job_id,),
        )
        connection.execute(
            "UPDATE document_version SET status = 'PROCESSING' WHERE id = %s",
            (row["version_id"],),
        )
        connection.execute(
            "UPDATE document SET status = 'PROCESSING' WHERE id = %s",
            (row["document_id"],),
        )
        logger.info(
            "OCR attempt started | job_id=%s | stage_id=%s | attempt=%s",
            job_id,
            stage_id,
            attempt_no,
        )
        return dict(row), stage_id


def complete_ocr_attempt(
    *,
    job: dict[str, Any],
    stage_id: uuid.UUID,
    parsed_content_key: str,
    quality_report: dict[str, Any],
) -> bool:
    with psycopg.connect(settings.database_url, row_factory=dict_row) as connection:
        current = connection.execute(
            "SELECT status FROM ingestion_job WHERE id = %s FOR UPDATE",
            (job["job_id"],),
        ).fetchone()
        if current is None:
            return False
        if current["status"] == "CANCELLED":
            connection.execute(
                """
                UPDATE ingestion_stage_run
                SET status = 'SKIPPED', completed_at = NOW(),
                    error_code = 'INGESTION_CANCELLED',
                    error_message = 'OCR completed after the ingestion job was cancelled'
                WHERE id = %s
                """,
                (stage_id,),
            )
            return False
        connection.execute(
            """
            UPDATE ingestion_stage_run
            SET status = 'COMPLETED', completed_at = NOW(), metrics = %s
            WHERE id = %s
            """,
            (Jsonb(quality_report), stage_id),
        )
        connection.execute(
            """
            UPDATE document_version
            SET status = 'PROCESSING', parser_name = 'PYMUPDF_PADDLEOCR',
                parser_version = '1.0', parsed_content_key = %s,
                quality_report = %s
            WHERE id = %s
            """,
            (parsed_content_key, Jsonb(quality_report), job["version_id"]),
        )
        connection.execute(
            "UPDATE document SET status = 'PROCESSING' WHERE id = %s",
            (job["document_id"],),
        )
        connection.execute(
            """
            UPDATE ingestion_job
            SET status = 'PENDING', current_stage = 'CHUNKING', progress = 45,
                error_code = NULL, error_message = NULL, completed_at = NULL
            WHERE id = %s
            """,
            (job["job_id"],),
        )
        logger.info(
            "OCR attempt completed | job_id=%s | stage_id=%s | parsed_content_key=%s",
            job["job_id"],
            stage_id,
            parsed_content_key,
        )
        return True


def fail_ocr_attempt(
    *,
    job: dict[str, Any],
    stage_id: uuid.UUID,
    error: Exception,
    quality_report: dict[str, Any] | None = None,
) -> None:
    error_code = type(error).__name__.upper()[:100]
    error_message = str(error)[:2000]
    with psycopg.connect(settings.database_url) as connection:
        connection.execute(
            """
            UPDATE ingestion_stage_run
            SET status = 'FAILED', completed_at = NOW(), error_code = %s,
                error_message = %s, metrics = %s
            WHERE id = %s
            """,
            (
                error_code,
                error_message,
                Jsonb(quality_report) if quality_report is not None else None,
                stage_id,
            ),
        )
        connection.execute(
            """
            UPDATE ingestion_job
            SET status = 'FAILED', current_stage = 'OCR', progress = 30,
                error_code = %s, error_message = %s, completed_at = NOW()
            WHERE id = %s
            """,
            (error_code, error_message, job["job_id"]),
        )
        connection.execute(
            """
            UPDATE document_version
            SET status = 'FAILED', quality_report = COALESCE(%s, quality_report)
            WHERE id = %s
            """,
            (
                Jsonb(quality_report) if quality_report is not None else None,
                job["version_id"],
            ),
        )
        connection.execute(
            "UPDATE document SET status = 'FAILED' WHERE id = %s",
            (job["document_id"],),
        )
    logger.error(
        "OCR attempt failed | job_id=%s | stage_id=%s | error=%s: %s",
        job["job_id"],
        stage_id,
        type(error).__name__,
        error,
    )


def mark_handoff_failure(job: dict[str, Any], error: Exception) -> None:
    with psycopg.connect(settings.database_url) as connection:
        connection.execute(
            """
            UPDATE ingestion_job
            SET status = 'FAILED', error_code = 'INGESTION_QUEUE_UNAVAILABLE',
                error_message = %s, completed_at = NOW()
            WHERE id = %s
            """,
            (str(error)[:2000], job["job_id"]),
        )
        connection.execute(
            "UPDATE document_version SET status = 'FAILED' WHERE id = %s",
            (job["version_id"],),
        )
        connection.execute(
            "UPDATE document SET status = 'FAILED' WHERE id = %s",
            (job["document_id"],),
        )
    logger.error(
        "OCR handoff failed | job_id=%s | error=%s: %s",
        job["job_id"],
        type(error).__name__,
        error,
    )


@celery_app.task(name="ocr.process_pdf", acks_late=True)
def process_pdf_ocr(job_id: str) -> dict[str, Any]:
    logger.info("OCR task received | job_id=%s", job_id)
    parsed_job_id = uuid.UUID(job_id)
    started = start_ocr_attempt(parsed_job_id)
    if started is None:
        return {"job_id": job_id, "status": "SKIPPED"}
    job, stage_id = started
    source_path = (settings.storage_root / job["storage_key"]).resolve()
    if settings.storage_root not in source_path.parents:
        error = ValueError("Document storage key escapes the configured storage root")
        fail_ocr_attempt(job=job, stage_id=stage_id, error=error)
        raise error

    try:
        parsed, quality_report = process_pdf(
            source_path,
            get_ocr_backend(),
            max_pages=settings.max_pages,
            minimum_confidence=settings.minimum_confidence,
        )
        parsed_path = source_path.parent / "parsed.json"
        temporary_path = source_path.parent / "parsed.ocr.tmp"
        temporary_path.write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary_path.replace(parsed_path)
        parsed_content_key = parsed_path.relative_to(settings.storage_root).as_posix()
        should_resume = complete_ocr_attempt(
            job=job,
            stage_id=stage_id,
            parsed_content_key=parsed_content_key,
            quality_report=quality_report,
        )
    except Exception as error:
        report = error.report if isinstance(error, PdfOCRQualityError) else None
        fail_ocr_attempt(
            job=job,
            stage_id=stage_id,
            error=error,
            quality_report=report,
        )
        raise

    if should_resume:
        try:
            celery_app.send_task(
                "ingestion.process_document",
                args=[job_id],
                queue=settings.main_queue,
            )
            logger.info(
                "OCR result handed to ingestion queue | job_id=%s | queue=%s",
                job_id,
                settings.main_queue,
            )
        except Exception as error:
            mark_handoff_failure(job, error)
            raise
    result = {
        "job_id": job_id,
        "status": "COMPLETED" if should_resume else "CANCELLED",
        "ocr_processed_pages": quality_report["ocr_processed_pages"],
        "character_count": quality_report["character_count"],
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    logger.info("OCR task completed | result=%s", result)
    return result
