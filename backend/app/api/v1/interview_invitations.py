import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import delete as sql_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.api.v1.interviews import (
    WRITE_ROLES,
    ensure_next_question_after_submitted_answer,
    generate_and_activate_next_question,
    question_has_timed_out,
    runtime_response,
)
from app.core.config import settings
from app.core.permissions import require_workspace_role
from app.core.security import (
    create_candidate_interview_token,
    decode_candidate_interview_token,
)
from app.db.models.interview import (
    CandidateProfile,
    InterviewAnswer,
    InterviewEvaluation,
    InterviewQuestion,
    InterviewSession,
    JobPosition,
)
from app.db.models.interview_invitation import InterviewInvitation
from app.db.models.interview_decision import InterviewDecision
from app.db.models.user import AppUser
from app.db.models.workspace import Workspace
from app.db.session import get_db_session
from app.schemas.interview import InterviewAnswerSubmitRequest, InterviewRuntimeResponse
from app.schemas.interview_invitation import (
    InterviewCandidateAccessResponse,
    InterviewInvitationCreateRequest,
    InterviewInvitationCreateResponse,
    InterviewInvitationResponse,
    InterviewInvitationVerifyRequest,
    PublicInterviewInvitationResponse,
)
from app.services.evaluation_lifecycle import enqueue_interview_evaluation
from app.services.interview_agent_graph import finish_interview_runtime_agent_graph
from app.services.invitation_credentials import (
    decrypt_invitation_credential,
    encrypt_invitation_credential,
)


router = APIRouter(tags=["候选人面试邀请"])
ACTIVE_INVITATION_STATUSES = {"PENDING", "OPENED", "VERIFIED", "STARTED"}


def hash_link_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_access_code(invitation_id: uuid.UUID, access_code: str) -> str:
    value = f"{invitation_id}:{access_code}".encode("utf-8")
    return hmac.new(
        settings.JWT_SECRET_KEY.encode("utf-8"), value, hashlib.sha256
    ).hexdigest()


def mask_email(email: str) -> str:
    local, domain = email.split("@", 1)
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}{'*' * max(2, len(local) - len(visible))}@{domain}"


def invitation_response(
    invitation: InterviewInvitation,
    *,
    include_credentials: bool = False,
) -> InterviewInvitationResponse:
    return InterviewInvitationResponse(
        id=invitation.id,
        interview_session_id=invitation.interview_session_id,
        email=invitation.email,
        status=invitation.status,
        max_access_count=invitation.max_access_count,
        access_count=invitation.access_count,
        expires_at=invitation.expires_at,
        opened_at=invitation.opened_at,
        verified_at=invitation.verified_at,
        consented_at=invitation.consented_at,
        started_at=invitation.started_at,
        completed_at=invitation.completed_at,
        revoked_at=invitation.revoked_at,
        created_at=invitation.created_at,
        invitation_token=(
            decrypt_invitation_credential(invitation.encrypted_token)
            if include_credentials
            else None
        ),
        access_code=(
            decrypt_invitation_credential(invitation.encrypted_access_code)
            if include_credentials
            else None
        ),
    )


async def get_managed_interview(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    interview_id: uuid.UUID,
    user: AppUser,
    *,
    for_update: bool = False,
) -> tuple[InterviewSession, CandidateProfile]:
    workspace, _ = await require_workspace_role(
        session, workspace_id, user.id, WRITE_ROLES
    )
    if workspace.type != "ORGANIZATION":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只有企业面试可以邀请候选人",
        )
    statement = (
        select(InterviewSession, CandidateProfile)
        .join(
            CandidateProfile,
            CandidateProfile.id == InterviewSession.candidate_profile_id,
        )
        .where(
            InterviewSession.id == interview_id,
            InterviewSession.workspace_id == workspace_id,
            InterviewSession.mode == "ENTERPRISE",
        )
    )
    if for_update:
        statement = statement.with_for_update()
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="企业面试不存在")
    return row


@router.get(
    "/workspaces/{workspace_id}/interviews/{interview_id}/invitations",
    response_model=list[InterviewInvitationResponse],
)
async def list_interview_invitations(
    workspace_id: uuid.UUID,
    interview_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[InterviewInvitationResponse]:
    interview, _ = await get_managed_interview(
        session, workspace_id, interview_id, current_user
    )
    invitations = list(
        (
            await session.scalars(
                select(InterviewInvitation)
                .where(
                    InterviewInvitation.workspace_id == workspace_id,
                    InterviewInvitation.interview_session_id == interview_id,
                )
                .order_by(InterviewInvitation.created_at.desc())
            )
        ).all()
    )
    now = datetime.now(timezone.utc)
    changed = False
    for invitation in invitations:
        if interview.status == "COMPLETED" and invitation.status != "REVOKED":
            invitation.status = "COMPLETED"
            invitation.completed_at = (
                invitation.completed_at or interview.completed_at or now
            )
            changed = True
        elif invitation.status in ACTIVE_INVITATION_STATUSES and invitation.expires_at <= now:
            invitation.status = "EXPIRED"
            changed = True
    if changed:
        await session.commit()
    return [
        invitation_response(item, include_credentials=True)
        for item in invitations
    ]


@router.post(
    "/workspaces/{workspace_id}/interviews/{interview_id}/invitations",
    response_model=InterviewInvitationCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_interview_invitation(
    workspace_id: uuid.UUID,
    interview_id: uuid.UUID,
    request: InterviewInvitationCreateRequest,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewInvitationCreateResponse:
    interview, candidate = await get_managed_interview(
        session, workspace_id, interview_id, current_user, for_update=True
    )
    if interview.status not in {"READY", "IN_PROGRESS"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="只有已就绪或进行中的面试可以创建备用邀请",
        )
    if candidate.email and candidate.email.strip().lower() != request.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邀请邮箱必须与候选人档案邮箱一致",
        )
    now = datetime.now(timezone.utc)
    existing = await session.scalar(
        select(InterviewInvitation).where(
            InterviewInvitation.interview_session_id == interview_id,
            InterviewInvitation.email == request.email,
            InterviewInvitation.status.in_(ACTIVE_INVITATION_STATUSES),
            InterviewInvitation.expires_at > now,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该候选人已有有效邀请，请先撤销原邀请",
        )

    invitation_id = uuid.uuid4()
    raw_token = secrets.token_urlsafe(32)
    access_code = f"{secrets.randbelow(1_000_000):06d}"
    invitation = InterviewInvitation(
        id=invitation_id,
        workspace_id=workspace_id,
        interview_session_id=interview_id,
        email=request.email,
        token_hash=hash_link_token(raw_token),
        access_code_hash=hash_access_code(invitation_id, access_code),
        encrypted_token=encrypt_invitation_credential(raw_token),
        encrypted_access_code=encrypt_invitation_credential(access_code),
        max_access_count=request.max_access_count,
        access_count=0,
        expires_at=now + timedelta(days=request.expires_in_days),
        created_by=current_user.id,
    )
    session.add(invitation)
    await session.commit()
    await session.refresh(invitation)
    base = invitation_response(invitation).model_dump(
        exclude={"invitation_token", "access_code"}
    )
    return InterviewInvitationCreateResponse(
        **base,
        invitation_token=raw_token,
        access_code=access_code,
    )


@router.post(
    "/workspaces/{workspace_id}/interviews/{interview_id}/invitations/{invitation_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_interview_invitation(
    workspace_id: uuid.UUID,
    interview_id: uuid.UUID,
    invitation_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    await get_managed_interview(session, workspace_id, interview_id, current_user)
    invitation = await session.scalar(
        select(InterviewInvitation)
        .where(
            InterviewInvitation.id == invitation_id,
            InterviewInvitation.workspace_id == workspace_id,
            InterviewInvitation.interview_session_id == interview_id,
        )
        .with_for_update()
    )
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="面试邀请不存在")
    if invitation.status == "COMPLETED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="已完成的面试邀请不能撤销",
        )
    if invitation.status != "REVOKED":
        invitation.status = "REVOKED"
        invitation.revoked_at = datetime.now(timezone.utc)
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def get_public_invitation_row(
    session: AsyncSession,
    raw_token: str,
    *,
    for_update: bool = False,
) -> tuple[InterviewInvitation, InterviewSession, Workspace, JobPosition, CandidateProfile]:
    statement = (
        select(
            InterviewInvitation,
            InterviewSession,
            Workspace,
            JobPosition,
            CandidateProfile,
        )
        .join(InterviewSession, InterviewSession.id == InterviewInvitation.interview_session_id)
        .join(Workspace, Workspace.id == InterviewInvitation.workspace_id)
        .join(JobPosition, JobPosition.id == InterviewSession.job_position_id)
        .join(CandidateProfile, CandidateProfile.id == InterviewSession.candidate_profile_id)
        .where(InterviewInvitation.token_hash == hash_link_token(raw_token))
    )
    if for_update:
        statement = statement.with_for_update()
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="面试邀请不存在")
    return row


@router.get(
    "/interview-invitations/{token}",
    response_model=PublicInterviewInvitationResponse,
)
async def get_public_interview_invitation(
    token: str,
    session: AsyncSession = Depends(get_db_session),
) -> PublicInterviewInvitationResponse:
    invitation, interview, workspace, position, candidate = await get_public_invitation_row(
        session, token, for_update=True
    )
    now = datetime.now(timezone.utc)
    if interview.status == "COMPLETED" and invitation.status != "REVOKED":
        invitation.status = "COMPLETED"
        invitation.completed_at = invitation.completed_at or interview.completed_at or now
    elif interview.status not in {"READY", "IN_PROGRESS"} and invitation.status in ACTIVE_INVITATION_STATUSES:
        invitation.status = "REVOKED"
        invitation.revoked_at = now
    elif invitation.status in ACTIVE_INVITATION_STATUSES and invitation.expires_at <= now:
        invitation.status = "EXPIRED"
    elif invitation.status == "PENDING":
        invitation.status = "OPENED"
        invitation.opened_at = now
    await session.commit()
    decision = await session.scalar(
        select(InterviewDecision).where(
            InterviewDecision.interview_session_id == interview.id
        )
    )
    evaluation_status = await session.scalar(
        select(InterviewEvaluation.status).where(
            InterviewEvaluation.interview_session_id == interview.id
        )
    )
    return PublicInterviewInvitationResponse(
        invitation_id=invitation.id,
        workspace_name=workspace.name,
        job_title=position.title,
        candidate_name=candidate.full_name,
        masked_email=mask_email(invitation.email),
        scheduled_at=interview.scheduled_at,
        expires_at=invitation.expires_at,
        status=invitation.status,
        evaluation_status=evaluation_status,
        decision=decision.decision if decision else None,
        decided_at=decision.decided_at if decision else None,
    )


@router.post(
    "/interview-invitations/{token}/verify",
    response_model=InterviewCandidateAccessResponse,
)
async def verify_interview_invitation(
    token: str,
    request: InterviewInvitationVerifyRequest,
    session: AsyncSession = Depends(get_db_session),
) -> InterviewCandidateAccessResponse:
    invitation, interview, _, _, _ = await get_public_invitation_row(
        session, token, for_update=True
    )
    now = datetime.now(timezone.utc)
    if invitation.expires_at <= now:
        invitation.status = "EXPIRED"
        await session.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="面试邀请已过期")
    if invitation.status == "REVOKED":
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="面试邀请已撤销")
    if invitation.status == "COMPLETED" or interview.status == "COMPLETED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该面试已经完成")
    if interview.status not in {"READY", "IN_PROGRESS"}:
        invitation.status = "REVOKED"
        invitation.revoked_at = now
        await session.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="该面试已取消或失效")
    if not request.consent:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="请先同意面试数据处理说明",
        )
    if invitation.access_count >= invitation.max_access_count:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="该邀请的验证次数已用完，请联系企业重新邀请",
        )
    invitation.access_count += 1
    expected_code_hash = hash_access_code(invitation.id, request.access_code)
    if request.email != invitation.email or not hmac.compare_digest(
        expected_code_hash, invitation.access_code_hash
    ):
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或访问码不正确",
        )
    invitation.status = "STARTED" if interview.status == "IN_PROGRESS" else "VERIFIED"
    invitation.verified_at = now
    invitation.consented_at = invitation.consented_at or now
    token_expires_at = min(invitation.expires_at, now + timedelta(hours=12))
    access_token = create_candidate_interview_token(
        invitation.id, interview.id, token_expires_at
    )
    await session.commit()
    return InterviewCandidateAccessResponse(
        invitation_id=invitation.id,
        interview_session_id=interview.id,
        access_token=access_token,
        expires_at=token_expires_at,
    )


async def get_candidate_context(
    session: AsyncSession,
    invitation_id: uuid.UUID,
    access_token: str | None,
    *,
    for_update: bool = False,
) -> tuple[InterviewInvitation, InterviewSession, AppUser]:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="候选人面试凭证无效或已过期",
    )
    if not access_token:
        raise unauthorized
    try:
        token_invitation_id, token_interview_id = decode_candidate_interview_token(
            access_token
        )
    except (jwt.InvalidTokenError, ValueError):
        raise unauthorized
    if token_invitation_id != invitation_id:
        raise unauthorized
    statement = (
        select(InterviewInvitation, InterviewSession)
        .join(InterviewSession, InterviewSession.id == InterviewInvitation.interview_session_id)
        .where(
            InterviewInvitation.id == invitation_id,
            InterviewInvitation.interview_session_id == token_interview_id,
        )
    )
    if for_update:
        statement = statement.with_for_update()
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        raise unauthorized
    invitation, interview = row
    now = datetime.now(timezone.utc)
    if invitation.expires_at <= now:
        invitation.status = "EXPIRED"
        await session.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="面试邀请已过期")
    if invitation.status in {"REVOKED", "EXPIRED"}:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="面试邀请已失效")
    actor = await session.get(AppUser, invitation.created_by)
    if actor is None or actor.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="企业面试执行身份不可用，请联系企业管理员",
        )
    return invitation, interview, actor


def sync_invitation_status(
    invitation: InterviewInvitation,
    interview: InterviewSession,
) -> None:
    now = datetime.now(timezone.utc)
    if interview.status == "COMPLETED":
        invitation.status = "COMPLETED"
        invitation.completed_at = invitation.completed_at or interview.completed_at or now
    elif interview.status == "IN_PROGRESS":
        invitation.status = "STARTED"
        invitation.started_at = invitation.started_at or interview.started_at or now


@router.get(
    "/candidate-interviews/{invitation_id}/runtime",
    response_model=InterviewRuntimeResponse,
)
async def get_candidate_interview_runtime(
    invitation_id: uuid.UUID,
    candidate_access_token: str | None = Header(
        default=None, alias="X-Interview-Access-Token"
    ),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewRuntimeResponse:
    invitation, interview, actor = await get_candidate_context(
        session, invitation_id, candidate_access_token, for_update=True
    )
    if interview.status == "COMPLETED":
        sync_invitation_status(invitation, interview)
        await session.commit()
        await enqueue_interview_evaluation(session, interview)
        return await runtime_response(session, interview)
    current_question = await session.scalar(
        select(InterviewQuestion).where(
            InterviewQuestion.interview_session_id == interview.id,
            InterviewQuestion.status == "ASKED",
        )
    )
    if (
        interview.status == "IN_PROGRESS"
        and current_question is not None
        and question_has_timed_out(current_question, interview)
    ):
        current_question.status = "SKIPPED"
        await session.flush()
        await generate_and_activate_next_question(session, interview, actor)
    elif interview.status == "IN_PROGRESS" and current_question is None:
        await generate_and_activate_next_question(session, interview, actor)
    sync_invitation_status(invitation, interview)
    await session.commit()
    if interview.status == "COMPLETED":
        await enqueue_interview_evaluation(session, interview)
    return await runtime_response(session, interview)


@router.post(
    "/candidate-interviews/{invitation_id}/start",
    response_model=InterviewRuntimeResponse,
)
async def start_candidate_interview(
    invitation_id: uuid.UUID,
    candidate_access_token: str | None = Header(
        default=None, alias="X-Interview-Access-Token"
    ),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewRuntimeResponse:
    invitation, interview, actor = await get_candidate_context(
        session, invitation_id, candidate_access_token, for_update=True
    )
    if interview.status == "COMPLETED":
        sync_invitation_status(invitation, interview)
        await session.commit()
        await enqueue_interview_evaluation(session, interview)
        return await runtime_response(session, interview)
    if interview.status == "READY":
        await session.execute(
            sql_delete(InterviewQuestion).where(
                InterviewQuestion.interview_session_id == interview.id
            )
        )
        interview.status = "IN_PROGRESS"
        interview.started_at = interview.started_at or datetime.now(timezone.utc)
        interview.completed_at = None
        await generate_and_activate_next_question(session, interview, actor)
    elif interview.status != "IN_PROGRESS":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前面试尚未就绪",
        )
    sync_invitation_status(invitation, interview)
    await session.commit()
    if interview.status == "COMPLETED":
        await enqueue_interview_evaluation(session, interview)
    return await runtime_response(session, interview)


@router.post(
    "/candidate-interviews/{invitation_id}/questions/{question_id}/answer",
    response_model=InterviewRuntimeResponse,
)
async def submit_candidate_interview_answer(
    invitation_id: uuid.UUID,
    question_id: uuid.UUID,
    request: InterviewAnswerSubmitRequest,
    candidate_access_token: str | None = Header(
        default=None, alias="X-Interview-Access-Token"
    ),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewRuntimeResponse:
    invitation, interview, actor = await get_candidate_context(
        session, invitation_id, candidate_access_token, for_update=True
    )
    if interview.status == "COMPLETED":
        sync_invitation_status(invitation, interview)
        await session.commit()
        await enqueue_interview_evaluation(session, interview)
        return await runtime_response(session, interview)
    if interview.status != "IN_PROGRESS":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="面试当前不在进行中")
    question = await session.scalar(
        select(InterviewQuestion)
        .where(
            InterviewQuestion.id == question_id,
            InterviewQuestion.interview_session_id == interview.id,
        )
        .with_for_update()
    )
    if question is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="问题不存在或不属于当前面试")
    if question.status == "ANSWERED":
        existing_answer = await session.scalar(
            select(InterviewAnswer).where(
                InterviewAnswer.interview_question_id == question.id
            )
        )
        if existing_answer is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="回答状态异常，请刷新面试页面",
            )
        await ensure_next_question_after_submitted_answer(
            session, interview, actor
        )
        sync_invitation_status(invitation, interview)
        await session.commit()
        if interview.status == "COMPLETED":
            await enqueue_interview_evaluation(session, interview)
        return await runtime_response(session, interview)
    if (
        question.order_no != interview.current_question_order
        or question.status != "ASKED"
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只能回答当前问题")
    if question_has_timed_out(question, interview):
        question.status = "SKIPPED"
        await session.flush()
        await generate_and_activate_next_question(session, interview, actor)
        sync_invitation_status(invitation, interview)
        await session.commit()
        if interview.status == "COMPLETED":
            await enqueue_interview_evaluation(session, interview)
        return await runtime_response(session, interview, question_timed_out=True)
    answer_content = request.content.strip()
    if not answer_content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="回答内容不能为空",
        )
    session.add(
        InterviewAnswer(
            interview_session_id=interview.id,
            interview_question_id=question.id,
            content=answer_content,
            input_type="TEXT",
            duration_seconds=request.duration_seconds,
            client_metadata=request.client_metadata,
        )
    )
    question.status = "ANSWERED"
    await session.flush()
    next_question = await generate_and_activate_next_question(session, interview, actor)
    sync_invitation_status(invitation, interview)
    await session.commit()
    if interview.status == "COMPLETED":
        await enqueue_interview_evaluation(session, interview)
    return await runtime_response(
        session,
        interview,
        follow_up_generated=bool(
            next_question and next_question.generated_by == "FOLLOW_UP"
        ),
    )


@router.post(
    "/candidate-interviews/{invitation_id}/questions/{question_id}/skip",
    response_model=InterviewRuntimeResponse,
)
async def skip_candidate_interview_question(
    invitation_id: uuid.UUID,
    question_id: uuid.UUID,
    candidate_access_token: str | None = Header(
        default=None, alias="X-Interview-Access-Token"
    ),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewRuntimeResponse:
    invitation, interview, actor = await get_candidate_context(
        session, invitation_id, candidate_access_token, for_update=True
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
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只能跳过当前问题")
    question.status = "SKIPPED"
    await session.flush()
    await generate_and_activate_next_question(session, interview, actor)
    sync_invitation_status(invitation, interview)
    await session.commit()
    if interview.status == "COMPLETED":
        await enqueue_interview_evaluation(session, interview)
    return await runtime_response(session, interview)


@router.post(
    "/candidate-interviews/{invitation_id}/finish",
    response_model=InterviewRuntimeResponse,
)
async def finish_candidate_interview(
    invitation_id: uuid.UUID,
    candidate_access_token: str | None = Header(
        default=None, alias="X-Interview-Access-Token"
    ),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewRuntimeResponse:
    invitation, interview, _ = await get_candidate_context(
        session, invitation_id, candidate_access_token, for_update=True
    )
    if interview.status == "COMPLETED":
        sync_invitation_status(invitation, interview)
        await session.commit()
        await enqueue_interview_evaluation(session, interview)
        return await runtime_response(session, interview)
    if interview.status != "IN_PROGRESS":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="面试尚未开始")
    remaining_questions = list(
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
    for question in remaining_questions:
        question.status = "SKIPPED"
    interview.status = "COMPLETED"
    interview.completed_at = datetime.now(timezone.utc)
    sync_invitation_status(invitation, interview)
    await session.commit()
    await finish_interview_runtime_agent_graph(session, interview)
    await enqueue_interview_evaluation(session, interview)
    return await runtime_response(session, interview)
