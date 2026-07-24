import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from openai import AsyncOpenAI
from sqlalchemy import delete, func, select

from app.core.config import settings
from app.core.logger import logger
from app.db.models.chunk import DocumentChunk
from app.db.models.document import Document, DocumentVersion
from app.db.models.ingestion import IngestionJob, IngestionStageRun
from app.db.models.knowledge_base import KnowledgeBase
from app.db.session import AsyncSessionFactory, engine
from app.services.document_parsers import build_quality_report, parser_for
from app.services.bm25_store import OpenSearchBM25Store
from app.services.hierarchical_chunker import HierarchicalChunker
from app.services.ai_concurrency import ai_concurrency_slot
from app.workers.celery_app import celery_app


class IngestionCancelled(Exception):
    pass


SUPPORTED_INGESTION_EXTENSIONS = {".md", ".txt", ".docx", ".pdf"}


async def start_stage(session, job: IngestionJob, stage: str, progress: int) -> IngestionStageRun:
    await session.refresh(job)
    if job.status == "CANCELLED":
        raise IngestionCancelled
    job.status = "RUNNING"
    job.current_stage = stage
    job.progress = progress
    latest_attempt = await session.scalar(
        select(func.max(IngestionStageRun.attempt_no)).where(
            IngestionStageRun.ingestion_job_id == job.id,
            IngestionStageRun.stage == stage,
        )
    )
    stage_run = IngestionStageRun(
        ingestion_job_id=job.id,
        stage=stage,
        attempt_no=(latest_attempt or 0) + 1,
        status="RUNNING",
        started_at=datetime.now(timezone.utc),
    )
    session.add(stage_run)
    await session.commit()
    logger.info(
        f"Ingestion stage started | job_id={job.id} | stage={stage} | "
        f"attempt={stage_run.attempt_no} | progress={progress}"
    )
    return stage_run


async def finish_stage(session, stage_run: IngestionStageRun, metrics: dict | None = None) -> None:
    stage_run.status = "COMPLETED"
    stage_run.metrics = metrics
    stage_run.completed_at = datetime.now(timezone.utc)
    await session.commit()
    logger.info(
        f"Ingestion stage completed | job_id={stage_run.ingestion_job_id} | "
        f"stage={stage_run.stage} | attempt={stage_run.attempt_no} | metrics={metrics or {}}"
    )


async def embed_and_index_chunks(
    session,
    job: IngestionJob,
    document: Document,
    version: DocumentVersion,
) -> None:
    logger.info(
        f"Embedding pipeline started | job_id={job.id} | "
        f"document_id={document.id} | version_id={version.id}"
    )
    embedding_stage = await start_stage(session, job, "EMBEDDING", 60)
    chunks = list(
        (
            await session.scalars(
                select(DocumentChunk)
                .where(
                    DocumentChunk.document_version_id == version.id,
                    DocumentChunk.chunk_type == "CHILD",
                )
                .order_by(DocumentChunk.chunk_index)
            )
        ).all()
    )
    if not chunks:
        raise ValueError("No child chunks available for embedding")

    client = AsyncOpenAI(
        api_key=settings.EMBEDDING_API_KEY or settings.OPENAI_API_KEY,
        base_url=settings.EMBEDDING_BASE_URL or settings.OPENAI_BASE_URL,
    )
    embedded_at = datetime.now(timezone.utc)
    embedding_queue_wait_ms = 0
    for offset in range(0, len(chunks), settings.EMBEDDING_BATCH_SIZE):
        batch = chunks[offset : offset + settings.EMBEDDING_BATCH_SIZE]
        logger.info(
            f"Embedding batch started | job_id={job.id} | offset={offset} | "
            f"batch_size={len(batch)} | total_chunks={len(chunks)}"
        )
        async with ai_concurrency_slot(
            "document_embedding",
            settings.EMBEDDING_MODEL_NAME,
        ) as concurrency:
            response = await client.embeddings.create(
                model=settings.EMBEDDING_MODEL_NAME,
                input=[chunk.content for chunk in batch],
                dimensions=settings.EMBEDDING_DIMENSIONS,
            )
        embedding_queue_wait_ms += concurrency.queue_wait_ms
        vectors = sorted(response.data, key=lambda item: item.index)
        if len(vectors) != len(batch):
            raise ValueError("Embedding API returned an incomplete batch")
        for chunk, result in zip(batch, vectors):
            if len(result.embedding) != settings.EMBEDDING_DIMENSIONS:
                raise ValueError(
                    f"Embedding dimension mismatch: expected {settings.EMBEDDING_DIMENSIONS}, "
                    f"got {len(result.embedding)}"
                )
            chunk.embedding = result.embedding
            chunk.embedding_model = settings.EMBEDDING_MODEL_NAME
            chunk.embedded_at = embedded_at

    await finish_stage(
        session,
        embedding_stage,
        {
            "embedded_chunk_count": len(chunks),
            "model": settings.EMBEDDING_MODEL_NAME,
            "dimensions": settings.EMBEDDING_DIMENSIONS,
            "batch_count": (
                len(chunks) + settings.EMBEDDING_BATCH_SIZE - 1
            ) // settings.EMBEDDING_BATCH_SIZE,
            "concurrency_queue_wait_ms": embedding_queue_wait_ms,
        },
    )

    indexing_stage = await start_stage(session, job, "INDEXING", 90)
    missing_embedding = any(chunk.embedding is None for chunk in chunks)
    if missing_embedding:
        raise ValueError("Some child chunks have no embedding")
    bm25_indexed_count = 0
    if settings.OPENSEARCH_URL:
        bm25_records = [
            {
                "chunk_id": str(chunk.id),
                "workspace_id": str(chunk.workspace_id),
                "knowledge_base_id": str(chunk.knowledge_base_id),
                "document_id": str(document.id),
                "document_version_id": str(version.id),
                "chunk_type": chunk.chunk_type,
                "content": chunk.content,
            }
            for chunk in chunks
        ]
        await asyncio.to_thread(
            OpenSearchBM25Store().index_chunks,
            bm25_records,
        )
        bm25_indexed_count = len(bm25_records)
    await finish_stage(
        session,
        indexing_stage,
        {
            "indexed_chunk_count": len(chunks),
            "vector_index": "idx_document_chunk_embedding_hnsw",
            "bm25_indexed_chunk_count": bm25_indexed_count,
        },
    )

    job.status = "COMPLETED"
    job.current_stage = "INDEXING"
    job.progress = 100
    job.completed_at = datetime.now(timezone.utc)
    job.error_code = None
    job.error_message = None
    version.status = "READY"
    document.status = "READY"
    await session.commit()
    logger.info(
        f"Ingestion completed | job_id={job.id} | document_id={document.id} | "
        f"child_chunks={len(chunks)} | bm25_indexed={bm25_indexed_count}"
    )


async def process_ingestion_job(job_id: uuid.UUID) -> None:
    logger.info(f"Ingestion job started | job_id={job_id}")
    async with AsyncSessionFactory() as session:
        job = await session.scalar(
            select(IngestionJob).where(IngestionJob.id == job_id).with_for_update()
        )
        if job is None or job.status in {
            "RUNNING",
            "WAITING_OCR",
            "COMPLETED",
            "CANCELLED",
        }:
            logger.info(
                f"Ingestion job skipped | job_id={job_id} | "
                f"status={job.status if job else 'NOT_FOUND'}"
            )
            return

        version = await session.get(DocumentVersion, job.document_version_id)
        document = await session.get(Document, version.document_id) if version else None
        if version is None or document is None:
            job.status = "FAILED"
            job.error_code = "DOCUMENT_VERSION_NOT_FOUND"
            job.error_message = "Document version no longer exists"
            await session.commit()
            return

        storage_root = Path(settings.DOCUMENT_STORAGE_ROOT).resolve()
        source_path = storage_root / version.storage_key
        document.status = "PROCESSING"
        version.status = "PROCESSING"

        try:
            if job.current_stage in {"EMBEDDING", "INDEXING"}:
                await embed_and_index_chunks(session, job, document, version)
                return

            if job.current_stage == "CHUNKING" and version.parsed_content_key:
                parsed_path = storage_root / version.parsed_content_key
                parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
            else:
                validation = await start_stage(session, job, "VALIDATION", 5)
                if not source_path.is_file():
                    raise FileNotFoundError(f"Source file not found: {version.storage_key}")
                await finish_stage(
                    session,
                    validation,
                    {"file_size": source_path.stat().st_size, "extension": source_path.suffix.lower()},
                )

                if source_path.suffix.lower() not in SUPPORTED_INGESTION_EXTENSIONS:
                    raise ValueError(
                        f"Unsupported document extension: {source_path.suffix.lower()}"
                    )

                parsing = await start_stage(session, job, "PARSING", 15)
                parser = parser_for(source_path)
                parsed = parser.parse(source_path)
                await finish_stage(session, parsing, {"parser": parser.name, "block_count": len(parsed["blocks"])})

                quality_check = await start_stage(session, job, "QUALITY_CHECK", 30)
                quality_report = build_quality_report(parsed)
                await finish_stage(session, quality_check, quality_report)
                if quality_report.get("needs_ocr"):
                    ocr_pages = quality_report.get("ocr_required_pages", [])
                    job.status = "WAITING_OCR"
                    job.current_stage = "OCR"
                    job.progress = 30
                    job.error_code = "OCR_REQUIRED"
                    job.error_message = (
                        f"PDF pages require OCR: {', '.join(str(page) for page in ocr_pages)}"
                    )[:2000]
                    job.completed_at = None
                    version.parser_name = parser.name
                    version.parser_version = parser.version
                    version.quality_report = quality_report
                    version.status = "OCR_PENDING"
                    document.status = "OCR_PENDING"
                    await session.commit()
                    logger.info(
                        f"Ingestion waiting for OCR | job_id={job.id} | "
                        f"document_id={document.id} | pages={ocr_pages}"
                    )
                    if settings.OCR_WORKER_ENABLED:
                        try:
                            celery_app.send_task(
                                "ocr.process_pdf",
                                args=[str(job.id)],
                                queue=settings.OCR_CELERY_QUEUE,
                            )
                            logger.info(
                                f"OCR task queued | job_id={job.id} | "
                                f"queue={settings.OCR_CELERY_QUEUE}"
                            )
                        except Exception as queue_error:
                            job.status = "FAILED"
                            job.error_code = "OCR_QUEUE_UNAVAILABLE"
                            job.error_message = str(queue_error)[:2000]
                            job.completed_at = datetime.now(timezone.utc)
                            version.status = "FAILED"
                            document.status = "FAILED"
                            await session.commit()
                            logger.error(
                                f"OCR task queue failed | job_id={job.id} | "
                                f"error={type(queue_error).__name__}: {queue_error}"
                            )
                    return
                if quality_report["empty"]:
                    raise ValueError("Document contains no readable text")

                cleaning = await start_stage(session, job, "CLEANING", 40)
                parsed["plain_text"] = parsed["plain_text"].replace("\r\n", "\n").replace("\r", "\n").strip()
                parsed_path = source_path.parent / "parsed.json"
                parsed_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
                await finish_stage(session, cleaning, {"parsed_content_key": parsed_path.relative_to(storage_root).as_posix()})

                version.parser_name = parser.name
                version.parser_version = parser.version
                version.parsed_content_key = parsed_path.relative_to(storage_root).as_posix()
                version.quality_report = quality_report

            knowledge_base = await session.get(KnowledgeBase, document.knowledge_base_id)
            if knowledge_base is None:
                raise ValueError("Knowledge base no longer exists")

            chunking = await start_stage(session, job, "CHUNKING", 45)
            chunker = HierarchicalChunker()
            records = chunker.chunk(
                parsed["plain_text"],
                version.original_filename,
                source_path.suffix.lower() == ".md",
            )
            if not records:
                raise ValueError("Document produced no chunks")

            await session.execute(
                delete(DocumentChunk).where(DocumentChunk.document_version_id == version.id)
            )
            parent_rows = [record for record in records if record.chunk_type == "PARENT"]
            child_rows = [record for record in records if record.chunk_type == "CHILD"]

            def chunk_model(record):
                return DocumentChunk(
                    id=record.id,
                    workspace_id=knowledge_base.workspace_id,
                    knowledge_base_id=knowledge_base.id,
                    document_version_id=version.id,
                    parent_chunk_id=record.parent_id,
                    chunk_type=record.chunk_type,
                    chunk_index=record.chunk_index,
                    content=record.content,
                    char_count=len(record.content),
                    content_hash=record.content_hash,
                    chunk_metadata=record.metadata,
                )

            session.add_all([chunk_model(record) for record in parent_rows])
            await session.flush()
            session.add_all([chunk_model(record) for record in child_rows])
            await finish_stage(
                session,
                chunking,
                {"parent_count": len(parent_rows), "child_count": len(child_rows)},
            )

            job.status = "PENDING"
            job.current_stage = "EMBEDDING"
            job.progress = 60
            await session.commit()
            await embed_and_index_chunks(session, job, document, version)
        except IngestionCancelled:
            await session.rollback()
            logger.info(f"Ingestion cancelled | job_id={job_id}")
            return
        except Exception as error:
            await session.rollback()
            logger.exception(
                f"Ingestion job failed | job_id={job_id} | "
                f"error={type(error).__name__}: {error}"
            )
            job = await session.get(IngestionJob, job_id)
            if job is not None:
                if job.status == "CANCELLED":
                    return
                running_stage = await session.scalar(
                    select(IngestionStageRun)
                    .where(
                        IngestionStageRun.ingestion_job_id == job_id,
                        IngestionStageRun.status == "RUNNING",
                    )
                    .order_by(IngestionStageRun.created_at.desc())
                    .limit(1)
                )
                if running_stage is not None:
                    running_stage.status = "FAILED"
                    running_stage.error_code = type(error).__name__.upper()
                    running_stage.error_message = str(error)[:2000]
                    running_stage.completed_at = datetime.now(timezone.utc)
                job.status = "FAILED"
                job.error_code = type(error).__name__.upper()
                job.error_message = str(error)[:2000]
                job.completed_at = datetime.now(timezone.utc)
                if version := await session.get(DocumentVersion, job.document_version_id):
                    version.status = "FAILED"
                    if document := await session.get(Document, version.document_id):
                        document.status = "FAILED"
                await session.commit()
            raise


@celery_app.task(
    name="ingestion.process_document",
    autoretry_for=(ConnectionError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def process_document(job_id: str) -> None:
    async def run() -> None:
        try:
            await process_ingestion_job(uuid.UUID(job_id))
        finally:
            await engine.dispose()

    asyncio.run(run())
