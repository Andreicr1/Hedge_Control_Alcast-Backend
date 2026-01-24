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
    audiences: list[str]
    issuers: list[str]
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


def _build_key_from_jwk(jwk_dict: Dict[str, Any], *, algorithm: str) -> Key:
    try:
        # Entra JWKS keys may not include an explicit "alg" field.
        # Passing the token algorithm avoids inference issues inside python-jose.
        return construct(jwk_dict, algorithm=algorithm)
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
    key = _build_key_from_jwk(jwk_dict, algorithm=alg)

    def _norm(s: str) -> str:
        return str(s or "").strip().rstrip("/")

    def _normalize_list(values: list[str]) -> list[str]:
        out: list[str] = []
        for v in values or []:
            nv = _norm(v)
            if nv and nv not in out:
                out.append(nv)
        return out

    allowed_issuers = set(_normalize_list(cfg.issuers))
    allowed_audiences = set(_normalize_list(cfg.audiences))

    try:
        pem = key.to_pem().decode("utf-8")
        claims = jwt.decode(
            token,
            pem,
            algorithms=[alg],
            options={
                "verify_aud": False,
                "verify_iss": False,
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

    # Manual issuer validation (support v1 + v2 issuers).
    iss = _norm(str(claims.get("iss") or ""))
    if allowed_issuers and iss not in allowed_issuers:
        raise EntraTokenValidationError("Invalid issuer")

    # Manual audience validation (allow GUID or api://GUID depending on setup).
    aud_claim = claims.get("aud")
    aud_values: list[str]
    if isinstance(aud_claim, list):
        aud_values = [str(v) for v in aud_claim if v is not None]
    else:
        aud_values = [str(aud_claim)]
    aud_norm = {_norm(v) for v in aud_values if _norm(v)}
    if allowed_audiences and not (aud_norm & allowed_audiences):
        raise EntraTokenValidationError("Invalid audience")

    # Extra safety: enforce tenant for single-tenant deployments.
    tid = str(claims.get("tid") or "")
    if cfg.tenant_id and tid and tid != cfg.tenant_id:
        raise EntraTokenValidationError("Invalid tenant")

    return claims
