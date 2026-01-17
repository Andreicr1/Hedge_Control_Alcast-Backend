from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas.exports import ExportJobCreate, ExportJobRead
from app.services.audit import audit_event
from app.services.exports_manifest import build_export_manifest, compute_export_id_and_hash
from app.services.exports_storage import storage_root

router = APIRouter(prefix="/exports", tags=["exports"])

_manifest_roles_dep = require_roles(
    models.RoleName.financeiro,
    models.RoleName.admin,
    models.RoleName.auditoria,
)

_exports_read_roles_dep = _manifest_roles_dep
_exports_write_roles_dep = require_roles(models.RoleName.financeiro, models.RoleName.admin)


@router.get("/manifest")
def export_manifest(
    request: Request,
    export_type: str = Query("state", min_length=1, max_length=64),  # noqa: B008
    as_of: Optional[datetime] = Query(None),  # noqa: B008
    subject_type: Optional[str] = Query(None, min_length=1, max_length=32),  # noqa: B008
    subject_id: Optional[int] = Query(None, ge=1),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
    current_user: models.User = Depends(_manifest_roles_dep),  # noqa: B008
):
    # Deterministic, read-only manifest builder. No file generation and no domain writes.
    filters: dict[str, Any] = {
        "subject_type": subject_type,
        "subject_id": subject_id,
    }

    counts = {
        "audit_logs": int(db.query(func.count(models.AuditLog.id)).scalar() or 0),
        "timeline_events": int(db.query(func.count(models.TimelineEvent.id)).scalar() or 0),
        "rfqs": int(db.query(func.count(models.Rfq.id)).scalar() or 0),
        "contracts": int(db.query(func.count(models.Contract.contract_id)).scalar() or 0),
    }

    built = build_export_manifest(
        export_type=export_type,
        as_of=as_of,
        filters=filters,
        counts=counts,
    )

    audit_event(
        "exports.manifest.requested",
        getattr(current_user, "id", None),
        {
            "export_id": built.export_id,
            "export_type": export_type,
            "as_of": as_of.isoformat() if as_of else None,
            "filters": filters,
            "inputs_hash": built.inputs_hash,
        },
        db=db,
        request_id=request.headers.get("X-Request-ID"),
        ip=getattr(request.client, "host", None) if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )

    return built.manifest


@router.post("", response_model=ExportJobRead, status_code=201)
def create_export_job(
    payload: ExportJobCreate,
    request: Request,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: models.User = Depends(_exports_write_roles_dep),  # noqa: B008
):
    filters: dict[str, Any] = {
        "subject_type": payload.subject_type,
        "subject_id": payload.subject_id,
    }

    export_id, inputs_hash = compute_export_id_and_hash(
        export_type=payload.export_type,
        as_of=payload.as_of,
        filters=filters,
    )

    existing = db.query(models.ExportJob).filter(models.ExportJob.export_id == export_id).first()
    if existing is not None:
        audit_event(
            "exports.job.requested",
            getattr(current_user, "id", None),
            {
                "export_id": existing.export_id,
                "inputs_hash": existing.inputs_hash,
                "export_type": existing.export_type,
                "as_of": existing.as_of.isoformat() if existing.as_of else None,
                "filters": existing.filters,
                "status": existing.status,
                "idempotent": True,
            },
            db=db,
            request_id=request.headers.get("X-Request-ID"),
            ip=getattr(request.client, "host", None) if request.client else None,
            user_agent=request.headers.get("User-Agent"),
        )
        return existing

    job = models.ExportJob(
        export_id=export_id,
        inputs_hash=inputs_hash,
        export_type=payload.export_type,
        as_of=payload.as_of,
        filters=filters,
        status="queued",
        requested_by_user_id=getattr(current_user, "id", None),
    )
    db.add(job)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        job = db.query(models.ExportJob).filter(models.ExportJob.export_id == export_id).first()
        if job is None:
            raise
    else:
        db.refresh(job)

    audit_event(
        "exports.job.requested",
        getattr(current_user, "id", None),
        {
            "export_id": job.export_id,
            "inputs_hash": job.inputs_hash,
            "export_type": job.export_type,
            "as_of": job.as_of.isoformat() if job.as_of else None,
            "filters": job.filters,
            "status": job.status,
            "idempotent": False,
        },
        db=db,
        request_id=request.headers.get("X-Request-ID"),
        ip=getattr(request.client, "host", None) if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )

    return job


@router.get("/{export_id}", response_model=ExportJobRead)
def get_export_job(
    export_id: str,
    request: Request,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: models.User = Depends(_exports_read_roles_dep),  # noqa: B008
):
    job = db.query(models.ExportJob).filter(models.ExportJob.export_id == export_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Export not found")

    audit_event(
        "exports.job.status_viewed",
        getattr(current_user, "id", None),
        {
            "export_id": job.export_id,
            "inputs_hash": job.inputs_hash,
            "export_type": job.export_type,
            "as_of": job.as_of.isoformat() if job.as_of else None,
            "filters": job.filters,
            "status": job.status,
        },
        db=db,
        request_id=request.headers.get("X-Request-ID"),
        ip=getattr(request.client, "host", None) if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )

    if job.status != "done":
        return ExportJobRead.from_orm(job).dict(exclude={"artifacts"})

    return job


@router.get("/{export_id}/download")
def download_export(
    export_id: str,
    request: Request,
    kind: Optional[str] = Query(None, min_length=1, max_length=64),  # noqa: B008
    filename: Optional[str] = Query(None, min_length=1, max_length=255),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
    current_user: models.User = Depends(_exports_read_roles_dep),  # noqa: B008
):
    job = db.query(models.ExportJob).filter(models.ExportJob.export_id == export_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Export not found")

    if job.status != "done":
        raise HTTPException(status_code=409, detail="Export not ready")

    artifacts = job.artifacts or []
    if not artifacts:
        raise HTTPException(status_code=404, detail="Export has no artifacts")

    primary: Optional[dict[str, Any]] = None
    if isinstance(artifacts, list):
        for a in artifacts:
            if not isinstance(a, dict):
                continue
            if kind is not None and a.get("kind") == kind:
                primary = a
                break
            if kind is None and filename is not None and a.get("filename") == filename:
                primary = a
                break

        if primary is None:
            primary = artifacts[0] if artifacts else None

    if kind is not None and (primary is None or primary.get("kind") != kind):
        raise HTTPException(status_code=404, detail="Export artifact not found")
    if filename is not None and (primary is None or primary.get("filename") != filename):
        raise HTTPException(status_code=404, detail="Export artifact not found")

    storage_uri = primary.get("storage_uri") if isinstance(primary, dict) else None
    if not storage_uri:
        raise HTTPException(status_code=404, detail="Export has no downloadable artifact")

    if storage_uri.startswith("http://") or storage_uri.startswith("https://"):
        audit_event(
            "exports.job.download_requested",
            getattr(current_user, "id", None),
            {
                "export_id": job.export_id,
                "inputs_hash": job.inputs_hash,
                "export_type": job.export_type,
                "as_of": job.as_of.isoformat() if job.as_of else None,
                "filters": job.filters,
                "storage_uri": storage_uri,
            },
            db=db,
            request_id=request.headers.get("X-Request-ID"),
            ip=getattr(request.client, "host", None) if request.client else None,
            user_agent=request.headers.get("User-Agent"),
        )

        return RedirectResponse(url=storage_uri)

    if storage_uri.startswith("file://"):
        raw_path = storage_uri.removeprefix("file://")
        artifact_path = Path(raw_path).resolve()
        root = storage_root().resolve()

        if not artifact_path.is_relative_to(root):
            raise HTTPException(status_code=404, detail="Export artifact not found")
        if not artifact_path.exists() or not artifact_path.is_file():
            raise HTTPException(status_code=404, detail="Export artifact not found")

        audit_event(
            "exports.job.download_requested",
            getattr(current_user, "id", None),
            {
                "export_id": job.export_id,
                "inputs_hash": job.inputs_hash,
                "export_type": job.export_type,
                "as_of": job.as_of.isoformat() if job.as_of else None,
                "filters": job.filters,
                "storage_uri": storage_uri,
            },
            db=db,
            request_id=request.headers.get("X-Request-ID"),
            ip=getattr(request.client, "host", None) if request.client else None,
            user_agent=request.headers.get("User-Agent"),
        )

        media_type = primary.get("content_type") if isinstance(primary, dict) else None
        filename = primary.get("filename") if isinstance(primary, dict) else None

        return FileResponse(
            path=str(artifact_path),
            media_type=str(media_type) if media_type else "application/octet-stream",
            filename=str(filename) if filename else artifact_path.name,
        )

    raise HTTPException(status_code=501, detail="Artifact storage_uri is not downloadable")
