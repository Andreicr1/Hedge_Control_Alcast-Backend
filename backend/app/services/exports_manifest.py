from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.config import settings


@dataclass(frozen=True)
class ExportManifest:
    export_id: str
    inputs_hash: str
    manifest: dict[str, Any]


def _canonical_json(data: dict[str, Any]) -> str:
    # Deterministic JSON for hashing: stable key order and no whitespace.
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_export_id_and_hash(
    *,
    export_type: str,
    as_of: datetime | None,
    filters: dict[str, Any],
    schema_version: int = 1,
) -> tuple[str, str]:
    request_payload: dict[str, Any] = {
        "schema_version": schema_version,
        "export_type": export_type,
        "as_of": as_of.isoformat() if as_of else None,
        "filters": filters,
    }

    inputs_hash = hashlib.sha256(_canonical_json(request_payload).encode("utf-8")).hexdigest()
    export_id = f"exp_{inputs_hash[:32]}"
    return export_id, inputs_hash


def build_export_manifest(
    *,
    export_type: str,
    as_of: datetime | None,
    filters: dict[str, Any],
    counts: dict[str, int],
    schema_version: int = 1,
) -> ExportManifest:
    export_id, inputs_hash = compute_export_id_and_hash(
        export_type=export_type,
        as_of=as_of,
        filters=filters,
        schema_version=schema_version,
    )

    # Manifest must be deterministic: avoid wall-clock timestamps.
    build_version = settings.build_version
    manifest: dict[str, Any] = {
        "schema_version": schema_version,
        "export_id": export_id,
        "inputs_hash": inputs_hash,
        "export_type": export_type,
        "as_of": as_of.isoformat() if as_of else None,
        # Deterministic: use the snapshot cutoff as the generation timestamp.
        "gerado_em": as_of.isoformat() if as_of else None,
        "filters": filters,
        "counts": counts,
        "versoes": {
            "build_version": build_version,
            "export_schema_version": schema_version,
        },
    }

    return ExportManifest(export_id=export_id, inputs_hash=inputs_hash, manifest=manifest)
