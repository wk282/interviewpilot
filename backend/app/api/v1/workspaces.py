import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.permissions import MEMBER_MANAGEMENT_ROLES, require_workspace_role
from app.db.models.invitation import WorkspaceInvitation
from app.db.models.user import AppUser
from app.db.models.workspace import Workspace, WorkspaceMember
from app.db.session import get_db_session
from app.schemas.invitation import InvitationCreateRequest, InvitationCreateResponse, WorkspaceMemberResponse
from app.schemas.workspace import WorkspaceResponse


router = APIRouter(prefix="/workspaces", tags=["工作空间"])


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[WorkspaceResponse]:
    rows = (
        await session.execute(
            select(Workspace, WorkspaceMember.role)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == current_user.id)
            .order_by(Workspace.type, Workspace.created_at)
        )
    ).all()

    return [
        WorkspaceResponse(
            id=workspace.id,
            name=workspace.name,
            type=workspace.type,
            role=role,
        )
        for workspace, role in rows
    ]


@router.post(
    "/{workspace_id}/invitations",
    response_model=InvitationCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_invitation(
    workspace_id: uuid.UUID,
    request: InvitationCreateRequest,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> InvitationCreateResponse:
    workspace, _ = await require_workspace_role(
        session, workspace_id, current_user.id, MEMBER_MANAGEMENT_ROLES
    )
    if workspace.type != "ORGANIZATION":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="个人工作空间不能邀请成员")

    existing_user = await session.scalar(select(AppUser).where(AppUser.email == request.email))
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已有平台账号")

    pending = await session.scalar(
        select(WorkspaceInvitation).where(
            WorkspaceInvitation.workspace_id == workspace_id,
            WorkspaceInvitation.email == request.email,
            WorkspaceInvitation.status == "PENDING",
            WorkspaceInvitation.expires_at > datetime.now(timezone.utc),
        )
    )
    if pending is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已有未过期邀请")

    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    invitation = WorkspaceInvitation(
        workspace_id=workspace_id,
        email=request.email,
        role=request.role,
        token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        invited_by=current_user.id,
        expires_at=expires_at,
    )
    session.add(invitation)
    await session.commit()
    await session.refresh(invitation)

    return InvitationCreateResponse(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        expires_at=invitation.expires_at,
        invitation_token=raw_token,
    )


@router.get("/{workspace_id}/members", response_model=list[WorkspaceMemberResponse])
async def list_members(
    workspace_id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[WorkspaceMemberResponse]:
    workspace, _ = await require_workspace_role(
        session, workspace_id, current_user.id, MEMBER_MANAGEMENT_ROLES
    )
    if workspace.type != "ORGANIZATION":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="个人工作空间没有成员管理")

    rows = (
        await session.execute(
            select(AppUser, WorkspaceMember)
            .join(WorkspaceMember, WorkspaceMember.user_id == AppUser.id)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .order_by(WorkspaceMember.joined_at)
        )
    ).all()
    return [
        WorkspaceMemberResponse(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=membership.role,
            joined_at=membership.joined_at,
        )
        for user, membership in rows
    ]
