from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas.analytics import EntityTreeNode, EntityTreeResponse

router = APIRouter(prefix="/analytics", tags=["analytics"])

_db_dep = Depends(get_db)
_finance_or_audit_user_dep = Depends(
    require_roles(models.RoleName.financeiro, models.RoleName.auditoria, models.RoleName.admin)
)


def _deal_label(deal: models.Deal) -> str:
    ref = (getattr(deal, "reference_name", None) or "").strip()
    if ref:
        return f"Deal #{deal.id} — {ref}"
    return f"Deal #{deal.id}"


def _contract_label(contract: models.Contract) -> str:
    number = (getattr(contract, "contract_number", None) or "").strip()
    if number:
        return f"Contrato {number}"
    cid = str(getattr(contract, "contract_id", "") or "")
    short = cid[:8] if cid else "—"
    return f"Contrato {short}"


@router.get("/entity-tree", response_model=EntityTreeResponse)
def get_entity_tree(
    deal_ids: list[int] | None = Query(None),
    limit_deals: int = Query(50, ge=1, le=500),
    db: Session = _db_dep,
    current_user: models.User = _finance_or_audit_user_dep,
):
    deals_q = db.query(models.Deal)
    if deal_ids:
        # Stable, explicit filter when provided.
        deals_q = deals_q.filter(models.Deal.id.in_(list(deal_ids)))

    deals = deals_q.order_by(models.Deal.id.desc()).limit(limit_deals).all()
    deal_id_list = [int(d.id) for d in deals]

    so_by_deal: dict[int, list[models.SalesOrder]] = {did: [] for did in deal_id_list}
    po_by_deal: dict[int, list[models.PurchaseOrder]] = {did: [] for did in deal_id_list}
    contracts_by_deal: dict[int, list[models.Contract]] = {did: [] for did in deal_id_list}

    if deal_id_list:
        sales_orders = (
            db.query(models.SalesOrder)
            .filter(models.SalesOrder.deal_id.in_(deal_id_list))
            .order_by(models.SalesOrder.id.asc())
            .all()
        )
        for so in sales_orders:
            so_by_deal.setdefault(int(so.deal_id), []).append(so)

        purchase_orders = (
            db.query(models.PurchaseOrder)
            .filter(models.PurchaseOrder.deal_id.in_(deal_id_list))
            .order_by(models.PurchaseOrder.id.asc())
            .all()
        )
        for po in purchase_orders:
            po_by_deal.setdefault(int(po.deal_id), []).append(po)

        contracts = (
            db.query(models.Contract)
            .filter(models.Contract.deal_id.in_(deal_id_list))
            .order_by(models.Contract.created_at.asc())
            .all()
        )
        for c in contracts:
            contracts_by_deal.setdefault(int(c.deal_id), []).append(c)

    deal_nodes: list[EntityTreeNode] = []

    for deal in deals:
        did = int(deal.id)
        children: list[EntityTreeNode] = []

        for so in so_by_deal.get(did, []):
            label = f"SO #{so.id} • {so.so_number}"
            children.append(
                EntityTreeNode(
                    id=f"so:{so.id}",
                    kind="so",
                    label=label,
                    deal_id=did,
                    entity_id=str(so.id),
                )
            )

        for po in po_by_deal.get(did, []):
            label = f"PO #{po.id} • {po.po_number}"
            children.append(
                EntityTreeNode(
                    id=f"po:{po.id}",
                    kind="po",
                    label=label,
                    deal_id=did,
                    entity_id=str(po.id),
                )
            )

        for c in contracts_by_deal.get(did, []):
            children.append(
                EntityTreeNode(
                    id=f"contract:{c.contract_id}",
                    kind="contract",
                    label=_contract_label(c),
                    deal_id=did,
                    entity_id=str(c.contract_id),
                )
            )

        deal_nodes.append(
            EntityTreeNode(
                id=f"deal:{did}",
                kind="deal",
                label=_deal_label(deal),
                deal_id=did,
                entity_id=str(did),
                children=children,
            )
        )

    root = EntityTreeNode(
        id="root",
        kind="root",
        label="Consolidado",
        children=deal_nodes,
    )

    return EntityTreeResponse(root=root)
