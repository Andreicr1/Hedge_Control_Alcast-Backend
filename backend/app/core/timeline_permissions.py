from __future__ import annotations

from typing import Optional, Protocol

from app.models.domain import RoleName
from app.schemas.timeline import TimelineVisibility


class _RoleLike(Protocol):
    name: RoleName


class _UserLike(Protocol):
    role: Optional[_RoleLike]


def can_write_timeline(user: _UserLike, visibility: TimelineVisibility) -> bool:
    """Return True if the given user is allowed to create timeline events.

    Phase 4 introduces human collaboration events, but the write matrix is shared:
    - Auditoria: never allowed (global read-only, defense-in-depth)
    - visibility='finance': only Financeiro/Admin
    - visibility='all': any authenticated role except Auditoria
    """

    role = getattr(user, "role", None)
    role_name = getattr(role, "name", None)

    if role_name is None:
        return False

    if role_name == RoleName.auditoria:
        return False

    if visibility == "finance":
        return role_name in (RoleName.financeiro, RoleName.admin)

    return True
