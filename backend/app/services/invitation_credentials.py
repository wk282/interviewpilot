import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.logger import logger


def credential_cipher() -> Fernet:
    derived_key = hashlib.sha256(
        f"interview-invitation:{settings.JWT_SECRET_KEY}".encode("utf-8")
    ).digest()
    return Fernet(base64.urlsafe_b64encode(derived_key))


def encrypt_invitation_credential(value: str) -> str:
    return credential_cipher().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_invitation_credential(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return credential_cipher().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError) as error:
        logger.warning(f"Invitation credential decryption failed: {error}")
        return None
