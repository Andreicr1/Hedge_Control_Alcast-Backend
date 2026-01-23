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

    cfg = EntraValidationSettings(
        tenant_id=str(settings.entra_tenant_id or '').strip(),
        audience=str(settings.entra_audience or '').strip(),
        issuer=str(settings.entra_issuer or '').strip(),
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
