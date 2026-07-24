from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required OCR worker setting: {name}")
    return value


def _psycopg_url(value: str) -> str:
    return value.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )


@dataclass(frozen=True)
class OCRWorkerSettings:
    database_url: str
    broker_url: str
    result_backend: str
    storage_root: Path
    ocr_queue: str
    main_queue: str
    render_scale: float
    minimum_confidence: float
    max_pages: int


settings = OCRWorkerSettings(
    database_url=_psycopg_url(_required("DATABASE_URL")),
    broker_url=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    result_backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
    storage_root=Path(os.getenv("DOCUMENT_STORAGE_ROOT", "data/uploads")).resolve(),
    ocr_queue=os.getenv("OCR_CELERY_QUEUE", "ocr"),
    main_queue=os.getenv("CELERY_MAIN_QUEUE", "celery"),
    render_scale=float(os.getenv("OCR_RENDER_SCALE", "2.5")),
    minimum_confidence=float(os.getenv("OCR_MIN_CONFIDENCE", "0.75")),
    max_pages=int(os.getenv("OCR_MAX_PAGES", "200")),
)
