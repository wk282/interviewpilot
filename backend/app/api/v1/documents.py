import asyncio
import hashlib
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import delete as sql_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.permissions import require_workspace_role
from app.services.bm25_store import OpenSearchBM25Store
from app.db.models.chunk import DocumentChunk
from app.db.models.document import Document, DocumentVersion
from app.db.models.ingestion import IngestionJob
from app.db.models.knowledge_base import KnowledgeBase
from app.db.models.recruitment import ApplicationResume
from app.db.models.user import AppUser
from app.db.session import get_db_session
from app.schemas.document import DocumentResponse
from app.schemas.ingestion import IngestionRetryRequest
from app.workers.ingestion_tasks import process_document
from app.core.logger import logger


router = APIRouter(
    prefix="/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}/documents",
    tags=["文档"],
)

ALL_ROLES = {"OWNER", "ADMIN", "HR", "INTERVIEWER", "VIEWER"}
MANAGER_ROLES = {"OWNER", "ADMIN"}
ALLOWED_EXTENSIONS = {
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


async def get_accessible_knowledge_base(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    user: AppUser,
    write: bool = False,
) -> KnowledgeBase:
    _, membership = await require_workspace_role(
        session,
        workspace_id,
        user.id,
        MANAGER_ROLES if write else ALL_ROLES,
    )
    knowledge_base = await session.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.workspace_id == workspace_id,
        )
    )
    if knowledge_base is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    if (
        not write
        and knowledge_base.visibility == "PRIVATE"
        and membership.role not in MANAGER_ROLES
        and knowledge_base.created_by != user.id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    return knowledge_base


def to_response(
    document: Document,
    version: DocumentVersion,
    job: IngestionJob,
) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        knowledge_base_id=document.knowledge_base_id,
        name=document.name,
        status=document.status,
        original_filename=version.original_filename,
        mime_type=version.mime_type,
        file_size=version.file_size,
        file_hash=version.file_hash,
        version_number=version.version_number,
        ingestion_job_id=job.id,
        ingestion_status=job.status,
        ingestion_stage=job.current_stage,
        ingestion_progress=job.progress,
        created_at=document.created_at,
    )


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    workspace_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[DocumentResponse]:
    await get_accessible_knowledge_base(
        session, workspace_id, knowledge_base_id, current_user
    )
    rows = (
        await session.execute(
            select(Document, DocumentVersion, IngestionJob)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .join(IngestionJob, IngestionJob.document_version_id == DocumentVersion.id)
            .where(
                Document.knowledge_base_id == knowledge_base_id,
                Document.status != "DELETED",
            )
            .order_by(Document.created_at.desc(), IngestionJob.created_at.desc())
        )
    ).all()
    return [to_response(document, version, job) for document, version, job in rows]


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    workspace_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentResponse:
    await get_accessible_knowledge_base(
        session, workspace_id, knowledge_base_id, current_user, write=True
    )

    original_filename = Path(file.filename or "").name
    extension = Path(original_filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="仅支持 PDF、DOCX、Markdown 和 TXT 文件",
        )

    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    relative_path = Path(str(workspace_id)) / str(knowledge_base_id) / str(document_id) / "v1" / f"original{extension}"
    target_path = Path(settings.DOCUMENT_STORAGE_ROOT).resolve() / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256()
    file_size = 0
    max_bytes = settings.DOCUMENT_MAX_FILE_SIZE_MB * 1024 * 1024
    try:
        with target_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                file_size += len(chunk)
                if file_size > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"文件不能超过 {settings.DOCUMENT_MAX_FILE_SIZE_MB} MB",
                    )
                digest.update(chunk)
                output.write(chunk)
        if file_size == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能上传空文件")

        file_hash = digest.hexdigest()
        duplicate = await session.scalar(
            select(DocumentVersion)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                Document.knowledge_base_id == knowledge_base_id,
                Document.status != "DELETED",
                DocumentVersion.file_hash == file_hash,
            )
            .limit(1)
        )
        if duplicate is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"相同文件已存在：{duplicate.original_filename}",
            )

        document = Document(
            id=document_id,
            knowledge_base_id=knowledge_base_id,
            name=Path(original_filename).stem,
            uploaded_by=current_user.id,
        )
        version = DocumentVersion(
            id=version_id,
            document_id=document_id,
            version_number=1,
            original_filename=original_filename,
            storage_key=relative_path.as_posix(),
            mime_type=ALLOWED_EXTENSIONS[extension],
            file_size=file_size,
            file_hash=file_hash,
        )
        job = IngestionJob(
            document_version_id=version_id,
            requested_by=current_user.id,
            status="PENDING",
            current_stage="VALIDATION",
            progress=0,
        )
        session.add_all([document, version, job])
        await session.commit()
        await session.refresh(document)
        await session.refresh(job)
        try:
            process_document.delay(str(job.id))
        except Exception as queue_error:
            job.status = "FAILED"
            job.error_code = "QUEUE_UNAVAILABLE"
            job.error_message = str(queue_error)[:2000]
            document.status = "FAILED"
            version.status = "FAILED"
            await session.commit()
        return to_response(document, version, job)
    except Exception:
        await session.rollback()
        target_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    workspace_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await get_accessible_knowledge_base(
        session, workspace_id, knowledge_base_id, current_user, write=True
    )
    document = await session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.knowledge_base_id == knowledge_base_id,
            Document.status != "DELETED",
        )
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    application_resume_id = await session.scalar(
        select(ApplicationResume.id).where(
            ApplicationResume.snapshot_document_id == document.id
        ).limit(1)
    )
    if application_resume_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="岗位申请简历快照不能从文档页面删除",
        )

    running_job = await session.scalar(
        select(IngestionJob)
        .join(DocumentVersion, DocumentVersion.id == IngestionJob.document_version_id)
        .where(
            DocumentVersion.document_id == document_id,
            IngestionJob.status == "RUNNING",
        )
        .limit(1)
    )
    if running_job is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="任务正在执行，请等待完成或失败后再删除",
        )

    await session.execute(sql_delete(Document).where(Document.id == document_id))
    await session.commit()

    if settings.OPENSEARCH_URL:
        try:
            await asyncio.to_thread(OpenSearchBM25Store().delete_by_document, document_id)
        except Exception as error:
            logger.warning(f"Failed to remove BM25 index for document {document_id}: {error}")

    document_directory = (
        Path(settings.DOCUMENT_STORAGE_ROOT).resolve()
        / str(workspace_id)
        / str(knowledge_base_id)
        / str(document_id)
    )
    try:
        shutil.rmtree(document_directory, ignore_errors=False)
    except FileNotFoundError:
        pass
    except OSError as error:
        logger.warning(f"Failed to remove document files for {document_id}: {error}")


@router.post("/{document_id}/process", response_model=DocumentResponse)
async def resume_document_processing(
    workspace_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentResponse:
    await get_accessible_knowledge_base(
        session, workspace_id, knowledge_base_id, current_user, write=True
    )
    row = (
        await session.execute(
            select(Document, DocumentVersion, IngestionJob)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .join(IngestionJob, IngestionJob.document_version_id == DocumentVersion.id)
            .where(
                Document.id == document_id,
                Document.knowledge_base_id == knowledge_base_id,
                Document.status != "DELETED",
            )
            .order_by(DocumentVersion.version_number.desc(), IngestionJob.created_at.desc())
            .limit(1)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    document, version, job = row
    resumable_stages = {"CHUNKING", "EMBEDDING"}
    if Path(version.storage_key).suffix.lower() == ".docx":
        resumable_stages.add("PARSING")
    if job.status != "PENDING" or job.current_stage not in resumable_stages:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="只有等待解析、切分或向量化的任务可以继续处理",
        )
    try:
        process_document.delay(str(job.id))
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"任务队列不可用：{error}",
        )
    return to_response(document, version, job)


@router.post("/{document_id}/retry", response_model=DocumentResponse)
async def retry_document_processing(
    workspace_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    document_id: uuid.UUID,
    request: IngestionRetryRequest,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentResponse:
    await get_accessible_knowledge_base(
        session, workspace_id, knowledge_base_id, current_user, write=True
    )
    row = (
        await session.execute(
            select(Document, DocumentVersion, IngestionJob)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .join(IngestionJob, IngestionJob.document_version_id == DocumentVersion.id)
            .where(
                Document.id == document_id,
                Document.knowledge_base_id == knowledge_base_id,
                Document.status != "DELETED",
            )
            .order_by(DocumentVersion.version_number.desc(), IngestionJob.created_at.desc())
            .limit(1)
            .with_for_update()
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    document, version, job = row
    if job.status == "RUNNING":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务正在执行")

    child_chunks = list(
        (
            await session.scalars(
                select(DocumentChunk).where(
                    DocumentChunk.document_version_id == version.id,
                    DocumentChunk.chunk_type == "CHILD",
                )
            )
        ).all()
    )

    if request.mode == "REEMBED":
        if not child_chunks:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="文档尚未生成可向量化的子块")
        restart_stage = "EMBEDDING"
        restart_progress = 60
        for chunk in child_chunks:
            chunk.embedding = None
            chunk.embedding_model = None
            chunk.embedded_at = None
    else:
        if job.status != "FAILED":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有失败任务可以自动重试")
        if job.current_stage in {"EMBEDDING", "INDEXING"} and child_chunks:
            restart_stage = "EMBEDDING"
            restart_progress = 60
        elif version.parsed_content_key:
            restart_stage = "CHUNKING"
            restart_progress = 45
        else:
            restart_stage = "VALIDATION"
            restart_progress = 0

    job.status = "PENDING"
    job.current_stage = restart_stage
    job.progress = restart_progress
    job.retry_count += 1
    job.error_code = None
    job.error_message = None
    job.completed_at = None
    document.status = "PROCESSING"
    version.status = "PROCESSING"
    await session.commit()

    try:
        process_document.delay(str(job.id))
    except Exception as error:
        job.status = "FAILED"
        job.error_code = "QUEUE_UNAVAILABLE"
        job.error_message = str(error)[:2000]
        job.completed_at = datetime.now(timezone.utc)
        document.status = "FAILED"
        version.status = "FAILED"
        await session.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="任务队列不可用")

    return to_response(document, version, job)
