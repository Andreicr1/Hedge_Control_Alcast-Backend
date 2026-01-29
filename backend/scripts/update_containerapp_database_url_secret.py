"""Ops helper to keep Azure Container App DB secrets consistent.

This script:
- Reads an existing secret containing the database password (e.g. 'db-password')
- URL-encodes it
- Writes/overwrites another secret (e.g. 'database-url') with a full SQLAlchemy DSN

It intentionally avoids printing credentials.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.parse
import shutil
from pathlib import Path


def _find_az() -> str:
    az = shutil.which("az") or shutil.which("az.cmd")
    if az:
        return az

    # Common Windows install locations
    candidates = [
        r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd",
        r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az",
        r"C:\Program Files (x86)\Microsoft SDKs\Azure\CLI2\wbin\az.cmd",
        r"C:\Program Files (x86)\Microsoft SDKs\Azure\CLI2\wbin\az",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate

    raise FileNotFoundError(
        "Azure CLI ('az') not found. Ensure Azure CLI is installed and available on PATH."
    )


def _az(*args: str) -> str:
    az = _find_az()
    proc = subprocess.run([az, *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "az command failed")
    return proc.stdout


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resource-group", "-g", required=True)
    parser.add_argument("--containerapp", "-n", required=True)
    parser.add_argument("--db-host", required=True)
    parser.add_argument("--db-name", required=True)
    parser.add_argument("--db-user", default="postgres")
    parser.add_argument("--password-secret", default="db-password")
    parser.add_argument("--database-url-secret", default="database-url")
    parser.add_argument("--sslmode", default="require")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    secret_raw = _az(
        "containerapp",
        "secret",
        "show",
        "-g",
        args.resource_group,
        "-n",
        args.containerapp,
        "--secret-name",
        args.password_secret,
        "-o",
        "json",
    )
    password = json.loads(secret_raw)["value"]
    password_enc = urllib.parse.quote(password, safe="")

    database_url = (
        f"postgresql+psycopg://{args.db_user}:{password_enc}@{args.db_host}:5432/{args.db_name}"
        f"?sslmode={urllib.parse.quote(args.sslmode, safe='')}"
    )

    if args.dry_run:
        print(
            "DRY RUN: would set secret. "
            f"scheme=postgresql+psycopg host={args.db_host} db={args.db_name} user={args.db_user} sslmode={args.sslmode}"
        )
        return 0

    _az(
        "containerapp",
        "secret",
        "set",
        "-g",
        args.resource_group,
        "-n",
        args.containerapp,
        "--secrets",
        f"{args.database_url_secret}={database_url}",
        "-o",
        "none",
    )

    print(
        "OK: updated Container App secret (credentials not printed): "
        f"{args.database_url_secret} -> postgresql+psycopg://{args.db_user}@{args.db_host}:5432/{args.db_name}?sslmode={args.sslmode}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
