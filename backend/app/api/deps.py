import uuid
from typing import Callable, Optional

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.core.entra_jwt import (
    EntraTokenValidationError,
    EntraValidationSettings,
    decode_and_validate_entra_access_token,
)
from app.database import get_db
from app.models import RoleName, User
from app.services.auth import decode_access_token, hash_password


def _token_url() -> str:
    if settings.api_prefix:
        prefix = settings.api_prefix.rstrip("/")
        return f"{prefix}/auth/token"
    return "/auth/token"


oauth2_scheme = OAuth2PasswordBearer(tokenUrl=_token_url())
oauth2_optional = OAuth2PasswordBearer(tokenUrl=_token_url(), auto_error=False)

_DB_DEP = Depends(get_db)
_TOKEN_OPT_DEP = Depends(oauth2_optional)


def _entra_cfg() -> EntraValidationSettings:
    tenant_id = str(settings.entra_tenant_id or "").strip()
    raw_aud = str(settings.entra_audience or "").strip()
    raw_iss = str(settings.entra_issuer or "").strip()
    raw_jwks = str(settings.entra_jwks_url or "").strip()

    def _split_csv(s: str) -> list[str]:
        # Allow comma/semicolon separated values in env.
        parts: list[str] = []
        for chunk in (s or "").replace(";", ",").split(","):
            v = str(chunk).strip()
            if v:
                parts.append(v)
        return parts

    # Audiences: accept either GUID or api://GUID depending on how the API was configured.
    audiences = _split_csv(raw_aud)
    if raw_aud and raw_aud.lower().startswith("api://"):
        maybe_guid = raw_aud[6:].strip().strip("/")
        if maybe_guid:
            audiences.append(maybe_guid)
    elif raw_aud and raw_aud.count("-") >= 4:
        audiences.append(f"api://{raw_aud}")

    # Issuers: accept both v1 and v2 issuer shapes for a tenant.
    issuers = _split_csv(raw_iss)
    if tenant_id and tenant_id.count("-") >= 4:
        issuers.append(f"https://login.microsoftonline.com/{tenant_id}/v2.0")
        issuers.append(f"https://sts.windows.net/{tenant_id}/")

    # JWKS URL: if not provided, default to tenant v2 discovery keys endpoint.
    # This matches our .env.example guidance and supports validating both v1/v2 issuer shapes.
    jwks_url = raw_jwks
    if not jwks_url and tenant_id and tenant_id.count("-") >= 4:
        jwks_url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"

    return EntraValidationSettings(
        tenant_id=tenant_id,
        audiences=audiences,
        issuers=issuers,
        jwks_url=jwks_url,
    )


def _extract_entra_email(claims: dict) -> Optional[str]:
    # Common delegated token claims for internal users.
    for key in ("preferred_username", "upn", "email", "unique_name"):
        val = claims.get(key)
        if isinstance(val, str) and "@" in val:
            return val.strip().lower()

    # Some Entra access tokens (depending on app registration / optional claims)
    # do not include a UPN/email-like claim. Fall back to a stable object id.
    oid = claims.get("oid") or claims.get("sub")
    if isinstance(oid, str) and oid.strip():
        # Single-tenant deployment: keep it unique and email-shaped.
        tid = claims.get("tid")
        suffix = "entra.local"
        if isinstance(tid, str) and tid.count("-") >= 4:
            suffix = f"{tid}.entra.local"
        return f"{oid.strip().lower()}@{suffix}"
    return None


def _map_entra_roles_to_role_name(roles_claim: object) -> Optional[RoleName]:
    if roles_claim is None:
        return None

    roles: list[str]
    if isinstance(roles_claim, str):
        roles = [roles_claim]
    elif isinstance(roles_claim, list):
        roles = [str(r) for r in roles_claim if r is not None]
    else:
        roles = [str(roles_claim)]

    normalized = {str(r).strip().lower() for r in roles if str(r).strip()}

    # Back-compat aliases (during transition)
    if "compras" in normalized or "vendas" in normalized:
        normalized.add("comercial")

    # Priority: admin > financeiro > comercial > auditoria > estoque
    if "admin" in normalized:
        return RoleName.admin
    if "financeiro" in normalized:
        return RoleName.financeiro
    if "comercial" in normalized:
        return RoleName.comercial
    if "auditoria" in normalized:
        return RoleName.auditoria
    if "estoque" in normalized:
        return RoleName.estoque

    return None


def _ensure_role_row(db: Session, role_name: RoleName) -> int:
    from app.models import Role

    role = db.query(Role).filter(Role.name == role_name).first()
    if role:
        return int(role.id)

    role = Role(name=role_name, description=str(role_name.value))
    db.add(role)
    db.flush()
    return int(role.id)


def _get_or_create_user_from_entra_claims(db: Session, claims: dict) -> User:
    email = _extract_entra_email(claims)
    if not email:
        detail = "Invalid credentials"
        env = str(getattr(settings, "environment", "") or "").lower()
        if env in {"dev", "development", "test"}:
            detail = (
                "Entra token is missing an identifiable user claim. "
                "Configure optional claims (preferred_username/email) or ensure oid/sub is present."
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

    role_name = _map_entra_roles_to_role_name(claims.get("roles"))
    if not role_name:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")

    user = db.query(User).filter(User.email == email).first()
    desired_role_id = _ensure_role_row(db, role_name)

    display_name = claims.get("name")
    name = (
        str(display_name).strip()
        if isinstance(display_name, str) and display_name.strip()
        else email
    )

    if not user:
        # Entra users don't authenticate with local password, but our schema requires a hash.
        user = User(
            email=email,
            name=name,
            hashed_password=hash_password(uuid.uuid4().hex),
            role_id=desired_role_id,
            active=True,
        )
        db.add(user)
        db.flush()
        db.refresh(user)
        return user

    changed = False
    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive"
        )
    if user.role_id != desired_role_id:
        user.role_id = desired_role_id
        changed = True
    if name and getattr(user, "name", "") != name:
        user.name = name
        changed = True
    if changed:
        db.add(user)
        db.flush()
        db.refresh(user)
    return user


def _extract_bearer_from_headers(request: Request) -> Optional[str]:
    # Some hosting layers may strip/override the standard Authorization header.
    # Accept a small set of custom headers (forwarded by our SWA Functions proxy).
    raw = (
        request.headers.get("authorization")
        or request.headers.get("x-hc-authorization")
        or request.headers.get("x-authorization")
        or request.headers.get("x-auth-token")
    )
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.lower().startswith("bearer "):
        return s.split(" ", 1)[1].strip()
    return s


def get_current_user(
    request: Request,
    db: Session = _DB_DEP,
    token: Optional[str] = _TOKEN_OPT_DEP,
) -> User:
    if not token:
        token = _extract_bearer_from_headers(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    # Heuristic: inspect token header algorithm. Entra access tokens are typically RS256.
    # Local tokens are HS256 by default.
    alg = ""
    try:
        from jose import jwt as jose_jwt

        hdr = jose_jwt.get_unverified_header(token)
        alg = str(hdr.get("alg") or "")
    except Exception:
        alg = ""

    mode = str(settings.auth_mode or "local").strip().lower()

    if alg.upper().startswith("RS"):
        if mode not in {"entra", "both"}:
            detail = "Invalid credentials"
            env = str(getattr(settings, "environment", "") or "").lower()
            if env in {"dev", "development", "test"}:
                detail = "AUTH_MODE=local does not accept Entra (RS*) tokens. Set AUTH_MODE=entra or both."
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)
        try:
            claims = decode_and_validate_entra_access_token(token, _entra_cfg())
        except EntraTokenValidationError as e:
            detail = "Invalid credentials"
            env = str(getattr(settings, "environment", "") or "").lower()
            if env in {"dev", "development", "test"}:
                detail = f"Invalid Entra token: {str(e)}"
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)
        return _get_or_create_user_from_entra_claims(db, claims)

    # Default: treat as local token.
    if mode == "entra":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

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
    request: Request,
    db: Session = _DB_DEP,
    token: Optional[str] = _TOKEN_OPT_DEP,
) -> Optional[User]:
    if not token:
        token = _extract_bearer_from_headers(request)
        if not token:
            return None
    try:
        return get_current_user(request=request, db=db, token=token)
    except HTTPException:
        return None


_CURRENT_USER_OPT_DEP = Depends(get_current_user_optional)


def require_roles(*roles: RoleName) -> Callable:
    _CURRENT_USER_DEP = Depends(get_current_user)

    legacy_to_canonical = {
        RoleName.compras.value: RoleName.comercial.value,
        RoleName.vendas.value: RoleName.comercial.value,
    }

    def canonicalize(role_value: str) -> str:
        return legacy_to_canonical.get(role_value, role_value)

    def dependency(user: User = _CURRENT_USER_DEP) -> User:
        if roles:
            user_role = getattr(getattr(user, "role", None), "name", None)
            # user.role.name is an Enum in our models; normalize to string.
            if isinstance(user_role, RoleName):
                user_role_value = user_role.value
            else:
                user_role_value = str(user_role) if user_role is not None else ""

            user_role_value = canonicalize(user_role_value)

            # Admin has access to everything
            if user_role_value == RoleName.admin.value:
                return user

            allowed = {canonicalize(r.value if isinstance(r, RoleName) else str(r)) for r in roles}

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


def require_ingest_token(
    authorization: str | None = Header(default=None, description="Bearer ingest token"),
) -> None:
    """Require operational ingest token.

    This endpoint auth is intentionally decoupled from user auth (OAuth/JWT),
    so that local operational scripts can post data without a user session.
    """

    expected = (settings.ingest_token or "").strip()
    if not expected:
        # Misconfiguration: disable ingestion rather than allowing open writes.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingestion is not configured",
        )

    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    token = parts[1].strip()
    if token != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")

    return None
