import asyncio
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete as sql_delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.logger import logger
from app.core.permissions import require_workspace_role
from app.services.bm25_store import OpenSearchBM25Store
from app.db.models.document import Document, DocumentVersion
from app.db.models.ingestion import IngestionJob
from app.db.models.knowledge_base import KnowledgeBase
from app.db.models.recruitment import ApplicationResume
from app.db.models.user import AppUser
from app.db.session import get_db_session
from app.schemas.knowledge_base import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseRenameRequest,
    KnowledgeBaseResponse,
)


router = APIRouter(prefix="/workspaces/{workspace_id}/knowledge-bases", tags=["知识库"])

PERSONAL_PURPOSES = {"RESUME", "PERSONAL_LEARNING", "JOB_SPECIFIC"}
ORGANIZATION_PURPOSES = {
    "RESUME",
    "ENTERPRISE_QUESTION_BANK",
    "JOB_SPECIFIC",
    "SCORING_RUBRIC",
    "TECHNICAL_STANDARD",
}
ALL_ROLES = {"OWNER", "ADMIN", "HR", "INTERVIEWER", "VIEWER"}
MANAGER_ROLES = {"OWNER", "ADMIN"}


@router.get("", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases(
    workspace_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[KnowledgeBase]:
    _, membership = await require_workspace_role(
        session, workspace_id, current_user.id, ALL_ROLES
    )

    query = select(KnowledgeBase).where(KnowledgeBase.workspace_id == workspace_id)
    if membership.role not in MANAGER_ROLES:
        query = query.where(
            or_(
                KnowledgeBase.visibility == "WORKSPACE",
                KnowledgeBase.created_by == current_user.id,
            )
        )
    return list((await session.scalars(query.order_by(KnowledgeBase.created_at.desc()))).all())


@router.post("", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    workspace_id: uuid.UUID,
    request: KnowledgeBaseCreateRequest,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> KnowledgeBase:
    workspace, _ = await require_workspace_role(
        session, workspace_id, current_user.id, MANAGER_ROLES
    )
    allowed_purposes = PERSONAL_PURPOSES if workspace.type == "PERSONAL" else ORGANIZATION_PURPOSES
    if request.purpose not in allowed_purposes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该知识库用途不适用于当前工作空间",
        )

    knowledge_base = KnowledgeBase(
        workspace_id=workspace_id,
        name=request.name.strip(),
        purpose=request.purpose,
        visibility=request.visibility,
        created_by=current_user.id,
    )
    session.add(knowledge_base)
    try:
        await session.commit()
        await session.refresh(knowledge_base)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="知识库名称已存在")
    return knowledge_base


@router.patch("/{knowledge_base_id}", response_model=KnowledgeBaseResponse)
async def rename_knowledge_base(
    workspace_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    request: KnowledgeBaseRenameRequest,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> KnowledgeBase:
    await require_workspace_role(session, workspace_id, current_user.id, MANAGER_ROLES)
    knowledge_base = await session.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.workspace_id == workspace_id,
        )
    )
    if knowledge_base is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")

    managed_resume_id = await session.scalar(
        select(ApplicationResume.id)
        .join(Document, Document.id == ApplicationResume.snapshot_document_id)
        .where(Document.knowledge_base_id == knowledge_base_id)
        .limit(1)
    )
    if managed_resume_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="岗位申请简历快照知识库由系统管理，不能改名",
        )

    name = request.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="知识库名称不能为空",
        )
    knowledge_base.name = name
    try:
        await session.commit()
        await session.refresh(knowledge_base)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="知识库名称已存在",
        )
    return knowledge_base


@router.delete("/{knowledge_base_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base(
    workspace_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_workspace_role(session, workspace_id, current_user.id, MANAGER_ROLES)
    knowledge_base = await session.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.workspace_id == workspace_id,
        )
    )
    if knowledge_base is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")

    application_resume_id = await session.scalar(
        select(ApplicationResume.id)
        .join(Document, Document.id == ApplicationResume.snapshot_document_id)
        .where(Document.knowledge_base_id == knowledge_base_id)
        .limit(1)
    )
    if application_resume_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="包含岗位申请简历快照的知识库不能删除",
        )

    running_job_id = await session.scalar(
        select(IngestionJob.id)
        .join(DocumentVersion, DocumentVersion.id == IngestionJob.document_version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(
            Document.knowledge_base_id == knowledge_base_id,
            IngestionJob.status == "RUNNING",
        )
        .limit(1)
    )
    if running_job_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="知识库中仍有文档正在处理，请等待任务完成或失败后再删除",
        )

    await session.execute(
        sql_delete(KnowledgeBase).where(KnowledgeBase.id == knowledge_base_id)
    )
    await session.commit()

    if settings.OPENSEARCH_URL:
        try:
            await asyncio.to_thread(
                OpenSearchBM25Store().delete_by_knowledge_base,
                knowledge_base_id,
            )
        except Exception as error:
            logger.warning(
                f"Failed to remove BM25 index for knowledge base {knowledge_base_id}: {error}"
            )

    knowledge_base_directory = (
        Path(settings.DOCUMENT_STORAGE_ROOT).resolve()
        / str(workspace_id)
        / str(knowledge_base_id)
    )
    try:
        shutil.rmtree(knowledge_base_directory, ignore_errors=False)
    except FileNotFoundError:
        pass
    except OSError as error:
        logger.warning(
            f"Failed to remove knowledge base files for {knowledge_base_id}: {error}"
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
