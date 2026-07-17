import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import and_, delete as sql_delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.dependencies import get_current_user
from app.api.v1.interviews import (
    READ_ROLES,
    WRITE_ROLES,
    generate_and_activate_next_question,
    question_has_timed_out,
    runtime_response,
    session_response,
)
from app.core.config import settings
from app.core.logger import logger
from app.core.permissions import require_workspace_role
from app.db.models.document import Document, DocumentVersion
from app.db.models.ingestion import IngestionJob
from app.db.models.interview import (
    CandidateProfile,
    InterviewAnswer,
    InterviewQuestion,
    InterviewSession,
    JobPosition,
)
from app.db.models.interview_decision import InterviewDecision
from app.db.models.knowledge_base import KnowledgeBase
from app.db.models.recruitment import (
    ApplicationResume,
    JobApplication,
    MessageRead,
    MessageThread,
    PlatformMessage,
)
from app.db.models.user import AppUser
from app.db.models.workspace import Workspace, WorkspaceMember
from app.db.session import get_db_session
from app.schemas.interview import (
    InterviewAnswerSubmitRequest,
    InterviewRuntimeResponse,
    InterviewSessionResponse,
)
from app.schemas.recruitment import (
    ApplicationInterviewCreateRequest,
    ApplicationStatusUpdateRequest,
    InterviewDecisionRequest,
    InterviewDecisionResponse,
    JobApplicationCreateRequest,
    JobApplicationResponse,
    MessageCreateRequest,
    MessageResponse,
    MessageThreadResponse,
    PublishedJobResponse,
)
from app.workers.ingestion_tasks import process_document
from app.services.evaluation_lifecycle import enqueue_interview_evaluation


router = APIRouter(tags=["岗位申请与站内消息"])
APPLICATION_RESUME_KB_NAME = "候选人投递简历"
MESSAGE_SEND_ROLES = {"OWNER", "ADMIN", "HR", "INTERVIEWER"}


async def personal_resume_source(
    session: AsyncSession,
    user: AppUser,
    document_id: uuid.UUID,
) -> tuple[Document, DocumentVersion, CandidateProfile]:
    row = (
        await session.execute(
            select(Document, DocumentVersion, CandidateProfile)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
            .join(Workspace, Workspace.id == KnowledgeBase.workspace_id)
            .join(
                WorkspaceMember,
                and_(
                    WorkspaceMember.workspace_id == Workspace.id,
                    WorkspaceMember.user_id == user.id,
                ),
            )
            .join(
                CandidateProfile,
                and_(
                    CandidateProfile.workspace_id == Workspace.id,
                    CandidateProfile.user_id == user.id,
                    CandidateProfile.source == "PERSONAL_ACCOUNT",
                ),
            )
            .where(
                Document.id == document_id,
                Document.status == "READY",
                DocumentVersion.status == "READY",
                KnowledgeBase.purpose == "RESUME",
                Workspace.type == "PERSONAL",
            )
            .order_by(DocumentVersion.version_number.desc())
            .limit(1)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请选择本人已解析完成的简历",
        )
    return row


async def ensure_application_resume_base(
    session: AsyncSession,
    workspace: Workspace,
    created_by: uuid.UUID,
) -> KnowledgeBase:
    await session.execute(
        select(Workspace.id).where(Workspace.id == workspace.id).with_for_update()
    )
    knowledge_base = await session.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.workspace_id == workspace.id,
            KnowledgeBase.name == APPLICATION_RESUME_KB_NAME,
        )
    )
    if knowledge_base is None:
        knowledge_base = KnowledgeBase(
            workspace_id=workspace.id,
            name=APPLICATION_RESUME_KB_NAME,
            purpose="RESUME",
            visibility="WORKSPACE",
            created_by=created_by,
        )
        session.add(knowledge_base)
        await session.flush()
    return knowledge_base


async def application_response(
    session: AsyncSession,
    application: JobApplication,
    *,
    include_internal: bool = False,
) -> JobApplicationResponse:
    workspace = await session.get(Workspace, application.workspace_id)
    position = await session.get(JobPosition, application.job_position_id)
    candidate = await session.get(CandidateProfile, application.candidate_profile_id)
    user = await session.get(AppUser, application.candidate_user_id)
    snapshot = await session.scalar(
        select(ApplicationResume).where(
            ApplicationResume.application_id == application.id
        )
    )
    thread = await session.scalar(
        select(MessageThread).where(MessageThread.application_id == application.id)
    )
    resume_document = (
        await session.get(Document, snapshot.snapshot_document_id)
        if snapshot and snapshot.snapshot_document_id
        else None
    )
    interview = await session.scalar(
        select(InterviewSession)
        .where(InterviewSession.application_id == application.id)
        .order_by(InterviewSession.created_at.desc())
        .limit(1)
    )
    if not all((workspace, position, candidate, user, snapshot, thread)):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="岗位申请数据不完整",
        )
    decision_user = (
        await session.get(AppUser, application.decided_by)
        if include_internal and application.decided_by
        else None
    )
    return JobApplicationResponse(
        id=application.id,
        workspace_id=application.workspace_id,
        workspace_name=workspace.name,
        job_position_id=application.job_position_id,
        job_title=position.title,
        candidate_user_id=application.candidate_user_id,
        candidate_profile_id=application.candidate_profile_id,
        candidate_name=candidate.full_name,
        candidate_email=user.email,
        candidate_phone=candidate.phone,
        candidate_profile_data=candidate.profile_data,
        status=application.status,
        cover_letter=application.cover_letter,
        resume_document_id=snapshot.snapshot_document_id,
        resume_filename=snapshot.original_filename,
        resume_status=resume_document.status if resume_document else None,
        interview_session_id=interview.id if interview else None,
        interview_status=interview.status if interview else None,
        thread_id=thread.id,
        submitted_at=application.submitted_at,
        reviewed_at=application.reviewed_at,
        withdrawn_at=application.withdrawn_at,
        decision_note=application.decision_note if include_internal else None,
        decided_by=application.decided_by if include_internal else None,
        decided_by_name=(
            decision_user.display_name or decision_user.email
            if decision_user
            else None
        ),
        decided_at=application.decided_at if include_internal else None,
        created_at=application.created_at,
        updated_at=application.updated_at,
    )


def create_system_message(
    thread: MessageThread,
    content: str,
    *,
    message_type: str = "APPLICATION_STATUS",
    interview_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> PlatformMessage:
    thread.updated_at = datetime.now(timezone.utc)
    return PlatformMessage(
        thread_id=thread.id,
        sender_type="SYSTEM",
        sender_user_id=None,
        message_type=message_type,
        interview_session_id=interview_id,
        content=content,
        message_metadata=metadata or {},
    )


async def interview_decision_response(
    session: AsyncSession,
    interview: InterviewSession,
    application: JobApplication | None = None,
) -> InterviewDecisionResponse:
    decision = await session.scalar(
        select(InterviewDecision).where(
            InterviewDecision.interview_session_id == interview.id
        )
    )
    decision_user = (
        await session.get(AppUser, decision.decided_by)
        if decision is not None and decision.decided_by
        else None
    )
    return InterviewDecisionResponse(
        interview_session_id=interview.id,
        application_id=application.id if application else None,
        application_status=application.status if application else None,
        decision=decision.decision if decision else None,
        internal_note=decision.internal_note if decision else None,
        decided_by=decision.decided_by if decision else None,
        decided_by_name=(
            decision_user.display_name or decision_user.email
            if decision_user
            else None
        ),
        decided_at=decision.decided_at if decision else None,
    )


@router.get("/candidate/jobs", response_model=list[PublishedJobResponse])
async def list_published_jobs(
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[PublishedJobResponse]:
    applied_position_ids = set(
        (
            await session.scalars(
                select(JobApplication.job_position_id).where(
                    JobApplication.candidate_user_id == current_user.id
                )
            )
        ).all()
    )
    rows = (
        await session.execute(
            select(JobPosition, Workspace)
            .join(Workspace, Workspace.id == JobPosition.workspace_id)
            .where(
                JobPosition.status == "ACTIVE",
                Workspace.type == "ORGANIZATION",
            )
            .order_by(JobPosition.created_at.desc())
        )
    ).all()
    return [
        PublishedJobResponse(
            id=position.id,
            workspace_id=workspace.id,
            workspace_name=workspace.name,
            title=position.title,
            department=position.department,
            description=position.description,
            requirements=position.requirements,
            created_at=position.created_at,
            applied=position.id in applied_position_ids,
        )
        for position, workspace in rows
    ]


@router.post(
    "/candidate/applications",
    response_model=JobApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_job_application(
    request: JobApplicationCreateRequest,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> JobApplicationResponse:
    row = (
        await session.execute(
            select(JobPosition, Workspace)
            .join(Workspace, Workspace.id == JobPosition.workspace_id)
            .where(
                JobPosition.id == request.job_position_id,
                JobPosition.status == "ACTIVE",
                Workspace.type == "ORGANIZATION",
            )
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="招聘岗位不存在或已关闭")
    position, workspace = row
    position_id = position.id
    candidate_user_id = current_user.id
    existing = await session.scalar(
        select(JobApplication).where(
            JobApplication.job_position_id == position_id,
            JobApplication.candidate_user_id == candidate_user_id,
        )
    )
    if existing is not None:
        return await application_response(session, existing)

    source_document, source_version, personal_profile = await personal_resume_source(
        session, current_user, request.resume_document_id
    )
    destination_base = await ensure_application_resume_base(
        session, workspace, position.created_by
    )
    application_id = uuid.uuid4()
    candidate_profile_id = uuid.uuid4()
    snapshot_document_id = uuid.uuid4()
    snapshot_version_id = uuid.uuid4()
    extension = Path(source_version.original_filename).suffix.lower()
    relative_path = (
        Path(str(workspace.id))
        / str(destination_base.id)
        / str(snapshot_document_id)
        / "v1"
        / f"original{extension}"
    )
    storage_root = Path(settings.DOCUMENT_STORAGE_ROOT).resolve()
    source_path = (storage_root / source_version.storage_key).resolve()
    target_path = storage_root / relative_path
    if storage_root not in source_path.parents or not source_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="原简历文件不存在，请重新上传后再投递",
        )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)

    candidate = CandidateProfile(
        id=candidate_profile_id,
        workspace_id=workspace.id,
        user_id=None,
        resume_knowledge_base_id=destination_base.id,
        resume_document_id=snapshot_document_id,
        full_name=personal_profile.full_name,
        email=current_user.email,
        phone=personal_profile.phone,
        source="ENTERPRISE_IMPORT",
        status="ACTIVE",
        profile_data={
            **personal_profile.profile_data,
            "application_id": str(application_id),
            "candidate_user_id": str(candidate_user_id),
        },
        created_by=candidate_user_id,
    )
    application = JobApplication(
        id=application_id,
        workspace_id=workspace.id,
        job_position_id=position_id,
        candidate_user_id=candidate_user_id,
        candidate_profile_id=candidate_profile_id,
        cover_letter=request.cover_letter.strip() if request.cover_letter else None,
    )
    snapshot_document = Document(
        id=snapshot_document_id,
        knowledge_base_id=destination_base.id,
        name=f"{personal_profile.full_name}-{position.title}",
        uploaded_by=candidate_user_id,
    )
    snapshot_version = DocumentVersion(
        id=snapshot_version_id,
        document_id=snapshot_document_id,
        version_number=1,
        original_filename=source_version.original_filename,
        storage_key=relative_path.as_posix(),
        mime_type=source_version.mime_type,
        file_size=source_version.file_size,
        file_hash=source_version.file_hash,
    )
    ingestion_job = IngestionJob(
        document_version_id=snapshot_version_id,
        requested_by=candidate_user_id,
        status="PENDING",
        current_stage="VALIDATION",
        progress=0,
    )
    snapshot = ApplicationResume(
        application_id=application_id,
        source_document_id=source_document.id,
        snapshot_document_id=snapshot_document_id,
        original_filename=source_version.original_filename,
        file_hash=source_version.file_hash,
    )
    thread = MessageThread(
        application_id=application_id,
        workspace_id=workspace.id,
        candidate_user_id=candidate_user_id,
        subject=f"{workspace.name} · {position.title}",
    )
    try:
        session.add(snapshot_document)
        await session.flush()
        session.add(snapshot_version)
        await session.flush()
        session.add(ingestion_job)
        await session.flush()
        session.add(candidate)
        await session.flush()
        session.add(application)
        await session.flush()
        session.add_all([snapshot, thread])
        await session.flush()
        session.add(
            create_system_message(
                thread,
                f"已向 {workspace.name} 提交 {position.title} 岗位申请。",
                metadata={"application_status": "SUBMITTED"},
            )
        )
        await session.commit()
        await session.refresh(application)
    except IntegrityError as error:
        logger.error(f"Job application persistence conflict: {error.orig}")
        await session.rollback()
        shutil.rmtree(target_path.parent.parent, ignore_errors=True)
        existing = await session.scalar(
            select(JobApplication).where(
                JobApplication.job_position_id == position_id,
                JobApplication.candidate_user_id == candidate_user_id,
            )
        )
        if existing is not None:
            return await application_response(session, existing)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="投递数据发生冲突，请刷新页面后重试",
        ) from error
    except Exception:
        await session.rollback()
        shutil.rmtree(target_path.parent.parent, ignore_errors=True)
        raise

    try:
        process_document.delay(str(ingestion_job.id))
    except Exception as queue_error:
        ingestion_job.status = "FAILED"
        ingestion_job.error_code = "QUEUE_UNAVAILABLE"
        ingestion_job.error_message = str(queue_error)[:2000]
        snapshot_document.status = "FAILED"
        snapshot_version.status = "FAILED"
        await session.commit()
    return await application_response(session, application)


@router.get("/candidate/applications", response_model=list[JobApplicationResponse])
async def list_candidate_applications(
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[JobApplicationResponse]:
    applications = list(
        (
            await session.scalars(
                select(JobApplication)
                .where(JobApplication.candidate_user_id == current_user.id)
                .order_by(JobApplication.created_at.desc())
            )
        ).all()
    )
    return [await application_response(session, item) for item in applications]


@router.post(
    "/candidate/applications/{application_id}/withdraw",
    response_model=JobApplicationResponse,
)
async def withdraw_job_application(
    application_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> JobApplicationResponse:
    application = await session.scalar(
        select(JobApplication)
        .where(
            JobApplication.id == application_id,
            JobApplication.candidate_user_id == current_user.id,
        )
        .with_for_update()
    )
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="岗位申请不存在")
    if application.status not in {"SUBMITTED", "REVIEWING"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前申请状态不能撤回")
    application.status = "WITHDRAWN"
    application.withdrawn_at = datetime.now(timezone.utc)
    thread = await session.scalar(
        select(MessageThread).where(MessageThread.application_id == application.id)
    )
    if thread:
        session.add(
            create_system_message(
                thread,
                "候选人已撤回岗位申请。",
                metadata={"application_status": "WITHDRAWN"},
            )
        )
    await session.commit()
    await session.refresh(application)
    return await application_response(session, application)


@router.get(
    "/workspaces/{workspace_id}/applications",
    response_model=list[JobApplicationResponse],
)
async def list_enterprise_applications(
    workspace_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[JobApplicationResponse]:
    await require_workspace_role(session, workspace_id, current_user.id, WRITE_ROLES)
    applications = list(
        (
            await session.scalars(
                select(JobApplication)
                .where(JobApplication.workspace_id == workspace_id)
                .order_by(JobApplication.created_at.desc())
            )
        ).all()
    )
    return [
        await application_response(session, item, include_internal=True)
        for item in applications
    ]


@router.get("/workspaces/{workspace_id}/applications/{application_id}/resume")
async def download_application_resume(
    workspace_id: uuid.UUID,
    application_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> FileResponse:
    await require_workspace_role(session, workspace_id, current_user.id, WRITE_ROLES)
    row = (
        await session.execute(
            select(ApplicationResume, DocumentVersion)
            .join(
                DocumentVersion,
                DocumentVersion.document_id == ApplicationResume.snapshot_document_id,
            )
            .join(JobApplication, JobApplication.id == ApplicationResume.application_id)
            .where(
                ApplicationResume.application_id == application_id,
                JobApplication.workspace_id == workspace_id,
            )
            .order_by(DocumentVersion.version_number.desc())
            .limit(1)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="投递简历不存在")
    snapshot, version = row
    storage_root = Path(settings.DOCUMENT_STORAGE_ROOT).resolve()
    file_path = (storage_root / version.storage_key).resolve()
    if storage_root not in file_path.parents or not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="投递简历文件不存在")
    return FileResponse(
        path=file_path,
        media_type=version.mime_type,
        filename=snapshot.original_filename,
    )


@router.patch(
    "/workspaces/{workspace_id}/applications/{application_id}/status",
    response_model=JobApplicationResponse,
)
async def update_application_status(
    workspace_id: uuid.UUID,
    application_id: uuid.UUID,
    request: ApplicationStatusUpdateRequest,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> JobApplicationResponse:
    await require_workspace_role(session, workspace_id, current_user.id, WRITE_ROLES)
    application = await session.scalar(
        select(JobApplication)
        .where(
            JobApplication.id == application_id,
            JobApplication.workspace_id == workspace_id,
        )
        .with_for_update()
    )
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="岗位申请不存在")
    if application.status in {"WITHDRAWN", "REJECTED", "HIRED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前申请已进入终态")
    if request.status == "REVIEWING" and application.status != "SUBMITTED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前申请已经开始处理")
    completed_interview = await session.scalar(
        select(InterviewSession)
        .where(
            InterviewSession.application_id == application.id,
            InterviewSession.status == "COMPLETED",
        )
        .order_by(InterviewSession.created_at.desc())
        .limit(1)
    )
    if request.status == "HIRED" and completed_interview is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="面试完成后才能标记录用")
    application.status = request.status
    application.reviewed_at = application.reviewed_at or datetime.now(timezone.utc)
    if request.status in {"REJECTED", "HIRED"}:
        normalized_note = (request.decision_note or "").strip() or None
        application.decision_note = normalized_note
        application.decided_by = current_user.id
        application.decided_at = datetime.now(timezone.utc)
        if completed_interview is not None:
            existing_decision = await session.scalar(
                select(InterviewDecision).where(
                    InterviewDecision.interview_session_id == completed_interview.id
                )
            )
            if existing_decision is None:
                session.add(
                    InterviewDecision(
                        interview_session_id=completed_interview.id,
                        decision=request.status,
                        internal_note=normalized_note,
                        decided_by=current_user.id,
                        decided_at=application.decided_at,
                    )
                )
    thread = await session.scalar(
        select(MessageThread).where(MessageThread.application_id == application.id)
    )
    labels = {"REVIEWING": "企业正在审核你的岗位申请。", "REJECTED": "本次岗位申请未进入下一阶段。", "HIRED": "企业已将申请标记为录用。"}
    if thread:
        session.add(
            create_system_message(
                thread,
                labels[request.status],
                metadata={"application_status": request.status},
            )
        )
    await session.commit()
    await session.refresh(application)
    return await application_response(session, application, include_internal=True)


@router.get(
    "/workspaces/{workspace_id}/interviews/{interview_id}/application",
    response_model=JobApplicationResponse,
)
async def get_interview_application(
    workspace_id: uuid.UUID,
    interview_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> JobApplicationResponse:
    await require_workspace_role(session, workspace_id, current_user.id, WRITE_ROLES)
    application = await session.scalar(
        select(JobApplication)
        .join(
            InterviewSession,
            InterviewSession.application_id == JobApplication.id,
        )
        .where(
            InterviewSession.id == interview_id,
            InterviewSession.workspace_id == workspace_id,
            JobApplication.workspace_id == workspace_id,
        )
    )
    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该面试没有关联岗位申请",
        )
    return await application_response(session, application, include_internal=True)


@router.get(
    "/workspaces/{workspace_id}/interviews/{interview_id}/decision",
    response_model=InterviewDecisionResponse,
)
async def get_interview_decision(
    workspace_id: uuid.UUID,
    interview_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewDecisionResponse:
    await require_workspace_role(session, workspace_id, current_user.id, WRITE_ROLES)
    interview = await session.scalar(
        select(InterviewSession).where(
            InterviewSession.id == interview_id,
            InterviewSession.workspace_id == workspace_id,
            InterviewSession.mode == "ENTERPRISE",
        )
    )
    if interview is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="企业面试不存在")
    application = (
        await session.get(JobApplication, interview.application_id)
        if interview.application_id
        else None
    )
    return await interview_decision_response(session, interview, application)


@router.post(
    "/workspaces/{workspace_id}/interviews/{interview_id}/decision",
    response_model=InterviewDecisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_interview_decision(
    workspace_id: uuid.UUID,
    interview_id: uuid.UUID,
    request: InterviewDecisionRequest,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewDecisionResponse:
    await require_workspace_role(session, workspace_id, current_user.id, WRITE_ROLES)
    interview = await session.scalar(
        select(InterviewSession)
        .where(
            InterviewSession.id == interview_id,
            InterviewSession.workspace_id == workspace_id,
            InterviewSession.mode == "ENTERPRISE",
        )
        .with_for_update()
    )
    if interview is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="企业面试不存在")
    if interview.status != "COMPLETED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="面试完成后才能作出决策")
    existing = await session.scalar(
        select(InterviewDecision).where(
            InterviewDecision.interview_session_id == interview.id
        )
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该面试已经作出决策")

    application = (
        await session.get(JobApplication, interview.application_id)
        if interview.application_id
        else None
    )
    if application is not None and application.status in {"WITHDRAWN", "REJECTED", "HIRED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="关联申请已进入终态")

    now = datetime.now(timezone.utc)
    normalized_note = (request.internal_note or "").strip() or None
    session.add(
        InterviewDecision(
            interview_session_id=interview.id,
            decision=request.decision,
            internal_note=normalized_note,
            decided_by=current_user.id,
            decided_at=now,
        )
    )
    if application is not None:
        application.status = request.decision
        application.decision_note = normalized_note
        application.decided_by = current_user.id
        application.decided_at = now
        application.reviewed_at = application.reviewed_at or now
        thread = await session.scalar(
            select(MessageThread).where(MessageThread.application_id == application.id)
        )
        if thread is not None:
            content = (
                "企业已将申请标记为录用。"
                if request.decision == "HIRED"
                else "本次岗位申请未进入下一阶段。"
            )
            session.add(
                create_system_message(
                    thread,
                    content,
                    metadata={"application_status": request.decision},
                )
            )
    await session.commit()
    return await interview_decision_response(session, interview, application)


@router.post(
    "/workspaces/{workspace_id}/applications/{application_id}/interview",
    response_model=InterviewSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_application_interview(
    workspace_id: uuid.UUID,
    application_id: uuid.UUID,
    request: ApplicationInterviewCreateRequest,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewSessionResponse:
    await require_workspace_role(session, workspace_id, current_user.id, WRITE_ROLES)
    application = await session.scalar(
        select(JobApplication)
        .where(
            JobApplication.id == application_id,
            JobApplication.workspace_id == workspace_id,
        )
        .with_for_update()
    )
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="岗位申请不存在")
    if application.status in {"REJECTED", "WITHDRAWN"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前申请不能创建面试")
    existing = await session.scalar(
        select(InterviewSession).where(InterviewSession.application_id == application.id).limit(1)
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该申请已经创建面试")
    candidate = await session.get(CandidateProfile, application.candidate_profile_id)
    position = await session.get(JobPosition, application.job_position_id)
    if candidate is None or position is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="申请关联数据不完整")
    resume = await session.get(Document, candidate.resume_document_id)
    if resume is None or resume.status != "READY":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="投递简历尚未处理完成")
    interview = InterviewSession(
        workspace_id=workspace_id,
        job_position_id=position.id,
        candidate_profile_id=candidate.id,
        application_id=application.id,
        interviewer_id=None,
        mode="ENTERPRISE",
        status="DRAFT",
        scheduled_at=request.scheduled_at,
        configuration={
            "reference_knowledge_base_ids": [],
            "max_question_count": request.max_question_count,
            "question_time_limit_minutes": request.question_time_limit_minutes,
        },
        created_by=current_user.id,
    )
    application.status = "REVIEWING"
    application.reviewed_at = application.reviewed_at or datetime.now(timezone.utc)
    session.add(interview)
    await session.flush()
    thread = await session.scalar(
        select(MessageThread).where(MessageThread.application_id == application.id)
    )
    if thread:
        session.add(
            create_system_message(
                thread,
                "企业已创建技术面试，面试计划就绪后会发送邀请。",
                interview_id=interview.id,
                metadata={"application_status": "REVIEWING"},
            )
        )
    await session.commit()
    await session.refresh(interview)
    return session_response(interview, position, candidate)


@router.post(
    "/workspaces/{workspace_id}/applications/{application_id}/interview-invitation",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_application_interview_invitation(
    workspace_id: uuid.UUID,
    application_id: uuid.UUID,
    interview_id: uuid.UUID = Query(...),
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    workspace, _ = await require_workspace_role(
        session, workspace_id, current_user.id, WRITE_ROLES
    )
    application = await session.scalar(
        select(JobApplication)
        .where(
            JobApplication.id == application_id,
            JobApplication.workspace_id == workspace_id,
        )
        .with_for_update()
    )
    interview = await session.scalar(
        select(InterviewSession).where(
            InterviewSession.id == interview_id,
            InterviewSession.application_id == application_id,
            InterviewSession.workspace_id == workspace_id,
            InterviewSession.status == "READY",
        )
    )
    if application is None or interview is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="面试计划尚未就绪或申请不匹配")
    thread = await session.scalar(
        select(MessageThread).where(MessageThread.application_id == application.id)
    )
    if thread is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="申请消息线程不存在")
    message = PlatformMessage(
        thread_id=thread.id,
        sender_type="ENTERPRISE",
        sender_user_id=current_user.id,
        message_type="INTERVIEW_INVITATION",
        interview_session_id=interview.id,
        content=f"{workspace.name} 邀请你参加技术面试。",
        message_metadata={
            "route": f"/candidate/enterprise-interviews/{interview.id}/run",
            "scheduled_at": interview.scheduled_at.isoformat() if interview.scheduled_at else None,
        },
    )
    application.status = "INTERVIEW"
    thread.updated_at = datetime.now(timezone.utc)
    session.add(message)
    try:
        await session.commit()
        await session.refresh(message)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="面试邀请已经发送")
    return await message_response(session, message)


async def thread_access(
    session: AsyncSession,
    thread_id: uuid.UUID,
    user: AppUser,
) -> tuple[MessageThread, str]:
    thread = await session.get(MessageThread, thread_id)
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="消息会话不存在")
    if thread.candidate_user_id == user.id:
        return thread, "CANDIDATE"
    membership = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == thread.workspace_id,
            WorkspaceMember.user_id == user.id,
            WorkspaceMember.role.in_(READ_ROLES),
        )
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="消息会话不存在")
    return thread, "ENTERPRISE"


async def message_response(
    session: AsyncSession,
    message: PlatformMessage,
) -> MessageResponse:
    sender = await session.get(AppUser, message.sender_user_id) if message.sender_user_id else None
    return MessageResponse(
        id=message.id,
        thread_id=message.thread_id,
        sender_type=message.sender_type,
        sender_user_id=message.sender_user_id,
        sender_name=(sender.display_name or sender.email) if sender else None,
        message_type=message.message_type,
        interview_session_id=message.interview_session_id,
        content=message.content,
        message_metadata=message.message_metadata,
        created_at=message.created_at,
    )


def message_audience_filter(actor_type: str):
    audience = PlatformMessage.message_metadata["audience"].astext
    return or_(audience.is_(None), audience == actor_type)


async def thread_response(
    session: AsyncSession,
    thread: MessageThread,
    user: AppUser,
) -> MessageThreadResponse:
    application = await session.get(JobApplication, thread.application_id)
    workspace = await session.get(Workspace, thread.workspace_id)
    position = await session.get(JobPosition, application.job_position_id) if application else None
    candidate = await session.get(AppUser, thread.candidate_user_id)
    actor_type = "CANDIDATE" if thread.candidate_user_id == user.id else "ENTERPRISE"
    latest = await session.scalar(
        select(PlatformMessage)
        .where(
            PlatformMessage.thread_id == thread.id,
            message_audience_filter(actor_type),
        )
        .order_by(PlatformMessage.created_at.desc())
        .limit(1)
    )
    unread_count = int(
        await session.scalar(
            select(func.count(PlatformMessage.id))
            .outerjoin(
                MessageRead,
                and_(
                    MessageRead.message_id == PlatformMessage.id,
                    MessageRead.user_id == user.id,
                ),
            )
            .where(
                PlatformMessage.thread_id == thread.id,
                MessageRead.id.is_(None),
                or_(
                    PlatformMessage.sender_user_id.is_(None),
                    PlatformMessage.sender_user_id != user.id,
                ),
                message_audience_filter(actor_type),
            )
        )
        or 0
    )
    if not all((application, workspace, position, candidate)):
        raise HTTPException(status_code=500, detail="消息会话数据不完整")
    return MessageThreadResponse(
        id=thread.id,
        application_id=thread.application_id,
        workspace_id=thread.workspace_id,
        workspace_name=workspace.name,
        job_title=position.title,
        candidate_name=candidate.display_name or candidate.email,
        subject=thread.subject,
        application_status=application.status,
        unread_count=unread_count,
        latest_message=latest.content if latest else None,
        latest_message_at=latest.created_at if latest else None,
        updated_at=thread.updated_at,
    )


@router.get("/message-threads", response_model=list[MessageThreadResponse])
async def list_message_threads(
    workspace_id: uuid.UUID | None = None,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[MessageThreadResponse]:
    if workspace_id is None:
        statement = select(MessageThread).where(
            MessageThread.candidate_user_id == current_user.id
        )
    else:
        await require_workspace_role(session, workspace_id, current_user.id, READ_ROLES)
        statement = select(MessageThread).where(MessageThread.workspace_id == workspace_id)
    threads = list(
        (
            await session.scalars(statement.order_by(MessageThread.updated_at.desc()))
        ).all()
    )
    return [await thread_response(session, thread, current_user) for thread in threads]


@router.get(
    "/message-threads/{thread_id}/messages",
    response_model=list[MessageResponse],
)
async def list_thread_messages(
    thread_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[MessageResponse]:
    thread, actor_type = await thread_access(session, thread_id, current_user)
    messages = list(
        (
            await session.scalars(
                select(PlatformMessage)
                .where(
                    PlatformMessage.thread_id == thread.id,
                    message_audience_filter(actor_type),
                )
                .order_by(PlatformMessage.created_at)
            )
        ).all()
    )
    existing_read_ids = set(
        (
            await session.scalars(
                select(MessageRead.message_id).where(
                    MessageRead.user_id == current_user.id,
                    MessageRead.message_id.in_([item.id for item in messages]),
                )
            )
        ).all()
    ) if messages else set()
    unread_message_ids = [item.id for item in messages if item.id not in existing_read_ids]
    if unread_message_ids:
        await session.execute(
            pg_insert(MessageRead)
            .values(
                [
                    {"message_id": message_id, "user_id": current_user.id}
                    for message_id in unread_message_ids
                ]
            )
            .on_conflict_do_nothing(index_elements=["message_id", "user_id"])
        )
    await session.commit()
    return [await message_response(session, item) for item in messages]


@router.post(
    "/message-threads/{thread_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_thread_message(
    thread_id: uuid.UUID,
    request: MessageCreateRequest,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    thread, sender_type = await thread_access(session, thread_id, current_user)
    if sender_type == "ENTERPRISE":
        await require_workspace_role(
            session, thread.workspace_id, current_user.id, MESSAGE_SEND_ROLES
        )
    message = PlatformMessage(
        thread_id=thread.id,
        sender_type=sender_type,
        sender_user_id=current_user.id,
        message_type="TEXT",
        content=request.content.strip(),
        message_metadata={},
    )
    thread.updated_at = datetime.now(timezone.utc)
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return await message_response(session, message)


async def candidate_interview_context(
    session: AsyncSession,
    interview_id: uuid.UUID,
    user: AppUser,
    *,
    for_update: bool = False,
) -> tuple[JobApplication, InterviewSession, AppUser]:
    statement = (
        select(JobApplication, InterviewSession)
        .join(InterviewSession, InterviewSession.application_id == JobApplication.id)
        .where(
            InterviewSession.id == interview_id,
            JobApplication.candidate_user_id == user.id,
            JobApplication.status.in_(("INTERVIEW", "HIRED")),
        )
    )
    if for_update:
        statement = statement.with_for_update()
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="企业面试不存在")
    application, interview = row
    actor = await session.get(AppUser, interview.created_by)
    if actor is None or actor.status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="企业面试执行身份不可用")
    return application, interview, actor


@router.get(
    "/candidate/assigned-interviews/{interview_id}/runtime",
    response_model=InterviewRuntimeResponse,
)
async def get_assigned_interview_runtime(
    interview_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewRuntimeResponse:
    _, interview, actor = await candidate_interview_context(
        session, interview_id, current_user, for_update=True
    )
    if interview.status == "COMPLETED":
        await enqueue_interview_evaluation(session, interview)
        return await runtime_response(session, interview)
    current_question = await session.scalar(
        select(InterviewQuestion).where(
            InterviewQuestion.interview_session_id == interview.id,
            InterviewQuestion.status == "ASKED",
        )
    )
    if interview.status == "IN_PROGRESS" and current_question and question_has_timed_out(current_question, interview):
        current_question.status = "SKIPPED"
        await session.flush()
        await generate_and_activate_next_question(session, interview, actor)
        await session.commit()
        if interview.status == "COMPLETED":
            await enqueue_interview_evaluation(session, interview)
        return await runtime_response(session, interview, question_timed_out=True)
    return await runtime_response(session, interview)


@router.post(
    "/candidate/assigned-interviews/{interview_id}/start",
    response_model=InterviewRuntimeResponse,
)
async def start_assigned_interview(
    interview_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewRuntimeResponse:
    _, interview, actor = await candidate_interview_context(
        session, interview_id, current_user, for_update=True
    )
    if interview.status in {"IN_PROGRESS", "COMPLETED"}:
        if interview.status == "COMPLETED":
            await enqueue_interview_evaluation(session, interview)
        return await runtime_response(session, interview)
    if interview.status != "READY":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="面试计划尚未就绪")
    await session.execute(
        sql_delete(InterviewQuestion).where(
            InterviewQuestion.interview_session_id == interview.id
        )
    )
    interview.status = "IN_PROGRESS"
    interview.started_at = interview.started_at or datetime.now(timezone.utc)
    interview.completed_at = None
    await generate_and_activate_next_question(session, interview, actor)
    await session.commit()
    if interview.status == "COMPLETED":
        await enqueue_interview_evaluation(session, interview)
    return await runtime_response(session, interview)


@router.post(
    "/candidate/assigned-interviews/{interview_id}/questions/{question_id}/answer",
    response_model=InterviewRuntimeResponse,
)
async def answer_assigned_interview(
    interview_id: uuid.UUID,
    question_id: uuid.UUID,
    request: InterviewAnswerSubmitRequest,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewRuntimeResponse:
    _, interview, actor = await candidate_interview_context(
        session, interview_id, current_user, for_update=True
    )
    if interview.status != "IN_PROGRESS":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="面试当前不在进行中")
    question = await session.scalar(
        select(InterviewQuestion)
        .where(
            InterviewQuestion.id == question_id,
            InterviewQuestion.interview_session_id == interview.id,
            InterviewQuestion.order_no == interview.current_question_order,
            InterviewQuestion.status == "ASKED",
        )
        .with_for_update()
    )
    if question is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只能回答当前问题")
    if question_has_timed_out(question, interview):
        question.status = "SKIPPED"
        await session.flush()
        await generate_and_activate_next_question(session, interview, actor)
        await session.commit()
        if interview.status == "COMPLETED":
            await enqueue_interview_evaluation(session, interview)
        return await runtime_response(session, interview, question_timed_out=True)
    session.add(
        InterviewAnswer(
            interview_session_id=interview.id,
            interview_question_id=question.id,
            content=request.content.strip(),
            input_type="TEXT",
            duration_seconds=request.duration_seconds,
            client_metadata=request.client_metadata,
        )
    )
    question.status = "ANSWERED"
    await session.flush()
    next_question = await generate_and_activate_next_question(session, interview, actor)
    await session.commit()
    if interview.status == "COMPLETED":
        await enqueue_interview_evaluation(session, interview)
    return await runtime_response(
        session,
        interview,
        follow_up_generated=bool(next_question and next_question.generated_by == "FOLLOW_UP"),
    )


@router.post(
    "/candidate/assigned-interviews/{interview_id}/questions/{question_id}/skip",
    response_model=InterviewRuntimeResponse,
)
async def skip_assigned_interview_question(
    interview_id: uuid.UUID,
    question_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewRuntimeResponse:
    _, interview, actor = await candidate_interview_context(
        session, interview_id, current_user, for_update=True
    )
    question = await session.scalar(
        select(InterviewQuestion)
        .where(
            InterviewQuestion.id == question_id,
            InterviewQuestion.interview_session_id == interview.id,
            InterviewQuestion.order_no == interview.current_question_order,
            InterviewQuestion.status == "ASKED",
        )
        .with_for_update()
    )
    if interview.status != "IN_PROGRESS" or question is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只能跳过当前问题")
    question.status = "SKIPPED"
    await session.flush()
    await generate_and_activate_next_question(session, interview, actor)
    await session.commit()
    if interview.status == "COMPLETED":
        await enqueue_interview_evaluation(session, interview)
    return await runtime_response(session, interview)


@router.post(
    "/candidate/assigned-interviews/{interview_id}/finish",
    response_model=InterviewRuntimeResponse,
)
async def finish_assigned_interview(
    interview_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewRuntimeResponse:
    _, interview, _ = await candidate_interview_context(
        session, interview_id, current_user, for_update=True
    )
    if interview.status == "COMPLETED":
        await enqueue_interview_evaluation(session, interview)
        return await runtime_response(session, interview)
    if interview.status != "IN_PROGRESS":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="面试尚未开始")
    questions = list(
        (
            await session.scalars(
                select(InterviewQuestion)
                .where(
                    InterviewQuestion.interview_session_id == interview.id,
                    InterviewQuestion.status.in_(("PENDING", "ASKED")),
                )
                .with_for_update()
            )
        ).all()
    )
    for question in questions:
        question.status = "SKIPPED"
    interview.status = "COMPLETED"
    interview.completed_at = datetime.now(timezone.utc)
    await session.commit()
    await enqueue_interview_evaluation(session, interview)
    return await runtime_response(session, interview)
