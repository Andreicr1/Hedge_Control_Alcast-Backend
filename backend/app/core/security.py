"""Security utilities.

Single source of truth for:
- Password hashing
- JWT token creation/verification

Note: app/services/auth.py is a thin wrapper around this module to keep existing
imports stable.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def hash_password(password: str) -> str:
    """Alias kept for compatibility with older call sites."""

    return get_password_hash(password)


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a JWT access token from a payload dict.

    Expected to include `sub` in `data` for user identity.
    """

    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def create_access_token_for_subject(subject: str, expires_minutes: Optional[int] = None) -> str:
    """Convenience helper: create token with a `sub` claim."""

    minutes = expires_minutes or settings.access_token_expire_minutes
    return create_access_token({"sub": subject}, expires_delta=timedelta(minutes=minutes))


def decode_access_token(token: str) -> Optional[dict]:
    """Decode JWT access token; returns payload or None if invalid."""

    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None


def decode_access_token_subject(token: str) -> Optional[str]:
    payload = decode_access_token(token)
    if not payload:
        return None
    subject = payload.get("sub")
    return str(subject) if subject else None
