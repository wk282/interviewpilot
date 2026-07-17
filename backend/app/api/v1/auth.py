from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.db.models.user import AppUser
from app.db.models.workspace import Workspace, WorkspaceMember
from app.db.session import get_db_session
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest


router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    existing_user = await session.scalar(
        select(AppUser).where(AppUser.email == request.email)
    )
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已注册")

    try:
        user = AppUser(
            email=request.email,
            hashed_password=hash_password(request.password),
            display_name=request.display_name,
        )
        session.add(user)
        await session.flush()

        workspace_name = (
            f"{request.display_name}的个人空间"
            if request.account_type == "PERSONAL"
            else request.organization_name
        )
        workspace = Workspace(
            name=workspace_name,
            type=request.account_type,
            created_by=user.id,
        )
        session.add(workspace)
        await session.flush()

        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=user.id,
                role="OWNER",
            )
        )
        await session.commit()
        await session.refresh(user)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="账号或工作空间已存在")
    except Exception:
        await session.rollback()
        raise

    return AuthResponse(access_token=create_access_token(user.id), user=user)


@router.post("/login", response_model=AuthResponse)
async def login(
    request: LoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    user = await session.scalar(select(AppUser).where(AppUser.email == request.email))

    if user is None or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被停用")

    return AuthResponse(access_token=create_access_token(user.id), user=user)
