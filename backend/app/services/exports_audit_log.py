from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app import models


def build_audit_log_csv_bytes(
    db: Session,
    *,
    as_of: datetime | None,
) -> bytes:
    """Build a deterministic audit log CSV export.

    Determinism rules:
    - Stable header ordering
    - Rows ordered by (created_at, id)
    - payload_json is canonicalized when it is valid JSON
    """

    headers = [
        "id",
        "created_at",
        "action",
        "user_id",
        "request_id",
        "ip",
        "user_agent",
        "payload_json",
    ]

    q = db.query(models.AuditLog)
    if as_of is not None:
        q = q.filter(models.AuditLog.created_at <= as_of)

    rows = q.order_by(models.AuditLog.created_at.asc(), models.AuditLog.id.asc()).all()

    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=headers, lineterminator="\n")
    writer.writeheader()

    for r in rows:
        payload = _canonicalize_json_string(r.payload_json)
        writer.writerow(
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else "",
                "action": r.action,
                "user_id": r.user_id if r.user_id is not None else "",
                "request_id": r.request_id or "",
                "ip": r.ip or "",
                "user_agent": r.user_agent or "",
                "payload_json": payload,
            }
        )

    return buf.getvalue().encode("utf-8")


def _canonicalize_json_string(payload_json: str | None) -> str:
    if not payload_json:
        return ""

    try:
        parsed: Any = json.loads(payload_json)
    except Exception:
        return str(payload_json)

    try:
        return json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        return str(payload_json)
