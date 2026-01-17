from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.services.audit import audit_event
from app.services.exports_audit_log import build_audit_log_csv_bytes
from app.services.exports_chain_export import build_chain_export_package_bytes
from app.services.exports_pnl_aggregate import build_pnl_aggregate_csv_bytes
from app.services.exports_state_at_time import build_state_at_time_csv_bytes
from app.services.exports_storage import write_export_artifact_bytes

ArtifactGenerator = Callable[[models.ExportJob], list[dict[str, Any]]]


def _default_generate_artifacts(job: models.ExportJob) -> list[dict[str, Any]]:
    # Minimal placeholder artifact; no storage integration yet.
    # Invariant: artifacts only exist when status == 'done' and are tied to inputs_hash.
    return [
        {
            "kind": "placeholder",
            "format": "json",
            "inputs_hash": job.inputs_hash,
            "checksum_sha256": job.inputs_hash,
        }
    ]


def _generate_artifacts_for_job(db: Session, job: models.ExportJob) -> list[dict[str, Any]]:
    if job.export_type == "audit_log":
        cutoff = job.as_of or job.created_at
        content = build_audit_log_csv_bytes(db, as_of=cutoff)
        return [
            write_export_artifact_bytes(
                export_id=job.export_id,
                kind="audit_log_csv",
                filename="audit_log.csv",
                content=content,
                content_type="text/csv",
                inputs_hash=job.inputs_hash,
            )
        ]

    if job.export_type == "state_at_time":
        cutoff = job.as_of or job.created_at
        content = build_state_at_time_csv_bytes(db, as_of=cutoff, filters=job.filters)
        return [
            write_export_artifact_bytes(
                export_id=job.export_id,
                kind="state_at_time_csv",
                filename="state_at_time.csv",
                content=content,
                content_type="text/csv",
                inputs_hash=job.inputs_hash,
            )
        ]

    if job.export_type == "pnl_aggregate":
        cutoff = job.as_of or job.created_at
        content = build_pnl_aggregate_csv_bytes(db, as_of=cutoff, filters=job.filters)
        return [
            write_export_artifact_bytes(
                export_id=job.export_id,
                kind="pnl_aggregate_csv",
                filename="pnl_aggregate.csv",
                content=content,
                content_type="text/csv",
                inputs_hash=job.inputs_hash,
            )
        ]

    if job.export_type == "chain_export":
        cutoff = job.as_of or job.created_at
        zip_bytes, csv_bytes, pdf_bytes, manifest_bytes = build_chain_export_package_bytes(
            db,
            export_id=job.export_id,
            inputs_hash=job.inputs_hash,
            as_of=cutoff,
            filters=job.filters,
        )

        artifacts: list[dict[str, Any]] = []

        # Keep bundle first for backward-compatible download UX.
        artifacts.append(
            write_export_artifact_bytes(
                export_id=job.export_id,
                kind="chain_export_bundle_zip",
                filename="chain_export.zip",
                content=zip_bytes,
                content_type="application/zip",
                inputs_hash=job.inputs_hash,
            )
        )
        artifacts.append(
            write_export_artifact_bytes(
                export_id=job.export_id,
                kind="chain_export_csv",
                filename="chain_export.csv",
                content=csv_bytes,
                content_type="text/csv",
                inputs_hash=job.inputs_hash,
            )
        )
        artifacts.append(
            write_export_artifact_bytes(
                export_id=job.export_id,
                kind="chain_export_pdf",
                filename="chain_export.pdf",
                content=pdf_bytes,
                content_type="application/pdf",
                inputs_hash=job.inputs_hash,
            )
        )
        artifacts.append(
            write_export_artifact_bytes(
                export_id=job.export_id,
                kind="chain_export_manifest_json",
                filename="manifest.json",
                content=manifest_bytes,
                content_type="application/json",
                inputs_hash=job.inputs_hash,
            )
        )

        return artifacts

    return _default_generate_artifacts(job)


def run_once(
    db: Session,
    *,
    worker_user_id: int | None = None,
    artifacts_generator: ArtifactGenerator | None = None,
) -> str | None:
    """Process at most one queued ExportJob.

    State machine (forward-only): queued -> running -> done|failed.

    Returns export_id when a job is claimed (even if it fails), otherwise None.
    """

    job = (
        db.query(models.ExportJob)
        .filter(models.ExportJob.status == "queued")
        .order_by(models.ExportJob.created_at.asc(), models.ExportJob.id.asc())
        .first()
    )
    if job is None:
        return None

    claimed = (
        db.query(models.ExportJob)
        .filter(models.ExportJob.id == job.id)
        .filter(models.ExportJob.status == "queued")
        .update(
            {"status": "running", "artifacts": None, "updated_at": func.now()},
            synchronize_session=False,
        )
    )
    if claimed != 1:
        db.rollback()
        return None

    db.commit()

    export_id = job.export_id

    audit_event(
        "exports.job.started",
        worker_user_id,
        {
            "export_id": export_id,
            "inputs_hash": job.inputs_hash,
            "export_type": job.export_type,
            "as_of": job.as_of.isoformat() if job.as_of else None,
            "filters": job.filters,
            "from_status": "queued",
            "to_status": "running",
        },
        db=db,
    )

    try:
        if artifacts_generator is None:
            artifacts = _generate_artifacts_for_job(db, job)
        else:
            artifacts = artifacts_generator(job)
        if not artifacts:
            raise ValueError("artifacts_generator returned no artifacts")
        if not isinstance(artifacts, list) or not all(isinstance(a, dict) for a in artifacts):
            raise ValueError("artifacts_generator must return list[dict]")

        completed = (
            db.query(models.ExportJob)
            .filter(models.ExportJob.id == job.id)
            .filter(models.ExportJob.status == "running")
            .update(
                {"status": "done", "artifacts": artifacts, "updated_at": func.now()},
                synchronize_session=False,
            )
        )
        if completed != 1:
            db.rollback()
            return export_id

        db.commit()

        checksums = [a.get("checksum_sha256") for a in artifacts if isinstance(a, dict)]

        audit_event(
            "exports.job.completed",
            worker_user_id,
            {
                "export_id": export_id,
                "inputs_hash": job.inputs_hash,
                "export_type": job.export_type,
                "as_of": job.as_of.isoformat() if job.as_of else None,
                "filters": job.filters,
                "artifacts_count": len(artifacts),
                "artifact_checksums_sha256": checksums,
            },
            db=db,
        )

        return export_id
    except Exception as exc:
        db.rollback()

        failed = (
            db.query(models.ExportJob)
            .filter(models.ExportJob.id == job.id)
            .filter(models.ExportJob.status == "running")
            .update(
                {"status": "failed", "artifacts": None, "updated_at": func.now()},
                synchronize_session=False,
            )
        )
        if failed == 1:
            db.commit()
            audit_event(
                "exports.job.failed",
                worker_user_id,
                {
                    "export_id": export_id,
                    "inputs_hash": job.inputs_hash,
                    "export_type": job.export_type,
                    "as_of": job.as_of.isoformat() if job.as_of else None,
                    "filters": job.filters,
                    "error_code": "unhandled_exception",
                    "error": str(exc)[:500],
                },
                db=db,
            )
        else:
            db.rollback()

        return export_id
