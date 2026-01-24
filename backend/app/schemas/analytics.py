from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EntityKind = Literal["root", "deal", "so", "po", "contract"]


class EntityTreeNode(BaseModel):
    id: str
    kind: EntityKind
    label: str

    # Convenience metadata for clients.
    deal_id: int | None = None
    entity_id: str | None = None

    children: list["EntityTreeNode"] = Field(default_factory=list)


class EntityTreeResponse(BaseModel):
    root: EntityTreeNode


try:  # Pydantic v2
    EntityTreeNode.model_rebuild()  # type: ignore[attr-defined]
except AttributeError:  # Pydantic v1
    EntityTreeNode.update_forward_refs()
