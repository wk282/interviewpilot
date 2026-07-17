import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from openai import AsyncOpenAI
from sqlalchemy import delete, func, select

from app.core.config import settings
from app.db.models.chunk import DocumentChunk
from app.db.models.document import Document, DocumentVersion
from app.db.models.ingestion import IngestionJob, IngestionStageRun
from app.db.models.knowledge_base import KnowledgeBase
from app.db.session import AsyncSessionFactory, engine
from app.services.document_parsers import build_quality_report, parser_for
from app.services.bm25_store import OpenSearchBM25Store
from app.services.hierarchical_chunker import HierarchicalChunker
from app.workers.celery_app import celery_app


class IngestionCancelled(Exception):
    pass


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
    return stage_run


async def finish_stage(session, stage_run: IngestionStageRun, metrics: dict | None = None) -> None:
    stage_run.status = "COMPLETED"
    stage_run.metrics = metrics
    stage_run.completed_at = datetime.now(timezone.utc)
    await session.commit()


async def embed_and_index_chunks(
    session,
    job: IngestionJob,
    document: Document,
    version: DocumentVersion,
) -> None:
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
    for offset in range(0, len(chunks), settings.EMBEDDING_BATCH_SIZE):
        batch = chunks[offset : offset + settings.EMBEDDING_BATCH_SIZE]
        response = await client.embeddings.create(
            model=settings.EMBEDDING_MODEL_NAME,
            input=[chunk.content for chunk in batch],
            dimensions=settings.EMBEDDING_DIMENSIONS,
        )
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


async def process_ingestion_job(job_id: uuid.UUID) -> None:
    async with AsyncSessionFactory() as session:
        job = await session.scalar(
            select(IngestionJob).where(IngestionJob.id == job_id).with_for_update()
        )
        if job is None or job.status in {"RUNNING", "COMPLETED", "CANCELLED"}:
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

                if source_path.suffix.lower() not in {".md", ".txt", ".docx"}:
                    job.status = "PENDING"
                    job.current_stage = "PARSING"
                    job.progress = 10
                    await session.commit()
                    return

                parsing = await start_stage(session, job, "PARSING", 15)
                parser = parser_for(source_path)
                parsed = parser.parse(source_path)
                await finish_stage(session, parsing, {"parser": parser.name, "block_count": len(parsed["blocks"])})

                quality_check = await start_stage(session, job, "QUALITY_CHECK", 30)
                quality_report = build_quality_report(parsed)
                if quality_report["empty"]:
                    raise ValueError("Document contains no readable text")
                await finish_stage(session, quality_check, quality_report)

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
            return
        except Exception as error:
            await session.rollback()
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
