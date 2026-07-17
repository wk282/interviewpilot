import uuid
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.core.config import settings


password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID:
    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    if payload.get("type") != "access" or not payload.get("sub"):
        raise jwt.InvalidTokenError("Invalid access token")
    return uuid.UUID(payload["sub"])


def create_candidate_interview_token(
    invitation_id: uuid.UUID,
    interview_session_id: uuid.UUID,
    expires_at: datetime,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(invitation_id),
        "interview_id": str(interview_session_id),
        "type": "candidate_interview",
        "iat": now,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_candidate_interview_token(token: str) -> tuple[uuid.UUID, uuid.UUID]:
    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    if (
        payload.get("type") != "candidate_interview"
        or not payload.get("sub")
        or not payload.get("interview_id")
    ):
        raise jwt.InvalidTokenError("Invalid candidate interview token")
    return uuid.UUID(payload["sub"]), uuid.UUID(payload["interview_id"])
