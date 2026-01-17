from typing import Optional

from app.core.security import (
    create_access_token_for_subject,
    decode_access_token_subject,
    hash_password,
    verify_password,
)

# Re-export for backwards compatibility
__all__ = [
    "create_access_token",
    "decode_access_token",
    "hash_password",
    "verify_password",
]


def create_access_token(subject: str, expires_minutes: Optional[int] = None) -> str:
    return create_access_token_for_subject(subject=subject, expires_minutes=expires_minutes)


def decode_access_token(token: str) -> Optional[str]:
    return decode_access_token_subject(token)
