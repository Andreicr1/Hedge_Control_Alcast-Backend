from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.core.timeline_mentions import normalize_mentions
from app.core.timeline_permissions import can_write_timeline
from app.core.timeline_threads import thread_key_for
from app.core.timeline_v1 import TIMELINE_V1_EVENT_TYPES
from app.database import get_db
from app.schemas import TimelineEventCreate, TimelineEventRead
from app.schemas.timeline import (
    TimelineHumanAttachmentCreate,
    TimelineHumanAttachmentUploadRead,
    TimelineHumanCommentCorrectionCreate,
    TimelineHumanCommentCreate,
)
from app.services.audit import audit_event
from app.services.timeline_attachments_storage import (
    resolve_local_path_from_storage_uri,
    write_timeline_attachment_bytes,
)
from app.services.timeline_emitters import correlation_id_from_request_id, emit_timeline_event

router = APIRouter(prefix="/timeline", tags=["timeline"])


def _visibility_filter_for(user: models.User):
    if user.role and user.role.name == models.RoleName.admin:
        return None
    if user.role and user.role.name == models.RoleName.financeiro:
        return models.TimelineEvent.visibility.in_(["all", "finance"])
    return models.TimelineEvent.visibility == "all"


@router.get("", response_model=List[TimelineEventRead])
def list_timeline(
    subject_type: str = Query(..., min_length=1, max_length=32),  # noqa: B008
    subject_id: int = Query(..., ge=1),  # noqa: B008
    limit: int = Query(200, ge=1, le=500),  # noqa: B008
    before: Optional[datetime] = Query(None),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
    current_user: models.User = Depends(require_roles()),  # noqa: B008
):
    q = db.query(models.TimelineEvent).filter(
        and_(
            models.TimelineEvent.subject_type == subject_type,
            models.TimelineEvent.subject_id == subject_id,
        )
    )

    vis = _visibility_filter_for(current_user)
    if vis is not None:
        q = q.filter(vis)

    if before is not None:
        q = q.filter(models.TimelineEvent.occurred_at < before)

    return (
        q.order_by(desc(models.TimelineEvent.occurred_at), desc(models.TimelineEvent.id))
        .limit(limit)
        .all()
    )


@router.get("/recent", response_model=List[TimelineEventRead])
def recent_timeline(
    limit: int = Query(50, ge=1, le=200),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
    current_user: models.User = Depends(require_roles()),  # noqa: B008
):
    q = db.query(models.TimelineEvent)

    vis = _visibility_filter_for(current_user)
    if vis is not None:
        q = q.filter(vis)

    return (
        q.order_by(desc(models.TimelineEvent.occurred_at), desc(models.TimelineEvent.id))
        .limit(limit)
        .all()
    )


@router.post("/events", response_model=TimelineEventRead, status_code=status.HTTP_201_CREATED)
def create_timeline_event(
    request: Request,
    payload: TimelineEventCreate,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: models.User = Depends(require_roles()),  # noqa: B008
):
    if payload.event_type not in TIMELINE_V1_EVENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "timeline.invalid_event_type",
                "event_type": payload.event_type,
                "allowed_event_types": sorted(TIMELINE_V1_EVENT_TYPES),
            },
        )

    # Enforce finance-only visibility writes.
    if payload.visibility == "finance":
        if not current_user.role or current_user.role.name not in (
            models.RoleName.financeiro,
            models.RoleName.admin,
        ):
            raise HTTPException(
                status_code=403,
                detail="Insufficient role for finance-only timeline events",
            )

    if payload.idempotency_key:
        existing = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == payload.event_type)
            .filter(models.TimelineEvent.idempotency_key == payload.idempotency_key)
            .first()
        )
        if existing is not None:
            return existing

    correlation_id = payload.correlation_id or str(uuid.uuid4())

    audit_id = audit_event(
        "timeline.event.created",
        getattr(current_user, "id", None),
        {
            "event_type": payload.event_type,
            "subject_type": payload.subject_type,
            "subject_id": payload.subject_id,
            "visibility": payload.visibility,
            "correlation_id": correlation_id,
            "supersedes_event_id": payload.supersedes_event_id,
        },
        db=db,
        request_id=request.headers.get("X-Request-ID"),
        ip=getattr(request.client, "host", None) if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )

    ev = models.TimelineEvent(
        event_type=payload.event_type,
        occurred_at=payload.occurred_at or datetime.utcnow(),
        subject_type=payload.subject_type,
        subject_id=payload.subject_id,
        correlation_id=correlation_id,
        supersedes_event_id=payload.supersedes_event_id,
        idempotency_key=payload.idempotency_key,
        actor_user_id=getattr(current_user, "id", None),
        audit_log_id=audit_id,
        visibility=payload.visibility,
        payload=payload.payload,
        meta=payload.meta,
    )

    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


@router.post(
    "/human/comments",
    response_model=TimelineEventRead,
    status_code=status.HTTP_201_CREATED,
)
def create_human_comment(
    request: Request,
    payload: TimelineHumanCommentCreate,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: models.User = Depends(require_roles()),  # noqa: B008
):
    # RBAC: Auditoria never writes; finance visibility only for Financeiro/Admin.
    if not can_write_timeline(current_user, payload.visibility):
        raise HTTPException(status_code=403, detail="Insufficient role for timeline write")

    event_type = "human.comment.created"
    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))
    thread_key = thread_key_for(payload.subject_type, payload.subject_id)
    mentions = normalize_mentions(payload.mentions)

    event_payload = {
        "body": payload.body,
        "thread_key": thread_key,
        "mentions": mentions,
        "attachments": payload.attachments,
    }

    audit_id = audit_event(
        "timeline.human.comment.created",
        getattr(current_user, "id", None),
        {
            "event_type": event_type,
            "subject_type": payload.subject_type,
            "subject_id": payload.subject_id,
            "visibility": payload.visibility,
            "correlation_id": correlation_id,
        },
        db=db,
        request_id=request.headers.get("X-Request-ID"),
        ip=getattr(request.client, "host", None) if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )

    if payload.idempotency_key:
        result = emit_timeline_event(
            db=db,
            event_type=event_type,
            subject_type=payload.subject_type,
            subject_id=payload.subject_id,
            correlation_id=correlation_id,
            idempotency_key=payload.idempotency_key,
            visibility=payload.visibility,
            payload=event_payload,
            meta=payload.meta,
            actor_user_id=getattr(current_user, "id", None),
            audit_log_id=audit_id,
        )

        for mention in mentions:
            emit_timeline_event(
                db=db,
                event_type="human.mentioned",
                subject_type=payload.subject_type,
                subject_id=payload.subject_id,
                correlation_id=correlation_id,
                idempotency_key=f"{payload.idempotency_key}:mention:{mention}",
                visibility=payload.visibility,
                payload={
                    "thread_key": thread_key,
                    "mention": mention,
                    "comment_event_id": result.event.id,
                },
                actor_user_id=getattr(current_user, "id", None),
                audit_log_id=audit_id,
            )
        return result.event

    ev = models.TimelineEvent(
        event_type=event_type,
        subject_type=payload.subject_type,
        subject_id=payload.subject_id,
        correlation_id=correlation_id,
        visibility=payload.visibility,
        payload=event_payload,
        meta=payload.meta,
        actor_user_id=getattr(current_user, "id", None),
        audit_log_id=audit_id,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)

    for mention in mentions:
        emit_timeline_event(
            db=db,
            event_type="human.mentioned",
            subject_type=payload.subject_type,
            subject_id=payload.subject_id,
            correlation_id=correlation_id,
            idempotency_key=f"comment:{ev.id}:mention:{mention}",
            visibility=payload.visibility,
            payload={"thread_key": thread_key, "mention": mention, "comment_event_id": ev.id},
            actor_user_id=getattr(current_user, "id", None),
            audit_log_id=audit_id,
        )
    return ev


@router.post(
    "/human/comments/corrections",
    response_model=TimelineEventRead,
    status_code=status.HTTP_201_CREATED,
)
def correct_human_comment(
    request: Request,
    payload: TimelineHumanCommentCorrectionCreate,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: models.User = Depends(require_roles()),  # noqa: B008
):
    superseded = (
        db.query(models.TimelineEvent)
        .filter(models.TimelineEvent.id == payload.supersedes_event_id)
        .first()
    )
    if superseded is None:
        raise HTTPException(status_code=404, detail="Timeline event not found")

    if superseded.event_type not in ("human.comment.created", "human.comment.corrected"):
        raise HTTPException(status_code=400, detail="Only human comments can be corrected")

    # RBAC: visibility is inherited from superseded event; no escalation.
    visibility = superseded.visibility
    if not can_write_timeline(current_user, visibility):
        raise HTTPException(status_code=403, detail="Insufficient role for timeline write")

    event_type = "human.comment.corrected"
    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))
    thread_key = thread_key_for(superseded.subject_type, superseded.subject_id)
    mentions = normalize_mentions(payload.mentions)

    event_payload = {
        "body": payload.body,
        "thread_key": thread_key,
        "mentions": mentions,
        "attachments": payload.attachments,
    }

    audit_id = audit_event(
        "timeline.human.comment.corrected",
        getattr(current_user, "id", None),
        {
            "event_type": event_type,
            "subject_type": superseded.subject_type,
            "subject_id": superseded.subject_id,
            "visibility": visibility,
            "correlation_id": correlation_id,
            "supersedes_event_id": superseded.id,
        },
        db=db,
        request_id=request.headers.get("X-Request-ID"),
        ip=getattr(request.client, "host", None) if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )

    if payload.idempotency_key:
        result = emit_timeline_event(
            db=db,
            event_type=event_type,
            subject_type=superseded.subject_type,
            subject_id=superseded.subject_id,
            correlation_id=correlation_id,
            idempotency_key=payload.idempotency_key,
            visibility=visibility,
            payload=event_payload,
            meta=payload.meta,
            supersedes_event_id=superseded.id,
            actor_user_id=getattr(current_user, "id", None),
            audit_log_id=audit_id,
        )

        for mention in mentions:
            emit_timeline_event(
                db=db,
                event_type="human.mentioned",
                subject_type=superseded.subject_type,
                subject_id=superseded.subject_id,
                correlation_id=correlation_id,
                idempotency_key=f"{payload.idempotency_key}:mention:{mention}",
                visibility=visibility,
                payload={
                    "thread_key": thread_key,
                    "mention": mention,
                    "comment_event_id": result.event.id,
                },
                actor_user_id=getattr(current_user, "id", None),
                audit_log_id=audit_id,
            )

        return result.event

    ev = models.TimelineEvent(
        event_type=event_type,
        subject_type=superseded.subject_type,
        subject_id=superseded.subject_id,
        correlation_id=correlation_id,
        supersedes_event_id=superseded.id,
        visibility=visibility,
        payload=event_payload,
        meta=payload.meta,
        actor_user_id=getattr(current_user, "id", None),
        audit_log_id=audit_id,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)

    for mention in mentions:
        emit_timeline_event(
            db=db,
            event_type="human.mentioned",
            subject_type=superseded.subject_type,
            subject_id=superseded.subject_id,
            correlation_id=correlation_id,
            idempotency_key=f"comment:{ev.id}:mention:{mention}",
            visibility=visibility,
            payload={"thread_key": thread_key, "mention": mention, "comment_event_id": ev.id},
            actor_user_id=getattr(current_user, "id", None),
            audit_log_id=audit_id,
        )

    return ev


@router.post(
    "/human/attachments",
    response_model=TimelineEventRead,
    status_code=status.HTTP_201_CREATED,
)
def add_human_attachment(
    request: Request,
    payload: TimelineHumanAttachmentCreate,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: models.User = Depends(require_roles()),  # noqa: B008
):
    # RBAC: Auditoria never writes; finance visibility only for Financeiro/Admin.
    if not can_write_timeline(current_user, payload.visibility):
        raise HTTPException(status_code=403, detail="Insufficient role for timeline write")

    event_type = "human.attachment.added"
    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))
    thread_key = thread_key_for(payload.subject_type, payload.subject_id)

    event_payload = {
        "thread_key": thread_key,
        "file_id": payload.file_id,
        "file_name": payload.file_name,
        "mime": payload.mime,
        "size": payload.size,
        "checksum": payload.checksum,
        "storage_uri": payload.storage_uri,
    }

    audit_id = audit_event(
        "timeline.human.attachment.added",
        getattr(current_user, "id", None),
        {
            "event_type": event_type,
            "subject_type": payload.subject_type,
            "subject_id": payload.subject_id,
            "visibility": payload.visibility,
            "correlation_id": correlation_id,
            "file_id": payload.file_id,
            "storage_uri": payload.storage_uri,
        },
        db=db,
        request_id=request.headers.get("X-Request-ID"),
        ip=getattr(request.client, "host", None) if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )

    if payload.idempotency_key:
        result = emit_timeline_event(
            db=db,
            event_type=event_type,
            subject_type=payload.subject_type,
            subject_id=payload.subject_id,
            correlation_id=correlation_id,
            idempotency_key=payload.idempotency_key,
            visibility=payload.visibility,
            payload=event_payload,
            meta=payload.meta,
            actor_user_id=getattr(current_user, "id", None),
            audit_log_id=audit_id,
        )
        return result.event

    ev = models.TimelineEvent(
        event_type=event_type,
        subject_type=payload.subject_type,
        subject_id=payload.subject_id,
        correlation_id=correlation_id,
        visibility=payload.visibility,
        payload=event_payload,
        meta=payload.meta,
        actor_user_id=getattr(current_user, "id", None),
        audit_log_id=audit_id,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


@router.post(
    "/human/attachments/upload",
    response_model=TimelineHumanAttachmentUploadRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_human_attachment(
    request: Request,
    file: UploadFile = File(...),  # noqa: B008
    visibility: str = Form("all"),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
    current_user: models.User = Depends(require_roles()),  # noqa: B008
):
    # RBAC: Auditoria never writes; finance visibility only for Financeiro/Admin.
    if visibility not in {"all", "finance"}:
        raise HTTPException(status_code=422, detail="Invalid visibility")
    if not can_write_timeline(current_user, visibility):
        raise HTTPException(status_code=403, detail="Insufficient role for timeline write")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Empty file")

    # Deterministic file_id by content hash (stable for idempotent uploads).
    sha256 = hashlib.sha256(content).hexdigest()
    file_id = f"file_{sha256[:32]}"

    artifact = write_timeline_attachment_bytes(
        file_id=file_id,
        filename=file.filename or "attachment.bin",
        content=content,
        content_type=file.content_type or "application/octet-stream",
    )

    audit_event(
        "timeline.human.attachment.uploaded",
        getattr(current_user, "id", None),
        {
            "file_id": file_id,
            "file_name": artifact.get("file_name"),
            "mime": artifact.get("mime"),
            "size": artifact.get("size"),
            "checksum": artifact.get("checksum"),
            "storage_uri": artifact.get("storage_uri"),
            "visibility": visibility,
        },
        db=db,
        request_id=request.headers.get("X-Request-ID"),
        ip=getattr(request.client, "host", None) if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )

    return artifact


@router.get("/human/attachments/{event_id}/download")
def download_human_attachment(
    event_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: models.User = Depends(require_roles()),  # noqa: B008
):
    ev = db.query(models.TimelineEvent).filter(models.TimelineEvent.id == event_id).first()
    if not ev or ev.event_type != "human.attachment.added":
        raise HTTPException(status_code=404, detail="Attachment event not found")

    # Enforce visibility on download too (do not rely on list endpoint only).
    vis_filter = _visibility_filter_for(current_user)
    if vis_filter is not None:
        allowed = (
            db.query(models.TimelineEvent.id)
            .filter(models.TimelineEvent.id == event_id, vis_filter)
            .first()
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="Insufficient role for attachment download")

    payload = ev.payload or {}
    storage_uri = payload.get("storage_uri")
    if not storage_uri:
        raise HTTPException(status_code=404, detail="Missing storage_uri")

    try:
        path = resolve_local_path_from_storage_uri(storage_uri)
    except ValueError as err:
        raise HTTPException(status_code=404, detail="Unsupported storage_uri") from err

    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path,
        media_type=payload.get("mime") or "application/octet-stream",
        filename=payload.get("file_name") or path.name,
    )
