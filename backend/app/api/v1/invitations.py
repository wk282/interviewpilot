import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.db.models.invitation import WorkspaceInvitation
from app.db.models.user import AppUser
from app.db.models.workspace import Workspace, WorkspaceMember
from app.db.session import get_db_session
from app.schemas.auth import AuthResponse
from app.schemas.invitation import InvitationAcceptRequest, InvitationInfoResponse


router = APIRouter(prefix="/invitations", tags=["企业邀请"])


def hash_invitation_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def get_pending_invitation(token: str, session: AsyncSession) -> WorkspaceInvitation:
    invitation = await session.scalar(
        select(WorkspaceInvitation).where(
            WorkspaceInvitation.token_hash == hash_invitation_token(token)
        )
    )
    if invitation is None or invitation.status != "PENDING":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="邀请不存在或已失效")

    if invitation.expires_at <= datetime.now(timezone.utc):
        invitation.status = "EXPIRED"
        await session.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="邀请已过期")
    return invitation


@router.get("/{token}", response_model=InvitationInfoResponse)
async def get_invitation(
    token: str,
    session: AsyncSession = Depends(get_db_session),
) -> InvitationInfoResponse:
    invitation = await get_pending_invitation(token, session)
    workspace = await session.get(Workspace, invitation.workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="企业工作空间不存在")
    return InvitationInfoResponse(
        workspace_name=workspace.name,
        email=invitation.email,
        role=invitation.role,
        expires_at=invitation.expires_at,
    )


@router.post("/{token}/accept", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def accept_invitation(
    token: str,
    request: InvitationAcceptRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    invitation = await get_pending_invitation(token, session)
    existing_user = await session.scalar(select(AppUser).where(AppUser.email == invitation.email))
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该邮箱已有账号；当前企业员工邀请仅支持新账号",
        )

    try:
        user = AppUser(
            email=invitation.email,
            hashed_password=hash_password(request.password),
            display_name=request.display_name,
        )
        session.add(user)
        await session.flush()

        session.add(
            WorkspaceMember(
                workspace_id=invitation.workspace_id,
                user_id=user.id,
                role=invitation.role,
            )
        )
        invitation.status = "ACCEPTED"
        invitation.accepted_by = user.id
        invitation.accepted_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(user)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="账号或企业成员关系已存在")
    except Exception:
        await session.rollback()
        raise

    return AuthResponse(access_token=create_access_token(user.id), user=user)
