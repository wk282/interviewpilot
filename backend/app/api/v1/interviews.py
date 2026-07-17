import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import and_, delete as sql_delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.permissions import require_workspace_role
from app.db.models.document import Document
from app.db.models.interview import (
    CandidateProfile,
    InterviewAnswer,
    InterviewEvaluation,
    InterviewPlan,
    InterviewQuestion,
    InterviewSession,
    JobPosition,
)
from app.db.models.knowledge_base import KnowledgeBase
from app.db.models.recruitment import JobApplication, MessageThread, PlatformMessage
from app.db.models.user import AppUser
from app.db.models.workspace import WorkspaceMember
from app.db.session import get_db_session
from app.schemas.interview import (
    CandidateProfileCreateRequest,
    CandidateProfileResponse,
    CandidateProfileUpdateRequest,
    InterviewAnswerSubmitRequest,
    InterviewEvaluationResponse,
    InterviewSessionCreateRequest,
    InterviewSessionResponse,
    InterviewSessionUpdateRequest,
    InterviewPlanResponse,
    InterviewQuestionResponse,
    InterviewRuntimeQuestionResponse,
    InterviewRuntimeResponse,
    JobPositionCreateRequest,
    JobPositionResponse,
    JobPositionUpdateRequest,
)
from app.services.interview_conductor import (
    CONDUCTOR_PROMPT_VERSION,
    GeneratedTurn,
    generate_next_turn,
)
from app.workers.interview_tasks import generate_interview_evaluation, generate_interview_plan


router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["面试管理"])

READ_ROLES = {"OWNER", "ADMIN", "HR", "INTERVIEWER", "VIEWER"}
WRITE_ROLES = {"OWNER", "ADMIN", "HR"}
PLAN_ROLES = {"OWNER", "ADMIN", "HR", "INTERVIEWER"}
EXECUTE_ROLES = {"OWNER", "ADMIN", "HR", "INTERVIEWER"}


async def validate_knowledge_base(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    knowledge_base_id: uuid.UUID | None,
    purpose: str,
) -> None:
    if knowledge_base_id is None:
        return
    knowledge_base = await session.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.workspace_id == workspace_id,
            KnowledgeBase.purpose == purpose,
        )
    )
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"请选择当前工作空间中的 {purpose} 知识库",
        )


async def validate_resume_document(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    require_ready: bool = True,
) -> Document:
    document = await session.scalar(
        select(Document)
        .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
        .where(
            Document.id == document_id,
            Document.status != "DELETED",
            KnowledgeBase.workspace_id == workspace_id,
            KnowledgeBase.purpose == "RESUME",
        )
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请选择当前工作空间中的简历文件",
        )
    if require_ready and document.status != "READY":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="简历尚未解析完成，请等待简历状态变为可用",
        )
    return document


async def validate_personal_reference_knowledge_bases(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    knowledge_base_ids: list[uuid.UUID],
) -> list[uuid.UUID]:
    unique_ids = list(dict.fromkeys(knowledge_base_ids))
    if not unique_ids:
        return []
    matched_ids = set(
        (
            await session.scalars(
                select(KnowledgeBase.id).where(
                    KnowledgeBase.id.in_(unique_ids),
                    KnowledgeBase.workspace_id == workspace_id,
                    KnowledgeBase.purpose == "PERSONAL_LEARNING",
                )
            )
        ).all()
    )
    if matched_ids != set(unique_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="面试参考资料必须是当前个人工作空间中的个人学习知识库",
        )
    return unique_ids


async def validate_interviewer(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    interviewer_id: uuid.UUID | None,
) -> None:
    if interviewer_id is None:
        return
    interviewer = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == interviewer_id,
            WorkspaceMember.role.in_(("OWNER", "ADMIN", "INTERVIEWER")),
        )
    )
    if interviewer is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="指定面试官不属于当前企业",
        )


def session_response(
    interview: InterviewSession,
    position: JobPosition,
    candidate: CandidateProfile,
) -> InterviewSessionResponse:
    return InterviewSessionResponse(
        id=interview.id,
        workspace_id=interview.workspace_id,
        job_position_id=interview.job_position_id,
        job_title=position.title,
        candidate_profile_id=interview.candidate_profile_id,
        candidate_name=candidate.full_name,
        interviewer_id=interview.interviewer_id,
        application_id=interview.application_id,
        mode=interview.mode,
        status=interview.status,
        current_question_order=interview.current_question_order,
        configuration=interview.configuration,
        scheduled_at=interview.scheduled_at,
        started_at=interview.started_at,
        completed_at=interview.completed_at,
        created_by=interview.created_by,
        created_at=interview.created_at,
        updated_at=interview.updated_at,
    )


def plan_response(
    plan: InterviewPlan,
    questions: list[InterviewQuestion],
) -> InterviewPlanResponse:
    return InterviewPlanResponse(
        id=plan.id,
        interview_session_id=plan.interview_session_id,
        version=plan.version,
        status=plan.status,
        objectives=plan.objectives,
        sections=plan.sections,
        model_name=plan.model_name,
        prompt_version=plan.prompt_version,
        generated_at=plan.generated_at,
        error_message=plan.error_message,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        questions=[
            InterviewQuestionResponse(
                id=question.id,
                order_no=question.order_no,
                question_type=question.question_type,
                content=question.content,
                competency=question.competency,
                difficulty=question.difficulty,
                generated_by=question.generated_by,
                status=question.status,
                max_score=float(question.max_score),
                expected_points=question.expected_points,
                source_evidence=question.source_evidence,
            )
            for question in questions
        ],
    )


def evaluation_response(
    evaluation: InterviewEvaluation,
) -> InterviewEvaluationResponse:
    return InterviewEvaluationResponse(
        id=evaluation.id,
        interview_session_id=evaluation.interview_session_id,
        status=evaluation.status,
        overall_score=(
            float(evaluation.overall_score)
            if evaluation.overall_score is not None
            else None
        ),
        dimension_scores=evaluation.dimension_scores,
        strengths=evaluation.strengths,
        weaknesses=evaluation.weaknesses,
        evidence=evaluation.evidence,
        report_text=evaluation.report_text,
        recommendation=evaluation.recommendation,
        model_name=evaluation.model_name,
        prompt_version=evaluation.prompt_version,
        error_message=evaluation.error_message,
        reviewed_at=evaluation.reviewed_at,
        created_at=evaluation.created_at,
        updated_at=evaluation.updated_at,
    )


async def get_executable_interview(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    interview_id: uuid.UUID,
    user: AppUser,
    *,
    for_update: bool = False,
) -> InterviewSession:
    _, membership = await require_workspace_role(
        session, workspace_id, user.id, EXECUTE_ROLES
    )
    statement = select(InterviewSession).where(
        InterviewSession.id == interview_id,
        InterviewSession.workspace_id == workspace_id,
    )
    if for_update:
        statement = statement.with_for_update()
    interview = await session.scalar(statement)
    if interview is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="面试不存在")
    if membership.role == "INTERVIEWER" and interview.interviewer_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能执行分配给自己的面试",
        )
    return interview


def reject_enterprise_execution_for_application(interview: InterviewSession) -> None:
    if interview.application_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="投递关联的企业面试只能由候选人账号作答",
        )


async def generate_and_activate_next_question(
    session: AsyncSession,
    interview: InterviewSession,
    user: AppUser,
) -> InterviewQuestion | None:
    turn: GeneratedTurn = await generate_next_turn(session, interview, user)
    if turn.action == "FINISH":
        interview.status = "COMPLETED"
        interview.completed_at = datetime.now(timezone.utc)
        return None
    latest_question = await session.scalar(
        select(InterviewQuestion)
        .where(InterviewQuestion.interview_session_id == interview.id)
        .order_by(InterviewQuestion.order_no.desc())
        .limit(1)
    )
    next_order = (latest_question.order_no if latest_question else 0) + 1
    interview_plan_id = latest_question.interview_plan_id if latest_question else None
    if interview_plan_id is None:
        interview_plan_id = await session.scalar(
            select(InterviewPlan.id)
            .where(
                InterviewPlan.interview_session_id == interview.id,
                InterviewPlan.status == "READY",
            )
            .order_by(InterviewPlan.version.desc())
            .limit(1)
        )
    question = InterviewQuestion(
        interview_session_id=interview.id,
        interview_plan_id=interview_plan_id,
        parent_question_id=(latest_question.id if turn.is_follow_up and latest_question else None),
        order_no=next_order,
        question_type="FOLLOW_UP" if turn.is_follow_up else (turn.question_type or "TECHNICAL"),
        content=turn.content or "请结合实际经历说明你的解决思路。",
        competency=turn.competency,
        difficulty=turn.difficulty or "MEDIUM",
        generated_by="FOLLOW_UP" if turn.is_follow_up else "PLAN",
        status="ASKED",
        max_score=10,
        expected_points=turn.expected_points or [],
        source_evidence=turn.source_evidence or [],
        decision_metadata={
            "reason": turn.reason,
            "is_follow_up": turn.is_follow_up,
            "planned_question_type": turn.question_type,
            "prompt_version": CONDUCTOR_PROMPT_VERSION,
            "retrieval_grade": turn.retrieval_grade or {},
            "retrieval_trace": turn.retrieval_trace or [],
        },
        asked_at=datetime.now(timezone.utc),
    )
    session.add(question)
    await session.flush()
    interview.current_question_order = question.order_no
    return question


async def runtime_response(
    session: AsyncSession,
    interview: InterviewSession,
    *,
    follow_up_generated: bool = False,
    question_timed_out: bool = False,
) -> InterviewRuntimeResponse:
    current_question = await session.scalar(
        select(InterviewQuestion).where(
            InterviewQuestion.interview_session_id == interview.id,
            InterviewQuestion.status == "ASKED",
        )
    )
    total_count = int(
        await session.scalar(
            select(func.count(InterviewQuestion.id)).where(
                InterviewQuestion.interview_session_id == interview.id
            )
        )
        or 0
    )
    completed_count = int(
        await session.scalar(
            select(func.count(InterviewQuestion.id)).where(
                InterviewQuestion.interview_session_id == interview.id,
                InterviewQuestion.status.in_(("ANSWERED", "SKIPPED")),
            )
        )
        or 0
    )
    question_response = None
    if current_question is not None:
        question_response = InterviewRuntimeQuestionResponse(
            id=current_question.id,
            order_no=current_question.order_no,
            question_type=current_question.question_type,
            content=current_question.content,
            competency=current_question.competency,
            difficulty=current_question.difficulty,
            generated_by=current_question.generated_by,
            asked_at=current_question.asked_at,
        )
    time_limit_minutes = int(
        interview.configuration.get("question_time_limit_minutes", 10)
    )
    return InterviewRuntimeResponse(
        interview_id=interview.id,
        status=interview.status,
        current_question=question_response,
        completed_question_count=completed_count,
        total_question_count=total_count,
        max_question_count=int(interview.configuration.get("max_question_count", 10)),
        question_time_limit_seconds=(
            time_limit_minutes * 60 if time_limit_minutes > 0 else None
        ),
        started_at=interview.started_at,
        completed_at=interview.completed_at,
        follow_up_generated=follow_up_generated,
        question_timed_out=question_timed_out,
    )


def question_has_timed_out(
    question: InterviewQuestion,
    interview: InterviewSession,
) -> bool:
    time_limit_minutes = int(
        interview.configuration.get("question_time_limit_minutes", 10)
    )
    if time_limit_minutes <= 0:
        return False
    return bool(
        question.asked_at
        and question.asked_at
        <= datetime.now(timezone.utc) - timedelta(minutes=time_limit_minutes)
    )


@router.get("/positions", response_model=list[JobPositionResponse])
async def list_positions(
    workspace_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[JobPosition]:
    await require_workspace_role(session, workspace_id, current_user.id, READ_ROLES)
    return list(
        (
            await session.scalars(
                select(JobPosition)
                .where(JobPosition.workspace_id == workspace_id)
                .order_by(JobPosition.created_at.desc())
            )
        ).all()
    )


@router.post("/positions", response_model=JobPositionResponse, status_code=status.HTTP_201_CREATED)
async def create_position(
    workspace_id: uuid.UUID,
    request: JobPositionCreateRequest,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> JobPosition:
    await require_workspace_role(session, workspace_id, current_user.id, WRITE_ROLES)
    await validate_knowledge_base(session, workspace_id, request.knowledge_base_id, "JOB_SPECIFIC")
    position = JobPosition(
        workspace_id=workspace_id,
        title=request.title.strip(),
        department=request.department.strip() if request.department else None,
        description=request.description,
        requirements=request.requirements,
        knowledge_base_id=request.knowledge_base_id,
        status=request.status,
        created_by=current_user.id,
    )
    session.add(position)
    await session.commit()
    await session.refresh(position)
    return position


@router.patch("/positions/{position_id}", response_model=JobPositionResponse)
async def update_position(
    workspace_id: uuid.UUID,
    position_id: uuid.UUID,
    request: JobPositionUpdateRequest,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> JobPosition:
    await require_workspace_role(session, workspace_id, current_user.id, WRITE_ROLES)
    position = await session.scalar(
        select(JobPosition).where(
            JobPosition.id == position_id,
            JobPosition.workspace_id == workspace_id,
        )
    )
    if position is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="岗位不存在")
    values = request.model_dump(exclude_unset=True)
    if "knowledge_base_id" in values:
        await validate_knowledge_base(session, workspace_id, values["knowledge_base_id"], "JOB_SPECIFIC")
    if "title" in values and values["title"] is not None:
        values["title"] = values["title"].strip()
    if "department" in values and values["department"] is not None:
        values["department"] = values["department"].strip()
    for field, value in values.items():
        setattr(position, field, value)
    await session.commit()
    await session.refresh(position)
    return position


@router.delete("/positions/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_position(
    workspace_id: uuid.UUID,
    position_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_workspace_role(session, workspace_id, current_user.id, WRITE_ROLES)
    position = await session.scalar(
        select(JobPosition).where(JobPosition.id == position_id, JobPosition.workspace_id == workspace_id)
    )
    if position is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="岗位不存在")
    session_id = await session.scalar(
        select(InterviewSession.id).where(InterviewSession.job_position_id == position_id).limit(1)
    )
    application_id = await session.scalar(
        select(JobApplication.id).where(JobApplication.job_position_id == position_id).limit(1)
    )
    if session_id is not None or application_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="岗位已有申请或面试记录，请关闭岗位而不是删除")
    await session.delete(position)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/candidates", response_model=list[CandidateProfileResponse])
async def list_candidates(
    workspace_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[CandidateProfile]:
    await require_workspace_role(session, workspace_id, current_user.id, READ_ROLES)
    return list(
        (
            await session.scalars(
                select(CandidateProfile)
                .where(CandidateProfile.workspace_id == workspace_id)
                .order_by(CandidateProfile.created_at.desc())
            )
        ).all()
    )


@router.post("/candidates", response_model=CandidateProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_candidate(
    workspace_id: uuid.UUID,
    request: CandidateProfileCreateRequest,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CandidateProfile:
    workspace, _ = await require_workspace_role(
        session, workspace_id, current_user.id, WRITE_ROLES
    )
    resume_document = await validate_resume_document(
        session, workspace_id, request.resume_document_id
    )
    candidate = CandidateProfile(
        workspace_id=workspace_id,
        user_id=current_user.id if workspace.type == "PERSONAL" else None,
        resume_knowledge_base_id=resume_document.knowledge_base_id,
        resume_document_id=resume_document.id,
        full_name=request.full_name.strip(),
        email=request.email.strip().lower() if request.email else None,
        phone=request.phone.strip() if request.phone else None,
        source="PERSONAL_ACCOUNT" if workspace.type == "PERSONAL" else "ENTERPRISE_IMPORT",
        profile_data=request.profile_data,
        created_by=current_user.id,
    )
    session.add(candidate)
    try:
        await session.commit()
        await session.refresh(candidate)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="个人候选人档案已存在")
    return candidate


@router.patch("/candidates/{candidate_id}", response_model=CandidateProfileResponse)
async def update_candidate(
    workspace_id: uuid.UUID,
    candidate_id: uuid.UUID,
    request: CandidateProfileUpdateRequest,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CandidateProfile:
    await require_workspace_role(session, workspace_id, current_user.id, WRITE_ROLES)
    candidate = await session.scalar(
        select(CandidateProfile).where(
            CandidateProfile.id == candidate_id,
            CandidateProfile.workspace_id == workspace_id,
        )
    )
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="候选人不存在")
    values = request.model_dump(exclude_unset=True)
    linked_application_id = await session.scalar(
        select(JobApplication.id).where(
            JobApplication.candidate_profile_id == candidate.id
        ).limit(1)
    )
    if linked_application_id is not None and "resume_document_id" in values:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="岗位投递生成的简历快照不能替换",
        )
    if "resume_document_id" in values:
        if values["resume_document_id"] is None:
            values["resume_knowledge_base_id"] = None
        else:
            resume_document = await validate_resume_document(
                session, workspace_id, values["resume_document_id"]
            )
            values["resume_knowledge_base_id"] = resume_document.knowledge_base_id
    for field in ("full_name", "email", "phone"):
        if field in values and values[field] is not None:
            values[field] = values[field].strip()
    if values.get("email"):
        values["email"] = values["email"].lower()
    for field, value in values.items():
        setattr(candidate, field, value)
    await session.commit()
    await session.refresh(candidate)
    return candidate


@router.delete("/candidates/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_candidate(
    workspace_id: uuid.UUID,
    candidate_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_workspace_role(session, workspace_id, current_user.id, WRITE_ROLES)
    candidate = await session.scalar(
        select(CandidateProfile).where(
            CandidateProfile.id == candidate_id,
            CandidateProfile.workspace_id == workspace_id,
        )
    )
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="候选人不存在")
    session_id = await session.scalar(
        select(InterviewSession.id).where(InterviewSession.candidate_profile_id == candidate_id).limit(1)
    )
    application_id = await session.scalar(
        select(JobApplication.id).where(JobApplication.candidate_profile_id == candidate_id).limit(1)
    )
    if session_id is not None or application_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="候选人已有岗位申请或面试记录，请归档而不是删除")
    await session.delete(candidate)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/interviews", response_model=list[InterviewSessionResponse])
async def list_interviews(
    workspace_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[InterviewSessionResponse]:
    await require_workspace_role(session, workspace_id, current_user.id, READ_ROLES)
    rows = (
        await session.execute(
            select(InterviewSession, JobPosition, CandidateProfile)
            .join(JobPosition, JobPosition.id == InterviewSession.job_position_id)
            .join(CandidateProfile, CandidateProfile.id == InterviewSession.candidate_profile_id)
            .where(InterviewSession.workspace_id == workspace_id)
            .order_by(InterviewSession.created_at.desc())
        )
    ).all()
    return [session_response(interview, position, candidate) for interview, position, candidate in rows]


@router.post("/interviews", response_model=InterviewSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_interview(
    workspace_id: uuid.UUID,
    request: InterviewSessionCreateRequest,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewSessionResponse:
    workspace, _ = await require_workspace_role(
        session, workspace_id, current_user.id, WRITE_ROLES
    )
    position = await session.scalar(
        select(JobPosition).where(
            JobPosition.id == request.job_position_id,
            JobPosition.workspace_id == workspace_id,
            JobPosition.status != "CLOSED",
        )
    )
    candidate = await session.scalar(
        select(CandidateProfile).where(
            CandidateProfile.id == request.candidate_profile_id,
            CandidateProfile.workspace_id == workspace_id,
            CandidateProfile.status == "ACTIVE",
        )
    )
    if position is None or candidate is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="岗位或候选人不可用")

    if request.application_id is not None:
        application = await session.scalar(
            select(JobApplication).where(
                JobApplication.id == request.application_id,
                JobApplication.workspace_id == workspace_id,
                JobApplication.job_position_id == position.id,
                JobApplication.candidate_profile_id == candidate.id,
                JobApplication.status.not_in(("REJECTED", "WITHDRAWN")),
            )
        )
        if application is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="岗位申请与所选岗位或候选人不匹配",
            )

    if candidate.resume_document_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先为候选人选择已解析完成的简历",
        )
    await validate_resume_document(session, workspace_id, candidate.resume_document_id)

    interviewer_id = request.interviewer_id
    reference_knowledge_base_ids: list[uuid.UUID] = []
    if workspace.type == "PERSONAL":
        interviewer_id = None
        reference_knowledge_base_ids = await validate_personal_reference_knowledge_bases(
            session,
            workspace_id,
            request.reference_knowledge_base_ids,
        )
    elif request.reference_knowledge_base_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="企业面试不能使用个人面试参考资料",
        )
    else:
        await validate_interviewer(session, workspace_id, interviewer_id)

    configuration = dict(request.configuration)
    configuration["reference_knowledge_base_ids"] = [
        str(knowledge_base_id) for knowledge_base_id in reference_knowledge_base_ids
    ]
    configuration["max_question_count"] = request.max_question_count
    configuration["question_time_limit_minutes"] = request.question_time_limit_minutes

    interview = InterviewSession(
        workspace_id=workspace_id,
        job_position_id=position.id,
        candidate_profile_id=candidate.id,
        interviewer_id=interviewer_id,
        application_id=request.application_id,
        mode="MOCK" if workspace.type == "PERSONAL" else "ENTERPRISE",
        scheduled_at=request.scheduled_at,
        configuration=configuration,
        created_by=current_user.id,
    )
    session.add(interview)
    await session.commit()
    await session.refresh(interview)
    return session_response(interview, position, candidate)


@router.patch("/interviews/{interview_id}", response_model=InterviewSessionResponse)
async def update_interview(
    workspace_id: uuid.UUID,
    interview_id: uuid.UUID,
    request: InterviewSessionUpdateRequest,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewSessionResponse:
    workspace, _ = await require_workspace_role(
        session, workspace_id, current_user.id, WRITE_ROLES
    )
    row = (
        await session.execute(
            select(InterviewSession, JobPosition, CandidateProfile)
            .join(JobPosition, JobPosition.id == InterviewSession.job_position_id)
            .join(CandidateProfile, CandidateProfile.id == InterviewSession.candidate_profile_id)
            .where(InterviewSession.id == interview_id, InterviewSession.workspace_id == workspace_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="面试不存在")
    interview, position, candidate = row
    if interview.status not in {"DRAFT", "READY"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前面试状态不允许修改")
    values = request.model_dump(exclude_unset=True)
    if workspace.type == "PERSONAL":
        values["interviewer_id"] = None
    elif "interviewer_id" in values:
        await validate_interviewer(session, workspace_id, values["interviewer_id"])
    for field, value in values.items():
        setattr(interview, field, value)
    await session.commit()
    await session.refresh(interview)
    return session_response(interview, position, candidate)


@router.post(
    "/interviews/{interview_id}/plan",
    response_model=InterviewPlanResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_interview_plan(
    workspace_id: uuid.UUID,
    interview_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewPlanResponse:
    _, membership = await require_workspace_role(
        session, workspace_id, current_user.id, PLAN_ROLES
    )
    interview = await session.scalar(
        select(InterviewSession).where(
            InterviewSession.id == interview_id,
            InterviewSession.workspace_id == workspace_id,
        )
    )
    if interview is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="面试不存在")
    if membership.role == "INTERVIEWER" and interview.interviewer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能规划分配给自己的面试")
    if interview.status not in {"DRAFT", "FAILED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前面试状态不能生成计划")

    candidate = await session.scalar(
        select(CandidateProfile).where(
            CandidateProfile.id == interview.candidate_profile_id,
            CandidateProfile.workspace_id == workspace_id,
        )
    )
    if candidate is None or candidate.resume_document_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先为候选人选择已解析完成的简历",
        )
    await validate_resume_document(session, workspace_id, candidate.resume_document_id)

    latest_version = await session.scalar(
        select(func.max(InterviewPlan.version)).where(
            InterviewPlan.interview_session_id == interview_id
        )
    )
    plan = InterviewPlan(
        interview_session_id=interview_id,
        version=(latest_version or 0) + 1,
        status="DRAFT",
        objectives=[],
        sections=[],
    )
    interview.status = "PLANNING"
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    try:
        generate_interview_plan.delay(str(plan.id))
    except Exception as error:
        plan.status = "FAILED"
        plan.error_message = str(error)[:2000]
        interview.status = "FAILED"
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="面试计划任务提交失败",
        ) from error
    return plan_response(plan, [])


@router.get("/interviews/{interview_id}/plan", response_model=InterviewPlanResponse)
async def get_interview_plan(
    workspace_id: uuid.UUID,
    interview_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewPlanResponse:
    await require_workspace_role(session, workspace_id, current_user.id, READ_ROLES)
    interview = await session.scalar(
        select(InterviewSession).where(
            InterviewSession.id == interview_id,
            InterviewSession.workspace_id == workspace_id,
        )
    )
    if interview is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="面试不存在")
    plan = await session.scalar(
        select(InterviewPlan)
        .where(InterviewPlan.interview_session_id == interview_id)
        .order_by(InterviewPlan.version.desc())
        .limit(1)
    )
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="面试计划尚未生成")
    questions = list(
        (
            await session.scalars(
                select(InterviewQuestion)
                .where(InterviewQuestion.interview_plan_id == plan.id)
                .order_by(InterviewQuestion.order_no)
            )
        ).all()
    )
    return plan_response(plan, questions)


@router.post("/interviews/{interview_id}/start", response_model=InterviewRuntimeResponse)
async def start_interview(
    workspace_id: uuid.UUID,
    interview_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewRuntimeResponse:
    interview = await get_executable_interview(
        session, workspace_id, interview_id, current_user, for_update=True
    )
    reject_enterprise_execution_for_application(interview)
    if interview.status == "COMPLETED":
        return await runtime_response(session, interview)
    if interview.status == "IN_PROGRESS":
        return await runtime_response(session, interview)
    if interview.status != "READY":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="面试计划尚未就绪",
        )
    await session.execute(
        sql_delete(InterviewQuestion).where(
            InterviewQuestion.interview_session_id == interview.id
        )
    )
    interview.status = "IN_PROGRESS"
    interview.started_at = interview.started_at or datetime.now(timezone.utc)
    interview.completed_at = None
    await generate_and_activate_next_question(session, interview, current_user)
    await session.commit()
    return await runtime_response(session, interview)


@router.get("/interviews/{interview_id}/runtime", response_model=InterviewRuntimeResponse)
async def get_interview_runtime(
    workspace_id: uuid.UUID,
    interview_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewRuntimeResponse:
    interview = await get_executable_interview(
        session, workspace_id, interview_id, current_user, for_update=True
    )
    reject_enterprise_execution_for_application(interview)
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
        await generate_and_activate_next_question(session, interview, current_user)
        await session.commit()
        return await runtime_response(session, interview, question_timed_out=True)
    return await runtime_response(session, interview)


@router.post(
    "/interviews/{interview_id}/questions/{question_id}/answer",
    response_model=InterviewRuntimeResponse,
)
async def submit_interview_answer(
    workspace_id: uuid.UUID,
    interview_id: uuid.UUID,
    question_id: uuid.UUID,
    request: InterviewAnswerSubmitRequest,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewRuntimeResponse:
    interview = await get_executable_interview(
        session, workspace_id, interview_id, current_user, for_update=True
    )
    reject_enterprise_execution_for_application(interview)
    if interview.status != "IN_PROGRESS":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="面试当前不在进行中",
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
    if question is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="只能回答当前问题",
        )
    if question_has_timed_out(question, interview):
        question.status = "SKIPPED"
        await session.flush()
        await generate_and_activate_next_question(session, interview, current_user)
        await session.commit()
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

    next_question = await generate_and_activate_next_question(
        session, interview, current_user
    )
    follow_up_generated = bool(
        next_question and next_question.generated_by == "FOLLOW_UP"
    )
    await session.commit()
    return await runtime_response(
        session,
        interview,
        follow_up_generated=follow_up_generated,
    )


@router.post(
    "/interviews/{interview_id}/questions/{question_id}/skip",
    response_model=InterviewRuntimeResponse,
)
async def skip_interview_question(
    workspace_id: uuid.UUID,
    interview_id: uuid.UUID,
    question_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewRuntimeResponse:
    interview = await get_executable_interview(
        session, workspace_id, interview_id, current_user, for_update=True
    )
    reject_enterprise_execution_for_application(interview)
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
    await generate_and_activate_next_question(session, interview, current_user)
    await session.commit()
    return await runtime_response(session, interview)


@router.post("/interviews/{interview_id}/finish", response_model=InterviewRuntimeResponse)
async def finish_interview(
    workspace_id: uuid.UUID,
    interview_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewRuntimeResponse:
    interview = await get_executable_interview(
        session, workspace_id, interview_id, current_user, for_update=True
    )
    reject_enterprise_execution_for_application(interview)
    if interview.status == "COMPLETED":
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
    await session.commit()
    return await runtime_response(session, interview)


@router.post(
    "/interviews/{interview_id}/evaluation",
    response_model=InterviewEvaluationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_interview_evaluation(
    workspace_id: uuid.UUID,
    interview_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewEvaluationResponse:
    interview = await get_executable_interview(
        session, workspace_id, interview_id, current_user, for_update=True
    )
    if interview.status != "COMPLETED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="面试完成后才能生成评估报告",
        )
    answered_count = int(
        await session.scalar(
            select(func.count(InterviewAnswer.id)).where(
                InterviewAnswer.interview_session_id == interview.id
            )
        )
        or 0
    )
    if answered_count == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="没有可用于评估的回答",
        )
    evaluation = await session.scalar(
        select(InterviewEvaluation)
        .where(InterviewEvaluation.interview_session_id == interview.id)
        .with_for_update()
    )
    if evaluation is None:
        evaluation = InterviewEvaluation(
            interview_session_id=interview.id,
            status="PENDING",
        )
        session.add(evaluation)
    elif evaluation.status == "COMPLETED":
        return evaluation_response(evaluation)
    elif evaluation.status in {"PENDING", "GENERATING"}:
        return evaluation_response(evaluation)
    else:
        evaluation.status = "PENDING"
        evaluation.error_message = None
    await session.commit()
    await session.refresh(evaluation)
    try:
        generate_interview_evaluation.delay(str(evaluation.id))
    except Exception as error:
        evaluation.status = "FAILED"
        evaluation.error_message = str(error)[:2000]
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="评估任务提交失败",
        ) from error
    return evaluation_response(evaluation)


@router.get(
    "/interviews/{interview_id}/evaluation",
    response_model=InterviewEvaluationResponse,
)
async def get_interview_evaluation(
    workspace_id: uuid.UUID,
    interview_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewEvaluationResponse:
    await require_workspace_role(session, workspace_id, current_user.id, READ_ROLES)
    interview = await session.scalar(
        select(InterviewSession).where(
            InterviewSession.id == interview_id,
            InterviewSession.workspace_id == workspace_id,
        )
    )
    if interview is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="面试不存在")
    evaluation = await session.scalar(
        select(InterviewEvaluation).where(
            InterviewEvaluation.interview_session_id == interview.id
        )
    )
    if evaluation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="评估报告尚未生成")
    return evaluation_response(evaluation)


@router.delete("/interviews/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interview(
    workspace_id: uuid.UUID,
    interview_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_workspace_role(session, workspace_id, current_user.id, WRITE_ROLES)
    interview = await session.scalar(
        select(InterviewSession).where(
            InterviewSession.id == interview_id,
            InterviewSession.workspace_id == workspace_id,
        )
    )
    if interview is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="面试不存在")

    if interview.application_id is not None:
        application = await session.get(JobApplication, interview.application_id)
        if application is not None and application.status == "INTERVIEW":
            application.status = "REVIEWING"

        thread = await session.scalar(
            select(MessageThread).where(
                MessageThread.application_id == interview.application_id
            )
        )
        if thread is not None:
            await session.execute(
                sql_delete(PlatformMessage).where(
                    PlatformMessage.thread_id == thread.id,
                    or_(
                        PlatformMessage.interview_session_id == interview.id,
                        PlatformMessage.message_metadata[
                            "interview_session_id"
                        ].astext
                        == str(interview.id),
                        and_(
                            PlatformMessage.sender_type == "SYSTEM",
                            PlatformMessage.message_type == "APPLICATION_STATUS",
                            PlatformMessage.content
                            == "企业已创建技术面试，面试计划就绪后会发送邀请。",
                        ),
                    ),
                )
            )
            thread.updated_at = datetime.now(timezone.utc)

    await session.execute(
        sql_delete(InterviewSession).where(InterviewSession.id == interview.id)
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
