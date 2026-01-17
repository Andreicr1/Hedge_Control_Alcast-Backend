from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from app.config import settings


def storage_root() -> Path:
    """Return the absolute storage root for this backend instance."""

    root = Path(settings.storage_dir)
    if root.is_absolute():
        return root

    # backend/app/services/... -> backend/
    backend_root = Path(__file__).resolve().parents[2]
    return (backend_root / root).resolve()


def write_export_artifact_bytes(
    *,
    export_id: str,
    kind: str,
    filename: str,
    content: bytes,
    content_type: str,
    inputs_hash: str | None = None,
) -> dict[str, Any]:
    root = storage_root()
    target_dir = (root / "exports" / export_id).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = (target_dir / filename).resolve()
    if not target_path.is_relative_to(target_dir):
        raise ValueError("Invalid artifact path")

    tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")

    sha256 = hashlib.sha256(content).hexdigest()

    tmp_path.write_bytes(content)
    tmp_path.replace(target_path)

    payload: dict[str, Any] = {
        "kind": kind,
        "filename": filename,
        "content_type": content_type,
        "size_bytes": len(content),
        "checksum_sha256": sha256,
        "storage_uri": f"file://{target_path.as_posix()}",
    }

    if inputs_hash is not None:
        payload["inputs_hash"] = inputs_hash

    return payload
