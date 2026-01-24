"""Validate a Microsoft Entra ID (Azure AD) access token against the backend settings.

Usage (PowerShell):
  $env:AUTH_MODE='entra'
  $env:ENTRA_TENANT_ID='<tenant-guid>'
  $env:ENTRA_AUDIENCE='api://<api-app-client-id>'
  python scripts/entra_validate_token.py --token '<access_token>'

Notes:
- This script uses the same validator as the API (JWKS + RS256 + iss/aud/exp/tid).
- Do NOT paste real tokens into logs or tickets.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Optional

from app.config import settings
from app.core.entra_jwt import EntraTokenValidationError, EntraValidationSettings
from app.core.entra_jwt import decode_and_validate_entra_access_token


def _map_roles_to_internal(roles_claim: Any) -> Optional[str]:
    if roles_claim is None:
        return None

    roles: list[str]
    if isinstance(roles_claim, str):
        roles = [roles_claim]
    elif isinstance(roles_claim, list):
        roles = [str(r) for r in roles_claim if r is not None]
    else:
        roles = [str(roles_claim)]

    normalized = {r.strip().lower() for r in roles if str(r).strip()}

    # Back-compat aliases
    if 'compras' in normalized or 'vendas' in normalized:
        normalized.add('comercial')

    if 'admin' in normalized:
        return 'admin'
    if 'financeiro' in normalized:
        return 'financeiro'
    if 'comercial' in normalized:
        return 'comercial'
    if 'auditoria' in normalized:
        return 'auditoria'
    if 'estoque' in normalized:
        return 'estoque'

    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--token', required=True, help='Entra access token (JWT)')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print claims JSON')
    args = parser.parse_args()

    tenant_id = str(settings.entra_tenant_id or '').strip()
    raw_aud = str(settings.entra_audience or '').strip()
    raw_iss = str(settings.entra_issuer or '').strip()

    def _split_csv(s: str) -> list[str]:
        parts: list[str] = []
        for chunk in (s or '').replace(';', ',').split(','):
            v = str(chunk).strip()
            if v:
                parts.append(v)
        return parts

    audiences = _split_csv(raw_aud)
    if raw_aud and raw_aud.lower().startswith('api://'):
        maybe_guid = raw_aud[6:].strip().strip('/')
        if maybe_guid:
            audiences.append(maybe_guid)
    elif raw_aud and raw_aud.count('-') >= 4:
        audiences.append(f'api://{raw_aud}')

    issuers = _split_csv(raw_iss)
    if tenant_id and tenant_id.count('-') >= 4:
        issuers.append(f'https://login.microsoftonline.com/{tenant_id}/v2.0')
        issuers.append(f'https://sts.windows.net/{tenant_id}/')

    cfg = EntraValidationSettings(
        tenant_id=tenant_id,
        audiences=audiences,
        issuers=issuers,
        jwks_url=str(settings.entra_jwks_url or '').strip(),
    )

    try:
        claims = decode_and_validate_entra_access_token(args.token, cfg)
    except EntraTokenValidationError as e:
        print('INVALID:', str(e))
        return 2

    summary = {
        'tid': claims.get('tid'),
        'iss': claims.get('iss'),
        'aud': claims.get('aud'),
        'scp': claims.get('scp'),
        'roles': claims.get('roles'),
        'preferred_username': claims.get('preferred_username') or claims.get('upn') or claims.get('email'),
        'name': claims.get('name'),
        'internal_role': _map_roles_to_internal(claims.get('roles')),
    }

    print('VALID: token signature + claims OK')
    print(json.dumps(summary, indent=2 if args.pretty else None, ensure_ascii=False))

    if not summary['internal_role']:
        print('WARNING: roles claim missing/unknown; backend will return 403')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
