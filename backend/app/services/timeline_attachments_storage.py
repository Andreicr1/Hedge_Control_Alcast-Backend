from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from app.services.exports_storage import storage_root


def write_timeline_attachment_bytes(
    *,
    file_id: str,
    filename: str,
    content: bytes,
    content_type: str,
) -> dict[str, Any]:
    """Persist a timeline attachment to local storage.

    Returns a deterministic artifact-like dict suitable for embedding in timeline payloads.

    Notes:
    - Uses the same storage_root() as exports.
    - Uses an atomic write (tmp -> replace).
    - Returns a file:// storage_uri (served via a dedicated download endpoint).
    """

    root = storage_root()
    target_dir = (root / "timeline_attachments" / file_id).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(filename).name
    if not safe_name:
        safe_name = "attachment.bin"

    target_path = (target_dir / safe_name).resolve()
    if not target_path.is_relative_to(target_dir):
        raise ValueError("Invalid attachment path")

    tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")

    sha256 = hashlib.sha256(content).hexdigest()

    tmp_path.write_bytes(content)
    tmp_path.replace(target_path)

    return {
        "file_id": file_id,
        "file_name": safe_name,
        "mime": content_type or "application/octet-stream",
        "size": len(content),
        "checksum": f"sha256:{sha256}",
        "storage_uri": f"file://{target_path.as_posix()}",
    }


def resolve_local_path_from_storage_uri(storage_uri: str) -> Path:
    if not storage_uri.startswith("file://"):
        raise ValueError("Unsupported storage_uri")

    raw = storage_uri[len("file://") :]
    p = Path(raw)

    # Require it to be under storage_root() to prevent path traversal.
    root = storage_root().resolve()
    resolved = p.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Invalid storage_uri path")

    return resolved
