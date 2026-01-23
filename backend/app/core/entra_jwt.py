"""Microsoft Entra ID (Azure AD) access token validation.

We accept Entra-issued JWTs (typically RS256) and validate:
- signature (using tenant JWKS)
- issuer
- audience

This module intentionally avoids adding new runtime dependencies.
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional

from jose import jwt
from jose.backends.base import Key
from jose.exceptions import ExpiredSignatureError, JWTClaimsError, JWTError
from jose.jwk import construct


@dataclass
class EntraValidationSettings:
    tenant_id: str
    audience: str
    issuer: str
    jwks_url: str
    # Refresh interval in seconds; Entra rotates keys periodically.
    jwks_refresh_seconds: int = 24 * 60 * 60


class EntraTokenValidationError(Exception):
    pass


class _JwksCache:
    def __init__(self) -> None:
        self._jwks: Optional[Dict[str, Any]] = None
        self._fetched_at: float = 0.0

    def _fetch_jwks(self, url: str) -> Dict[str, Any]:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
        doc = json.loads(raw)
        if not isinstance(doc, dict) or "keys" not in doc:
            raise EntraTokenValidationError("Invalid JWKS document")
        return doc

    def get_jwk(self, jwks_url: str, kid: str, refresh_seconds: int) -> Dict[str, Any]:
        now = time.time()

        should_refresh = (
            self._jwks is None
            or not self._jwks.get("keys")
            or (now - self._fetched_at) > refresh_seconds
        )

        if should_refresh:
            self._jwks = self._fetch_jwks(jwks_url)
            self._fetched_at = now

        keys = self._jwks.get("keys", []) if isinstance(self._jwks, dict) else []
        for k in keys:
            if isinstance(k, dict) and k.get("kid") == kid:
                return k

        # Key not found: refresh once immediately (covers rotation window).
        self._jwks = self._fetch_jwks(jwks_url)
        self._fetched_at = now
        keys = self._jwks.get("keys", []) if isinstance(self._jwks, dict) else []
        for k in keys:
            if isinstance(k, dict) and k.get("kid") == kid:
                return k

        raise EntraTokenValidationError("Signing key not found")


_JWKS_CACHE = _JwksCache()


def _build_key_from_jwk(jwk_dict: Dict[str, Any]) -> Key:
    try:
        return construct(jwk_dict)
    except Exception as e:
        raise EntraTokenValidationError("Failed to construct JWK") from e


def decode_and_validate_entra_access_token(
    token: str,
    cfg: EntraValidationSettings,
) -> Dict[str, Any]:
    """Validate an Entra access token and return its claims.

    Raises EntraTokenValidationError on validation failures.
    """

    try:
        headers = jwt.get_unverified_header(token)
    except JWTError as e:
        raise EntraTokenValidationError("Invalid token header") from e

    alg = str(headers.get("alg") or "").upper()
    kid = str(headers.get("kid") or "")
    if not kid:
        raise EntraTokenValidationError("Missing kid")

    # Entra access tokens are commonly RS256.
    if alg not in {"RS256", "RS384", "RS512"}:
        raise EntraTokenValidationError("Unsupported token algorithm")

    jwk_dict = _JWKS_CACHE.get_jwk(cfg.jwks_url, kid=kid, refresh_seconds=cfg.jwks_refresh_seconds)
    key = _build_key_from_jwk(jwk_dict)

    try:
        pem = key.to_pem().decode("utf-8")
        claims = jwt.decode(
            token,
            pem,
            algorithms=[alg],
            audience=cfg.audience,
            issuer=cfg.issuer,
            options={
                "verify_aud": True,
                "verify_iss": True,
                "verify_signature": True,
                "verify_exp": True,
            },
        )
    except ExpiredSignatureError as e:
        raise EntraTokenValidationError("Token expired") from e
    except JWTClaimsError as e:
        raise EntraTokenValidationError("Invalid token claims") from e
    except JWTError as e:
        raise EntraTokenValidationError("Invalid token") from e

    # Extra safety: enforce tenant for single-tenant deployments.
    tid = str(claims.get("tid") or "")
    if cfg.tenant_id and tid and tid != cfg.tenant_id:
        raise EntraTokenValidationError("Invalid tenant")

    return claims
