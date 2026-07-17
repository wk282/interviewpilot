import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.workspace import Workspace, WorkspaceMember


INVITABLE_ROLES = {"ADMIN", "HR", "INTERVIEWER", "VIEWER"}
MEMBER_MANAGEMENT_ROLES = {"OWNER", "ADMIN"}


async def require_workspace_role(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    allowed_roles: set[str],
) -> tuple[Workspace, WorkspaceMember]:
    row = (
        await session.execute(
            select(Workspace, WorkspaceMember)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(
                Workspace.id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
    ).one_or_none()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工作空间不存在")

    workspace, membership = row
    if membership.role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有执行该操作的权限")
    return workspace, membership
