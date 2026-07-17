from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.db.models.user import AppUser
from app.schemas.auth import UserResponse


router = APIRouter(prefix="/users", tags=["用户"])


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: AppUser = Depends(get_current_user)) -> AppUser:
    return current_user
