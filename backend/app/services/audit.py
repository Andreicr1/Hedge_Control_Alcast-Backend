import json
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


def audit_event(
    action: str,
    user_id: Optional[int],
    payload: Dict[str, Any],
    *,
    db: Session | None = None,
    idempotency_key: str | None = None,
    request_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Optional[int]:
    """
    Persist audit event to database; if DB write fails, fallback to stdout.

    Returns the created audit log id when available.
    """
    event = {
        "action": action,
        "user_id": user_id,
        "payload": payload,
        "timestamp": datetime.utcnow().isoformat(),
    }

    created_session = False
    session: Session | None = db
    try:
        from app import models

        if session is None:
            from app.database import SessionLocal

            session = SessionLocal()
            created_session = True

        audit_model = getattr(models, "AuditLog", None)
        if audit_model:
            if idempotency_key:
                existing = (
                    session.query(audit_model)
                    .filter(audit_model.idempotency_key == idempotency_key)
                    .first()
                )
                if existing is not None:
                    return getattr(existing, "id", None)

            log = audit_model(
                action=action,
                user_id=user_id,
                payload_json=json.dumps(payload or {}),
                idempotency_key=idempotency_key,
                request_id=request_id,
                ip=ip,
                user_agent=user_agent,
            )
            session.add(log)
            session.commit()
            try:
                session.refresh(log)
            except Exception:
                pass
            return getattr(log, "id", None)
        else:
            print(f"[AUDIT] {event}")
            return None
    except (SQLAlchemyError, Exception):
        print(f"[AUDIT-FAIL-DB] {event}")
        return None
    finally:
        if created_session and session is not None:
            try:
                session.close()
            except Exception:
                pass

    return None
