from typing import Callable, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import RoleName, User
from app.services.auth import decode_access_token


def _token_url() -> str:
    if settings.api_prefix:
        prefix = settings.api_prefix.rstrip("/")
        return f"{prefix}/auth/token"
    return "/auth/token"


oauth2_scheme = OAuth2PasswordBearer(tokenUrl=_token_url())
oauth2_optional = OAuth2PasswordBearer(tokenUrl=_token_url(), auto_error=False)

_DB_DEP = Depends(get_db)
_TOKEN_DEP = Depends(oauth2_scheme)
_TOKEN_OPT_DEP = Depends(oauth2_optional)


def get_current_user(db: Session = _DB_DEP, token: str = _TOKEN_DEP) -> User:
    subject = decode_access_token(token)
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user = db.query(User).filter(User.email == subject, User.active.is_(True)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


def get_current_user_optional(
    db: Session = _DB_DEP,
    token: Optional[str] = _TOKEN_OPT_DEP,
) -> Optional[User]:
    if not token:
        return None
    try:
        return get_current_user(db=db, token=token)
    except HTTPException:
        return None


_CURRENT_USER_OPT_DEP = Depends(get_current_user_optional)


def require_roles(*roles: RoleName) -> Callable:
    _CURRENT_USER_DEP = Depends(get_current_user)

    def dependency(user: User = _CURRENT_USER_DEP) -> User:
        if roles:
            user_role = getattr(getattr(user, "role", None), "name", None)
            # user.role.name is an Enum in our models; normalize to string.
            if isinstance(user_role, RoleName):
                user_role_value = user_role.value
            else:
                user_role_value = str(user_role) if user_role is not None else ""

            # Admin has access to everything
            if user_role_value == RoleName.admin.value:
                return user

            allowed = {(r.value if isinstance(r, RoleName) else str(r)) for r in roles}

            if user_role_value not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role"
                )
        return user

    return dependency


_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# Some POST endpoints are explicitly compute-only (no persistence, no domain writes).
# Auditoria is allowed to call these while remaining globally read-only for everything else.
_AUDITORIA_SAFE_POST_PATH_SUFFIXES = {
    "/cashflow/advanced/preview",
}


def enforce_auditoria_readonly(
    request: Request,
    user: Optional[User] = _CURRENT_USER_OPT_DEP,
) -> None:
    """Defense-in-depth: Auditoria is globally read-only.

    This is enforced at request boundary so that even if a route accidentally allows
    Auditoria in its role list, write attempts are still blocked.
    """

    if not user:
        return
    if not user.role:
        return
    method = request.method.upper()
    if user.role.name != RoleName.auditoria:
        return

    if method in _SAFE_METHODS:
        return

    # Allowlisted compute-only POST endpoints.
    if method == "POST":
        path = str(getattr(request.url, "path", "") or "")
        if any(path.endswith(suffix) for suffix in _AUDITORIA_SAFE_POST_PATH_SUFFIXES):
            return

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Auditoria is read-only")
