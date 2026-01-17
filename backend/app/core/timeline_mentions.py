from __future__ import annotations


def normalize_mentions(raw: list[str]) -> list[str]:
    """Normalize mentions from API payload.

    Scope (T4.1.3): mentions are declared explicitly in the request payload.

    Rules:
    - trim whitespace
    - lowercase
    - remove leading '@'
    - drop empty
    - de-duplicate preserving order

    Values are treated as opaque identifiers (e.g., email or user_id-as-string).
    """

    normalized: list[str] = []
    seen: set[str] = set()

    for item in raw or []:
        if item is None:
            continue
        value = str(item).strip()
        if value.startswith("@"):  # allow clients to send '@email'
            value = value[1:]
        value = value.strip().lower()
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)

    return normalized
