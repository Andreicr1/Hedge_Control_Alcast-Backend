from __future__ import annotations


def thread_key_for(subject_type: str, subject_id: int) -> str:
    """Return a deterministic thread key for timeline human collaboration.

    Convention (Fase 4): `${subject_type}:${subject_id}`

    This is intentionally simple and stable; it must not depend on mutable fields.
    """

    if not subject_type or not isinstance(subject_type, str):
        raise ValueError("subject_type must be a non-empty string")
    if not isinstance(subject_id, int) or subject_id <= 0:
        raise ValueError("subject_id must be a positive integer")

    return f"{subject_type}:{subject_id}"
