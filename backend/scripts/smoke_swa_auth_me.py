"""Smoke test for /api/auth/me through Azure Static Web Apps.

This script is designed for the SWA + integrated Azure Functions proxy setup.
It sends BOTH headers:
- Authorization: Bearer <token>
- x-hc-authorization: Bearer <token>

Usage (PowerShell):
  cd c:\Projetos\Hedge_Control_Alcast-Backend\backend
  .\.venv311\Scripts\python.exe scripts\smoke_swa_auth_me.py --base-url "https://<your-swa-host>" --token "<ACCESS_TOKEN>"

Tip:
- The frontend stores the access token in localStorage under key: auth_token
  (see Frontend src/api/client.ts). You can copy it from DevTools.

Security:
- Avoid pasting real tokens into logs/tickets.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request


def _normalize_base_url(base_url: str) -> str:
    s = str(base_url or '').strip().rstrip('/')
    if not s.startswith('http://') and not s.startswith('https://'):
        raise SystemExit('base-url must start with http:// or https://')
    return s


def _get(url: str, token: str) -> tuple[int, str]:
    bearer = f"Bearer {token.strip()}"
    req = urllib.request.Request(
        url,
        method='GET',
        headers={
            'Accept': 'application/json',
            'Authorization': bearer,
            'x-hc-authorization': bearer,
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return int(resp.status), resp.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8') if e.fp is not None else ''
        return int(e.code), body


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', required=True, help='SWA host, e.g. https://<name>.azurestaticapps.net')
    parser.add_argument('--token', required=True, help='Access token (JWT)')
    args = parser.parse_args()

    base = _normalize_base_url(args.base_url)
    url = f"{base}/api/auth/me"

    status, body = _get(url, token=args.token)

    print(f"GET {url}")
    print(f"Status: {status}")

    # Try JSON pretty output.
    try:
        parsed = json.loads(body) if body else None
        print(json.dumps(parsed, indent=2, ensure_ascii=False))
    except Exception:
        if body:
            print(body)

    if status == 200:
        return 0
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
