from __future__ import annotations

import argparse
import os
import random
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

# Ensure "app" is importable when running as a script (python scripts/seed_realistic_data.py)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import models  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.services.audit import audit_event  # noqa: E402
from app.services.deal_engine import link_hedge_to_deal  # noqa: E402
from app.services.document_numbering import next_monthly_number  # noqa: E402
from app.services.exposure_engine import (  # noqa: E402
    close_open_exposures_for_source,
    reconcile_purchase_order_exposures,
    reconcile_sales_order_exposures,
)
from app.services.exposure_timeline import (  # noqa: E402
    emit_exposure_closed,
    emit_exposure_created,
    emit_exposure_recalculated,
)
from app.services.timeline_emitters import emit_timeline_event  # noqa: E402
from app.services.treasury_decisions_service import (  # noqa: E402
    create_kyc_override,
    create_treasury_decision,
)
from app.services.workflow_approvals import require_approval_or_raise  # noqa: E402


@dataclass(frozen=True)
class CompanySpec:
    slug: str
    code: str
    label: str


COMPANIES: dict[str, CompanySpec] = {
    "alcast_trading": CompanySpec(slug="alcast_trading", code="AT", label="Alcast Trading"),
    "alcast_brasil": CompanySpec(slug="alcast_brasil", code="AB", label="Alcast Brasil"),
}


def _env_guard(*, allow_production: bool) -> None:
    environment = str(os.getenv("ENVIRONMENT", "dev") or "dev").strip().lower()
    if environment in {"prod", "production"} and not allow_production:
        raise SystemExit(
            "Refusing to seed when ENVIRONMENT=production. "
            "Re-run with --allow-production if you really intend to do this."
        )


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _weighted_choice(rng: random.Random, items: list[tuple[models.PriceType, float]]) -> models.PriceType:
    total = sum(w for _, w in items)
    x = rng.random() * total
    upto = 0.0
    for it, w in items:
        upto += w
        if x <= upto:
            return it
    return items[-1][0]


def _pick_horizon_bucket(rng: random.Random) -> int:
    """Return days offset for delivery date.

    Buckets:
    - short: 30-90
    - mid: 180-365
    - long: 540-730
    """

    roll = rng.random()
    if roll < 0.45:
        return rng.randint(30, 90)
    if roll < 0.80:
        return rng.randint(180, 365)
    return rng.randint(540, 730)


def _ensure_roles_and_seed_users(db: Session, *, password: str) -> dict[str, int]:
    """Ensure baseline dev users exist and return ids by role slug."""

    from app.services.auth import hash_password

    def ensure_role(role_name: models.RoleName) -> models.Role:
        role = db.query(models.Role).filter(models.Role.name == role_name).first()
        if role:
            return role
        role = models.Role(name=role_name, description=role_name.value)
        db.add(role)
        db.flush()
        return role

    def ensure_user(*, email: str, name: str, role: models.Role) -> models.User:
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            user = models.User(
                email=email,
                name=name,
                hashed_password=hash_password(password),
                role_id=role.id,
                active=True,
            )
            db.add(user)
        else:
            user.name = name
            user.role_id = role.id
            user.active = True
            user.hashed_password = hash_password(password)
            db.add(user)
        db.flush()
        return user

    domain = str(os.getenv("SEED_EMAIL_DOMAIN", "alcast.local") or "alcast.local").strip().lstrip("@")

    roles = {
        "admin": ensure_role(models.RoleName.admin),
        "finance": ensure_role(models.RoleName.financeiro),
        "sales": ensure_role(models.RoleName.vendas),
        "purchasing": ensure_role(models.RoleName.compras),
        "audit": ensure_role(models.RoleName.auditoria),
    }

    users = {
        "admin": ensure_user(
            email=f"admin@{domain}",
            name="Administrador",
            role=roles["admin"],
        ),
        "finance": ensure_user(
            email=f"financeiro@{domain}",
            name="Financeiro",
            role=roles["finance"],
        ),
        "sales": ensure_user(
            email=f"vendas@{domain}",
            name="Vendas",
            role=roles["sales"],
        ),
        "purchasing": ensure_user(
            email=f"compras@{domain}",
            name="Compras",
            role=roles["purchasing"],
        ),
        "audit": ensure_user(
            email=f"auditoria@{domain}",
            name="Auditoria",
            role=roles["audit"],
        ),
    }

    db.commit()
    return {k: int(u.id) for k, u in users.items()}


def _ensure_lme_prices(db: Session, *, days: int) -> None:
    """Ensure we have a stable daily LME series for the last `days` days.

    This is intentionally deterministic and de-duplicated by (symbol, price_type, date).
    """

    from app.models.lme_price import LMEPrice

    symbol_specs: dict[str, dict[str, str]] = {
        "P3Y00": {"name": "Aluminium Hg Cash", "market": "LME"},
        "P4Y00": {"name": "Aluminium Hg 3M", "market": "LME"},
        "Q7Y00": {"name": "Aluminium Hg Official", "market": "LME"},
    }

    def gen_price(base: float, day_index: int) -> float:
        # Keep this deterministic but not trivially linear.
        import math

        wave = 35.0 * math.sin(day_index / 9.0)
        drift = 0.6 * day_index
        return round(base + wave + drift, 2)

    now = datetime.now(timezone.utc)
    start_day = (now - timedelta(days=int(days))).date()

    # Build existing keys set for the range.
    rows = (
        db.query(LMEPrice.symbol, LMEPrice.price_type, LMEPrice.ts_price)
        .filter(LMEPrice.symbol.in_(sorted(symbol_specs.keys())))
        .filter(LMEPrice.ts_price >= datetime.combine(start_day, datetime.min.time(), tzinfo=timezone.utc))
        .all()
    )
    existing: set[tuple[str, str, date]] = set()
    for sym, pt, ts in rows:
        if ts is None:
            continue
        existing.add((str(sym), str(pt), ts.date()))

    to_add: list[LMEPrice] = []
    for i in range(int(days)):
        day = start_day + timedelta(days=i)
        ts_close = datetime(day.year, day.month, day.day, 16, 0, 0, tzinfo=timezone.utc)

        for sym, base in (("P3Y00", 2250.0), ("P4Y00", 2310.0)):
            if (sym, "close", day) not in existing:
                to_add.append(
                    LMEPrice(
                        symbol=sym,
                        name=symbol_specs[sym]["name"],
                        market=symbol_specs[sym]["market"],
                        price=gen_price(base, i),
                        price_type="close",
                        ts_price=ts_close,
                        source="seed_realistic_data",
                    )
                )

        # official series (used by cashflow default)
        sym = "Q7Y00"
        if (sym, "official", day) not in existing:
            to_add.append(
                LMEPrice(
                    symbol=sym,
                    name=symbol_specs[sym]["name"],
                    market=symbol_specs[sym]["market"],
                    price=gen_price(2235.0, i),
                    price_type="official",
                    ts_price=ts_close,
                    source="seed_realistic_data",
                )
            )

    # latest live snapshots
    for sym, base in (("P3Y00", 2265.0), ("P4Y00", 2325.0)):
        to_add.append(
            LMEPrice(
                symbol=sym,
                name=symbol_specs[sym]["name"],
                market=symbol_specs[sym]["market"],
                price=gen_price(base, int(days)),
                price_type="live",
                ts_price=now,
                source="seed_realistic_data",
            )
        )

    if to_add:
        db.add_all(to_add)
        db.commit()


def _seed_marker_key(company: CompanySpec) -> str:
    return f"seed_realistic:{company.slug}:v1"


def _already_seeded(db: Session, company: CompanySpec) -> bool:
    existing = (
        db.query(models.AuditLog)
        .filter(models.AuditLog.idempotency_key == _seed_marker_key(company))
        .first()
    )
    return existing is not None


def _reset_company(db: Session, company: CompanySpec) -> None:
    """Delete all data created by this seeder for a company.

    Since the DB schema doesn't have a first-class company dimension yet, we isolate
    by deterministic prefixes:
    - deals.reference_name starts with "{CODE} •"
    - customer/supplier.code starts with "{CODE}-"
    - counterparty.name starts with "{LABEL} —"
    - so/po/rfq numbers start with "{CODE}-"
    - contract_number starts with "{CODE}-CT-"

    This makes the reset safe and predictable.
    """

    deal_prefix = f"{company.code} •"
    name_prefix = f"{company.label} —"
    code_prefix = f"{company.code}-"

    deal_ids = [
        int(d.id)
        for d in db.query(models.Deal.id)
        .filter(models.Deal.reference_name.ilike(f"{deal_prefix}%"))
        .all()
    ]

    so_ids = [
        int(x.id)
        for x in db.query(models.SalesOrder.id)
        .filter(models.SalesOrder.so_number.ilike(f"{code_prefix}%"))
        .all()
    ]
    po_ids = [
        int(x.id)
        for x in db.query(models.PurchaseOrder.id)
        .filter(models.PurchaseOrder.po_number.ilike(f"{code_prefix}%"))
        .all()
    ]

    rfq_ids = [
        int(x.id)
        for x in db.query(models.Rfq.id)
        .filter(models.Rfq.rfq_number.ilike(f"{code_prefix}RFQ-%"))
        .all()
    ]

    contract_ids = [
        str(x.contract_id)
        for x in db.query(models.Contract.contract_id)
        .filter(models.Contract.contract_number.ilike(f"{company.code}-CT-%"))
        .all()
    ]

    exposure_ids: list[int] = []
    if so_ids:
        exposure_ids.extend(
            [
                int(e.id)
                for e in db.query(models.Exposure.id)
                .filter(models.Exposure.source_type == models.MarketObjectType.so)
                .filter(models.Exposure.source_id.in_(so_ids))
                .all()
            ]
        )
    if po_ids:
        exposure_ids.extend(
            [
                int(e.id)
                for e in db.query(models.Exposure.id)
                .filter(models.Exposure.source_type == models.MarketObjectType.po)
                .filter(models.Exposure.source_id.in_(po_ids))
                .all()
            ]
        )

    hedge_ids = [
        int(h.id)
        for h in db.query(models.Hedge.id)
        .filter(models.Hedge.reference_code.ilike(f"{code_prefix}HEDGE-%"))
        .all()
    ]

    # Workflow requests are linked by subject_id. We only create a subset for rfq/hedge.
    wf_ids = [
        int(wf.id)
        for wf in db.query(models.WorkflowRequest.id)
        .filter(
            (models.WorkflowRequest.subject_type == "rfq")
            & (models.WorkflowRequest.subject_id.in_([str(i) for i in rfq_ids]))
        )
        .all()
    ]
    if hedge_ids:
        wf_ids.extend(
            [
                int(wf.id)
                for wf in db.query(models.WorkflowRequest.id)
                .filter(models.WorkflowRequest.subject_type == "hedge")
                .filter(models.WorkflowRequest.subject_id.in_([str(i) for i in hedge_ids]))
                .all()
            ]
        )

    # Delete children first.
    if wf_ids:
        db.query(models.WorkflowDecision).filter(
            models.WorkflowDecision.workflow_request_id.in_(wf_ids)
        ).delete(synchronize_session=False)
        db.query(models.WorkflowRequest).filter(models.WorkflowRequest.id.in_(wf_ids)).delete(
            synchronize_session=False
        )

    if exposure_ids:
        db.query(models.TreasuryKycOverride).filter(
            models.TreasuryKycOverride.decision_id.in_(
                db.query(models.TreasuryDecision.id).filter(
                    models.TreasuryDecision.exposure_id.in_(exposure_ids)
                )
            )
        ).delete(synchronize_session=False)
        db.query(models.TreasuryDecision).filter(models.TreasuryDecision.exposure_id.in_(exposure_ids)).delete(
            synchronize_session=False
        )

        db.query(models.HedgeTask).filter(models.HedgeTask.exposure_id.in_(exposure_ids)).delete(
            synchronize_session=False
        )
        db.query(models.HedgeExposure).filter(models.HedgeExposure.exposure_id.in_(exposure_ids)).delete(
            synchronize_session=False
        )
        db.query(models.ContractExposure).filter(models.ContractExposure.exposure_id.in_(exposure_ids)).delete(
            synchronize_session=False
        )
        db.query(models.Exposure).filter(models.Exposure.id.in_(exposure_ids)).delete(
            synchronize_session=False
        )

    if hedge_ids:
        db.query(models.HedgeExposure).filter(models.HedgeExposure.hedge_id.in_(hedge_ids)).delete(
            synchronize_session=False
        )
        db.query(models.Hedge).filter(models.Hedge.id.in_(hedge_ids)).delete(synchronize_session=False)

    if rfq_ids:
        db.query(models.RfqSendAttempt).filter(models.RfqSendAttempt.rfq_id.in_(rfq_ids)).delete(
            synchronize_session=False
        )
        db.query(models.WhatsAppMessage).filter(models.WhatsAppMessage.rfq_id.in_(rfq_ids)).delete(
            synchronize_session=False
        )
        db.query(models.RfqInvitation).filter(models.RfqInvitation.rfq_id.in_(rfq_ids)).delete(
            synchronize_session=False
        )
        db.query(models.RfqQuote).filter(models.RfqQuote.rfq_id.in_(rfq_ids)).delete(
            synchronize_session=False
        )
        db.query(models.Rfq).filter(models.Rfq.id.in_(rfq_ids)).delete(synchronize_session=False)

    if contract_ids:
        db.query(models.ContractExposure).filter(models.ContractExposure.contract_id.in_(contract_ids)).delete(
            synchronize_session=False
        )
        db.query(models.Contract).filter(models.Contract.contract_id.in_(contract_ids)).delete(
            synchronize_session=False
        )

    if so_ids:
        db.query(models.SalesOrder).filter(models.SalesOrder.id.in_(so_ids)).delete(synchronize_session=False)
    if po_ids:
        db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id.in_(po_ids)).delete(synchronize_session=False)

    if deal_ids:
        db.query(models.DealLink).filter(models.DealLink.deal_id.in_(deal_ids)).delete(
            synchronize_session=False
        )
        db.query(models.Deal).filter(models.Deal.id.in_(deal_ids)).delete(synchronize_session=False)

    db.query(models.Customer).filter(models.Customer.code.ilike(f"{code_prefix}CUST-%")).delete(
        synchronize_session=False
    )
    db.query(models.Supplier).filter(models.Supplier.code.ilike(f"{code_prefix}SUP-%")).delete(
        synchronize_session=False
    )
    db.query(models.Counterparty).filter(models.Counterparty.name.ilike(f"{name_prefix}%")).delete(
        synchronize_session=False
    )

    # Remove seed marker.
    db.query(models.AuditLog).filter(models.AuditLog.idempotency_key == _seed_marker_key(company)).delete(
        synchronize_session=False
    )

    # Remove seed-created timeline events that use deterministic idempotency keys.
    # Without this, re-seeding after reset can hit idempotency conflicts and/or
    # keep timeline events pointing at deleted RFQ/Contract ids.
    db.query(models.TimelineEvent).filter(
        models.TimelineEvent.idempotency_key.ilike(f"seed:rfq:{company.code}-RFQ-%:awarded")
    ).delete(synchronize_session=False)
    db.query(models.TimelineEvent).filter(
        models.TimelineEvent.idempotency_key.ilike(f"seed:contract:{company.code}-CT-%:created")
    ).delete(synchronize_session=False)

    db.commit()


def _ensure_customer(db: Session, *, company: CompanySpec, code: str, name: str, rng: random.Random) -> models.Customer:
    existing = db.query(models.Customer).filter(models.Customer.code == code).first()
    if existing is not None:
        return existing

    kyc_status = "approved" if rng.random() > 0.12 else "pending"
    risk_rating = rng.choice(["low", "medium", "medium", "high"]) if kyc_status == "approved" else rng.choice(["medium", "high"]) 
    sanctions_flag = bool(rng.random() < 0.03)

    c = models.Customer(
        name=name,
        trade_name=name,
        code=code,
        legal_name=name + " Ltd.",
        entity_type="company",
        tax_id=None,
        tax_id_type=None,
        tax_id_country=None,
        city=rng.choice(["São Paulo", "Santos", "Hamburg", "Rotterdam", "New Orleans", "Singapore"]),
        state=rng.choice(["SP", "", "", ""]),
        country=rng.choice(["Brazil", "Netherlands", "Germany", "United States", "Singapore", "Mexico"]),
        contact_email=f"trading@{company.slug}.example",
        contact_phone=None,
        base_currency="USD",
        payment_terms=rng.choice(["Net 30", "Net 45", "Net 60", "LC at sight", "CAD"]),
        risk_rating=risk_rating,
        sanctions_flag=sanctions_flag,
        kyc_status=kyc_status,
        kyc_notes=None if kyc_status == "approved" else "Documentação em análise; necessário refresh de KYC.",
        active=bool(rng.random() > 0.05),
    )
    db.add(c)
    db.flush()
    return c


def _ensure_supplier(db: Session, *, company: CompanySpec, code: str, name: str, rng: random.Random) -> models.Supplier:
    existing = db.query(models.Supplier).filter(models.Supplier.code == code).first()
    if existing is not None:
        return existing

    kyc_status = "approved" if rng.random() > 0.10 else "pending"
    risk_rating = rng.choice(["low", "medium", "medium", "high"]) if kyc_status == "approved" else rng.choice(["medium", "high"]) 
    sanctions_flag = bool(rng.random() < 0.02)

    s = models.Supplier(
        name=name,
        trade_name=name,
        code=code,
        legal_name=name + " S.A.",
        entity_type="company",
        tax_id=None,
        tax_id_type=None,
        tax_id_country=None,
        city=rng.choice(["Bahrain", "Al Jubail", "Quebec", "Reykjavík", "Sohar", "Abu Dhabi"]),
        state=None,
        country=rng.choice(["Bahrain", "Canada", "Iceland", "Oman", "United Arab Emirates", "Australia"]),
        contact_email=f"sales@{company.slug}.example",
        contact_phone=None,
        base_currency="USD",
        payment_terms=rng.choice(["Net 30", "Net 45", "Advance", "LC at sight"]),
        risk_rating=risk_rating,
        sanctions_flag=sanctions_flag,
        kyc_status=kyc_status,
        kyc_notes=None if kyc_status == "approved" else "KYC pendente; solicitar documentos adicionais.",
        active=bool(rng.random() > 0.06),
    )
    db.add(s)
    db.flush()
    return s


def _ensure_counterparty(
    db: Session,
    *,
    company: CompanySpec,
    name: str,
    cp_type: models.CounterpartyType,
    rng: random.Random,
) -> models.Counterparty:
    existing = db.query(models.Counterparty).filter(models.Counterparty.name == name).first()
    if existing is not None:
        return existing

    kyc_status = "approved" if rng.random() > 0.08 else "pending"
    cp = models.Counterparty(
        name=name,
        type=cp_type,
        trade_name=name,
        legal_name=name,
        entity_type="financial",
        contact_name=rng.choice(["Ops Desk", "Metals Desk", "Execution", "Back Office"]),
        contact_email=f"desk@{company.slug}.example",
        contact_phone=None,
        city=rng.choice(["London", "New York", "Singapore", "Zurich", "Geneva"]),
        country=rng.choice(["United Kingdom", "United States", "Singapore", "Switzerland"]),
        base_currency="USD",
        payment_terms="",
        risk_rating=rng.choice(["low", "medium", "medium", "high"]),
        sanctions_flag=False,
        kyc_status=kyc_status,
        kyc_notes=None if kyc_status == "approved" else "KYC em atualização; revisão anual pendente.",
        internal_notes=f"Seeded for {company.label}",
        active=True,
    )
    db.add(cp)
    db.flush()
    return cp


def _ensure_deal(db: Session, *, company: CompanySpec, reference_name: str, created_by: int | None) -> models.Deal:
    existing = db.query(models.Deal).filter(models.Deal.reference_name == reference_name).first()
    if existing is not None:
        return existing

    d = models.Deal(
        commodity="Aluminium P1020A",
        reference_name=reference_name,
        currency="USD",
        status=models.DealStatus.open,
        lifecycle_status=models.DealLifecycleStatus.open,
        created_by=created_by,
    )
    db.add(d)
    db.flush()
    return d


def _create_sales_order(
    db: Session,
    *,
    company: CompanySpec,
    deal: models.Deal,
    so_number: str,
    customer_id: int,
    pricing_type: models.PriceType,
    qty_mt: float,
    delivery_date: date,
    rng: random.Random,
) -> models.SalesOrder:
    existing = db.query(models.SalesOrder).filter(models.SalesOrder.so_number == so_number).first()
    if existing is not None:
        return existing

    is_fix = pricing_type == models.PriceType.FIX
    unit_price = None
    if is_fix:
        unit_price = float(rng.uniform(2360.0, 2890.0))

    reference_price = rng.choice(["Q7Y00", "P3Y00", "P4Y00"]) if not is_fix else "Q7Y00"

    so = models.SalesOrder(
        so_number=so_number,
        deal_id=int(deal.id),
        customer_id=int(customer_id),
        product=rng.choice(["Aluminium P1020A", "Aluminium Billet", "Aluminium T-bar", "Aluminium Sows"]),
        total_quantity_mt=float(qty_mt),
        unit="MT",
        unit_price=unit_price,
        pricing_type=pricing_type,
        pricing_period=None,
        lme_premium=float(rng.uniform(0.0, 120.0)),
        premium=float(rng.uniform(0.0, 80.0)),
        reference_price=reference_price,
        fixing_deadline=(delivery_date - timedelta(days=rng.randint(7, 21))) if not is_fix else None,
        expected_delivery_date=delivery_date,
        location=rng.choice(["Rotterdam", "Hamburg", "Santos", "New Orleans", "Busan"]),
        status=models.OrderStatus.active if rng.random() > 0.10 else models.OrderStatus.draft,
        notes=rng.choice(
            [
                "Incoterm CFR; warehouse release subject to BL confirmation.",
                "Incoterm FOB; premiums per alloy specs; quality cert required.",
                "Payment terms per master agreement; tolerance +/- 5%.",
            ]
        ),
    )
    db.add(so)
    db.flush()

    # Keep DealLink consistent.
    db.query(models.DealLink).filter(
        models.DealLink.entity_type == models.DealEntityType.so,
        models.DealLink.entity_id == so.id,
    ).delete(synchronize_session=False)
    db.add(
        models.DealLink(
            deal_id=int(deal.id),
            entity_type=models.DealEntityType.so,
            entity_id=int(so.id),
            direction=models.DealDirection.sell,
            quantity_mt=float(so.total_quantity_mt),
            allocation_type=models.DealAllocationType.manual,
        )
    )

    return so


def _create_purchase_order(
    db: Session,
    *,
    company: CompanySpec,
    deal: models.Deal,
    po_number: str,
    supplier_id: int,
    pricing_type: models.PriceType,
    qty_mt: float,
    delivery_date: date,
    rng: random.Random,
) -> models.PurchaseOrder:
    existing = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.po_number == po_number).first()
    if existing is not None:
        return existing

    is_fix = pricing_type == models.PriceType.FIX
    unit_price = None
    if is_fix:
        unit_price = float(rng.uniform(2320.0, 2820.0))

    reference_price = rng.choice(["Q7Y00", "P3Y00", "P4Y00"]) if not is_fix else "Q7Y00"

    po = models.PurchaseOrder(
        po_number=po_number,
        deal_id=int(deal.id),
        supplier_id=int(supplier_id),
        product=rng.choice(["Aluminium P1020A", "Aluminium Billet", "Aluminium Sows"]),
        total_quantity_mt=float(qty_mt),
        unit="MT",
        unit_price=unit_price,
        pricing_type=pricing_type,
        pricing_period=None,
        lme_premium=float(rng.uniform(0.0, 140.0)),
        premium=float(rng.uniform(0.0, 90.0)),
        reference_price=reference_price,
        fixing_deadline=(delivery_date - timedelta(days=rng.randint(10, 25))) if not is_fix else None,
        expected_delivery_date=delivery_date,
        location=rng.choice(["Port Klang", "Sohar", "Halifax", "Ras Al Khair", "Bahrain"]),
        status=models.OrderStatus.active if rng.random() > 0.10 else models.OrderStatus.draft,
        notes=rng.choice(
            [
                "Shipment window per laycan; demurrage per charter party.",
                "Quality: AA 99.7% min; packing per buyer specs.",
                "Payment LC at sight; documents: invoice/packing list/COA.",
            ]
        ),
    )
    db.add(po)
    db.flush()

    db.query(models.DealLink).filter(
        models.DealLink.entity_type == models.DealEntityType.po,
        models.DealLink.entity_id == po.id,
    ).delete(synchronize_session=False)
    db.add(
        models.DealLink(
            deal_id=int(deal.id),
            entity_type=models.DealEntityType.po,
            entity_id=int(po.id),
            direction=models.DealDirection.buy,
            quantity_mt=float(po.total_quantity_mt),
            allocation_type=models.DealAllocationType.manual,
        )
    )

    return po


def _ensure_rfq_and_contract_for_so(
    db: Session,
    *,
    company: CompanySpec,
    rfq_number: str,
    deal_id: int,
    so_id: int,
    quantity_mt: float,
    counterparty_id: int,
    fixed_price: float,
    month_name: str,
    year: int,
    actor_user_id: int | None,
    correlation_id: str,
    rng: random.Random,
) -> tuple[models.Rfq, models.Contract]:
    rfq = db.query(models.Rfq).filter(models.Rfq.rfq_number == rfq_number).first()
    if rfq is None:
        rfq = models.Rfq(
            deal_id=int(deal_id),
            rfq_number=rfq_number,
            so_id=int(so_id),
            quantity_mt=float(quantity_mt),
            period=f"{month_name[:3].title()}-{str(year)[-2:]}",
            status=models.RfqStatus.awarded,
            sent_at=datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=rng.randint(5, 40)),
            awarded_at=datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=rng.randint(1, 10)),
            decided_by=actor_user_id,
            decided_at=datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=rng.randint(1, 10)),
            trade_specs=[
                {
                    "trade_type": "SWAP",
                    "trade_index": 0,
                    "quote_group_id": f"{company.code}-QG-{uuid.uuid4().hex[:8]}",
                    "leg1": {
                        "side": "buy",
                        "price_type": "AVG",
                        "quantity_mt": float(quantity_mt),
                        "month_name": str(month_name).lower(),
                        "year": int(year),
                    },
                    "leg2": {
                        "side": "sell",
                        "price_type": "Fix",
                        "quantity_mt": float(quantity_mt),
                        "price": float(fixed_price),
                    },
                    "sync_ppt": True,
                }
            ],
        )
        db.add(rfq)
        db.flush()

        # Winner quote and invitation (minimal, but coherent).
        q = models.RfqQuote(
            rfq_id=int(rfq.id),
            counterparty_id=int(counterparty_id),
            counterparty_name=db.get(models.Counterparty, int(counterparty_id)).name
            if db.get(models.Counterparty, int(counterparty_id))
            else None,
            quote_price=float(fixed_price),
            price_type="Fix",
            volume_mt=float(quantity_mt),
            valid_until=datetime.utcnow().replace(tzinfo=timezone.utc) + timedelta(days=2),
            notes="Indicative firm quote; subject to internal approvals.",
            channel=rng.choice(["whatsapp", "email", "api"]),
            status="quoted",
            quote_group_id=(rfq.trade_specs[0] or {}).get("quote_group_id"),
            leg_side="sell",
        )
        db.add(q)
        db.flush()
        rfq.winner_quote_id = int(q.id)
        rfq.winner_rank = 1
        db.add(rfq)

        inv = models.RfqInvitation(
            rfq_id=int(rfq.id),
            counterparty_id=int(counterparty_id),
            counterparty_name=q.counterparty_name,
            status="winner",
            sent_at=rfq.sent_at or datetime.utcnow().replace(tzinfo=timezone.utc),
            responded_at=rfq.awarded_at,
            expires_at=(rfq.sent_at + timedelta(days=2)) if rfq.sent_at else None,
            message_text="RFQ seeded for institutional QA.",
        )
        db.add(inv)

        # Commit RFQ/Quote/Invitation before emitting timeline.
        # emit_timeline_event commits/rollbacks internally for idempotency.
        db.commit()

        emit_timeline_event(
            db=db,
            event_type="RFQ_AWARDED",
            subject_type="rfq",
            subject_id=int(rfq.id),
            correlation_id=correlation_id,
            idempotency_key=f"seed:rfq:{rfq.rfq_number}:awarded",
            visibility="finance",
            actor_user_id=actor_user_id,
            payload={
                "rfq_id": int(rfq.id),
                "rfq_number": rfq.rfq_number,
                "so_id": int(rfq.so_id),
                "winner_counterparty_id": int(counterparty_id),
                "quote_price": float(fixed_price),
            },
        )

    # Contract
    contract_number = f"{company.code}-CT-{int(rfq.id):05d}"
    contract = (
        db.query(models.Contract)
        .filter(models.Contract.contract_number == contract_number)
        .first()
    )
    if contract is None:
        # Observation month bounds for settlement date heuristic.
        obs_start = date(int(year), _month_to_int(month_name), 1)
        obs_end = _month_end(obs_start)
        settlement_date = obs_end + timedelta(days=rng.randint(3, 12))

        trade_snapshot = {
            "trade_index": 0,
            "quote_group_id": (rfq.trade_specs[0] or {}).get("quote_group_id"),
            "legs": [
                {
                    "side": "buy",
                    "price_type": "AVG",
                    "volume_mt": float(quantity_mt),
                    "month_name": str(month_name).lower(),
                    "year": int(year),
                },
                {
                    "side": "sell",
                    "price_type": "Fix",
                    "volume_mt": float(quantity_mt),
                    "price": float(fixed_price),
                },
            ],
        }

        contract = models.Contract(
            contract_number=contract_number,
            deal_id=int(deal_id),
            rfq_id=int(rfq.id),
            counterparty_id=int(counterparty_id),
            status=models.ContractStatus.active.value,
            trade_index=0,
            quote_group_id=(rfq.trade_specs[0] or {}).get("quote_group_id"),
            trade_snapshot=trade_snapshot,
            settlement_date=settlement_date,
            settlement_meta={
                "source": "seed_realistic_data",
                "observation_start": obs_start.isoformat(),
                "observation_end": obs_end.isoformat(),
            },
            created_by=actor_user_id,
        )
        db.add(contract)
        db.flush()

        # Commit contract before timeline emission for the same reason as above.
        db.commit()

        emit_timeline_event(
            db=db,
            event_type="CONTRACT_CREATED",
            subject_type="rfq",
            subject_id=int(rfq.id),
            correlation_id=correlation_id,
            idempotency_key=f"seed:contract:{contract.contract_number}:created",
            visibility="finance",
            actor_user_id=actor_user_id,
            payload={
                "contract_id": str(contract.contract_id),
                "contract_number": contract.contract_number,
                "rfq_id": int(rfq.id),
                "deal_id": int(deal_id),
                "counterparty_id": int(counterparty_id),
                "settlement_date": contract.settlement_date.isoformat()
                if contract.settlement_date
                else None,
            },
        )

    db.commit()
    return rfq, contract


def _month_to_int(month_name: str) -> int:
    m = (month_name or "").strip().lower()
    months = [
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    ]
    if m not in months:
        raise ValueError("invalid month_name")
    return months.index(m) + 1


def _month_end(start: date) -> date:
    if start.month == 12:
        return date(start.year + 1, 1, 1) - timedelta(days=1)
    return date(start.year, start.month + 1, 1) - timedelta(days=1)


def _seed_company(
    db: Session,
    *,
    company: CompanySpec,
    rng: random.Random,
    actor_ids: dict[str, int],
    scale: float,
    correlation_id: str,
) -> None:
    # Marker: idempotent audit log.
    if _already_seeded(db, company):
        return

    # ---- counterparties / customers / suppliers ----
    base_customers = [
        "Novelis Europe GmbH",
        "Hydro Extrusions Trading",
        "Constellium Trading",
        "UACJ Americas",
        "Arconic Rolled Products",
        "Ball Beverage Packaging",
        "Crown Holdings Metals",
        "Gränges AB",
        "Norsk Metall Imports",
        "Metal Exchange LatAm",
        "Grupo Alubar",
        "CBA Comercial",
        "Votorantim Metais",
        "Gerdau Aços Longos",
        "CSN Trading",
        "Aperam Alloys",
        "Tupy Industrial",
        "Randon Components",
        "Embraer Supply Chain",
        "Flex Metals Solutions",
        "Delta Metals Trading",
        "Andes Packaging",
        "Pacific Alloy Traders",
        "Monterrey Extrusion",
        "Maple Metals Distribution",
        "Iberia Metals",
        "Balkan Aluminium Buyers",
        "Nordic Light Metals",
    ]

    base_suppliers = [
        "Rio Tinto Aluminium",
        "Alcoa Primary Metals",
        "South32 Aluminium",
        "Rusal Trading",
        "Emirates Global Aluminium",
        "Qatalum",
        "Bahrain Aluminium (ALBA)",
        "Vedanta Aluminium",
        "Hindalco Industries",
        "Norsk Hydro Primary",
        "Century Aluminum",
        "Press Metal",
        "Aluminium Bahrain Shipping",
        "Oman Aluminium Rolling",
        "Queensland Alumina",
        "Mozal Aluminium",
        "Ma'aden Aluminium",
        "Sohar Aluminium",
        "Aluminum Bahrain Sows",
        "Gulf Aluminium Supply",
        "Canadian Smelter Supply",
        "Iceland Smelter Trading",
    ]

    base_counterparties = [
        ("Marex", models.CounterpartyType.broker),
        ("StoneX", models.CounterpartyType.broker),
        ("TP ICAP", models.CounterpartyType.broker),
        ("Mitsubishi UFJ", models.CounterpartyType.bank),
        ("J.P. Morgan", models.CounterpartyType.bank),
        ("ING Metals", models.CounterpartyType.bank),
        ("Standard Chartered", models.CounterpartyType.bank),
        ("SocGen Commodities", models.CounterpartyType.bank),
        ("ED&F Man Capital", models.CounterpartyType.broker),
        ("Citigroup Metals", models.CounterpartyType.bank),
        ("Macquarie Commodities", models.CounterpartyType.bank),
        ("BNP Paribas Commodities", models.CounterpartyType.bank),
    ]

    n_customers = max(20, min(30, int(round(25 * scale))))
    n_suppliers = max(15, min(25, int(round(20 * scale))))
    n_counterparties = max(8, min(12, int(round(10 * scale))))

    customers: list[models.Customer] = []
    for i in range(n_customers):
        code = f"{company.code}-CUST-{i+1:03d}"
        name = f"{company.label} — {base_customers[i % len(base_customers)]}"
        customers.append(_ensure_customer(db, company=company, code=code, name=name, rng=rng))

    suppliers: list[models.Supplier] = []
    for i in range(n_suppliers):
        code = f"{company.code}-SUP-{i+1:03d}"
        name = f"{company.label} — {base_suppliers[i % len(base_suppliers)]}"
        suppliers.append(_ensure_supplier(db, company=company, code=code, name=name, rng=rng))

    counterparties: list[models.Counterparty] = []
    for i in range(n_counterparties):
        base_name, cp_type = base_counterparties[i % len(base_counterparties)]
        name = f"{company.label} — {base_name}"
        counterparties.append(
            _ensure_counterparty(db, company=company, name=name, cp_type=cp_type, rng=rng)
        )

    db.commit()

    # ---- deals ----
    n_deals = max(30, min(50, int(round(40 * scale))))
    deals: list[models.Deal] = []
    scenarios = [
        "Billet premiums • Europe",
        "P1020A • LatAm shipments",
        "Sows • Gulf origin",
        "T-bar • US Midwest",
        "Rolling slab • OEM supply",
        "Scrap hedge offset • blend",
    ]
    for i in range(n_deals):
        ref = f"{company.code} • D{i+1:03d} • {rng.choice(scenarios)}"
        deals.append(_ensure_deal(db, company=company, reference_name=ref, created_by=actor_ids.get("admin")))

    db.commit()

    # ---- SO/PO generation targets ----
    n_sos = max(80, min(150, int(round(120 * scale))))
    n_pos = max(80, min(150, int(round(120 * scale))))

    pt_weights: list[tuple[models.PriceType, float]] = [
        (models.PriceType.FIX, 0.40),
        (models.PriceType.AVG, 0.30),
        (models.PriceType.AVG_INTER, 0.15),
        (models.PriceType.C2R, 0.15),
    ]

    created_exposures: list[int] = []

    # Sales Orders
    for i in range(n_sos):
        deal = deals[i % len(deals)]
        cust = customers[(i * 3) % len(customers)]
        pt = _weighted_choice(rng, pt_weights)
        qty = float(rng.uniform(180.0, 2600.0))
        dd = _today_utc() + timedelta(days=_pick_horizon_bucket(rng))
        so_number = f"{company.code}-SO-{i+1:05d}"

        so = _create_sales_order(
            db,
            company=company,
            deal=deal,
            so_number=so_number,
            customer_id=int(cust.id),
            pricing_type=pt,
            qty_mt=qty,
            delivery_date=dd,
            rng=rng,
        )
        db.flush()

        rec = reconcile_sales_order_exposures(db=db, so=so)

        # Important: timeline emission commits/rollbacks internally for idempotency.
        # Commit the exposure mutations first so a timeline idempotency conflict
        # cannot rollback the newly-created exposure rows.
        created_ids = list(rec.created_exposure_ids)
        recalculated_ids = list(rec.recalculated_exposure_ids)
        closed_ids = list(rec.closed_exposure_ids)
        db.commit()

        for exp_id in created_ids:
            exp = db.get(models.Exposure, int(exp_id))
            if exp is not None:
                emit_exposure_created(
                    db=db,
                    exposure=exp,
                    correlation_id=correlation_id,
                    actor_user_id=actor_ids.get("finance"),
                )
                created_exposures.append(int(exp_id))
        for exp_id in recalculated_ids:
            exp = db.get(models.Exposure, int(exp_id))
            if exp is not None:
                emit_exposure_recalculated(
                    db=db,
                    exposure=exp,
                    correlation_id=correlation_id,
                    actor_user_id=actor_ids.get("finance"),
                    reason="seed_sales_order",
                )
        for exp_id in closed_ids:
            exp = db.get(models.Exposure, int(exp_id))
            if exp is not None:
                emit_exposure_closed(
                    db=db,
                    exposure=exp,
                    correlation_id=correlation_id,
                    actor_user_id=actor_ids.get("finance"),
                    reason="seed_sales_order",
                )

    # Purchase Orders
    for i in range(n_pos):
        deal = deals[(i * 2) % len(deals)]
        sup = suppliers[(i * 5) % len(suppliers)]
        pt = _weighted_choice(rng, pt_weights)
        qty = float(rng.uniform(200.0, 3200.0))
        dd = _today_utc() + timedelta(days=_pick_horizon_bucket(rng))
        po_number = f"{company.code}-PO-{i+1:05d}"

        po = _create_purchase_order(
            db,
            company=company,
            deal=deal,
            po_number=po_number,
            supplier_id=int(sup.id),
            pricing_type=pt,
            qty_mt=qty,
            delivery_date=dd,
            rng=rng,
        )
        db.flush()

        rec = reconcile_purchase_order_exposures(db=db, po=po)
        created_ids = list(rec.created_exposure_ids)
        recalculated_ids = list(rec.recalculated_exposure_ids)
        closed_ids = list(rec.closed_exposure_ids)
        db.commit()

        for exp_id in created_ids:
            exp = db.get(models.Exposure, int(exp_id))
            if exp is not None:
                emit_exposure_created(
                    db=db,
                    exposure=exp,
                    correlation_id=correlation_id,
                    actor_user_id=actor_ids.get("finance"),
                )
                created_exposures.append(int(exp_id))
        for exp_id in recalculated_ids:
            exp = db.get(models.Exposure, int(exp_id))
            if exp is not None:
                emit_exposure_recalculated(
                    db=db,
                    exposure=exp,
                    correlation_id=correlation_id,
                    actor_user_id=actor_ids.get("finance"),
                    reason="seed_purchase_order",
                )
        for exp_id in closed_ids:
            exp = db.get(models.Exposure, int(exp_id))
            if exp is not None:
                emit_exposure_closed(
                    db=db,
                    exposure=exp,
                    correlation_id=correlation_id,
                    actor_user_id=actor_ids.get("finance"),
                    reason="seed_purchase_order",
                )

    db.commit()

    # ---- Hedge scenarios (open / partial / hedged / closed) ----
    rng.shuffle(created_exposures)

    def _reconcile_source_for_exposure(exp: models.Exposure) -> None:
        if exp.source_type == models.MarketObjectType.so:
            so = db.get(models.SalesOrder, int(exp.source_id))
            if so is None:
                return
            rec = reconcile_sales_order_exposures(db=db, so=so)
        else:
            po = db.get(models.PurchaseOrder, int(exp.source_id))
            if po is None:
                return
            rec = reconcile_purchase_order_exposures(db=db, po=po)
        recalculated_ids = list(rec.recalculated_exposure_ids)
        closed_ids = list(rec.closed_exposure_ids)
        db.commit()

        # Emit recalculated/closed after committing the mutations.
        for exp_id in recalculated_ids:
            ex = db.get(models.Exposure, int(exp_id))
            if ex is not None:
                emit_exposure_recalculated(
                    db=db,
                    exposure=ex,
                    correlation_id=correlation_id,
                    actor_user_id=actor_ids.get("finance"),
                    reason="seed_hedge_link",
                )
        for exp_id in closed_ids:
            ex = db.get(models.Exposure, int(exp_id))
            if ex is not None:
                emit_exposure_closed(
                    db=db,
                    exposure=ex,
                    correlation_id=correlation_id,
                    actor_user_id=actor_ids.get("finance"),
                    reason="seed_hedge_link",
                )

    for idx, exp_id in enumerate(created_exposures):
        exp = db.get(models.Exposure, int(exp_id))
        if exp is None:
            continue

        r = idx / max(1, len(created_exposures))
        if r < 0.30:
            # keep open
            continue
        if r < 0.60:
            # partially hedged
            hedge_qty = float(exp.quantity_mt) * float(rng.uniform(0.25, 0.70))
        elif r < 0.85:
            # fully hedged
            hedge_qty = float(exp.quantity_mt)
        else:
            # close exposure to simulate closed lifecycle
            close_open_exposures_for_source(
                db=db,
                source_type=exp.source_type,
                source_id=int(exp.source_id),
            )
            db.commit()
            exp2 = db.get(models.Exposure, int(exp.id))
            if exp2 is not None:
                emit_exposure_closed(
                    db=db,
                    exposure=exp2,
                    correlation_id=correlation_id,
                    actor_user_id=actor_ids.get("finance"),
                    reason="seed_close",
                )
            continue

        cp = counterparties[idx % len(counterparties)]
        hedge = models.Hedge(
            so_id=int(exp.source_id) if exp.source_type == models.MarketObjectType.so else None,
            counterparty_id=int(cp.id),
            quantity_mt=float(hedge_qty),
            contract_price=float(rng.uniform(2350.0, 2850.0)),
            current_market_price=float(rng.uniform(2350.0, 2850.0)),
            mtm_value=None,
            period=rng.choice(["Jan-26", "Feb-26", "Mar-26", "Apr-26", "May-26", "Jun-26"]),
            instrument="LME Aluminium Swap",
            maturity_date=None,
            reference_code=f"{company.code}-HEDGE-{uuid.uuid4().hex[:10].upper()}",
            status=models.HedgeStatus.active if rng.random() > 0.18 else models.HedgeStatus.closed,
        )
        db.add(hedge)
        db.flush()

        db.add(
            models.HedgeExposure(
                hedge_id=int(hedge.id),
                exposure_id=int(exp.id),
                quantity_mt=float(hedge_qty),
            )
        )

        # Link to deal for entity-tree visibility.
        try:
            # Find deal via source order.
            deal_id = None
            if exp.source_type == models.MarketObjectType.so:
                so = db.get(models.SalesOrder, int(exp.source_id))
                deal_id = int(so.deal_id) if so else None
            else:
                po = db.get(models.PurchaseOrder, int(exp.source_id))
                deal_id = int(po.deal_id) if po else None

            if deal_id is not None:
                link_hedge_to_deal(db, hedge, deal_id)
        except Exception:
            # Keep seeding resilient.
            pass

        db.commit()
        _reconcile_source_for_exposure(exp)

    # ---- Treasury Decisions + KYC overrides ----
    open_or_partial = (
        db.query(models.Exposure)
        .filter(models.Exposure.status.in_([models.ExposureStatus.open, models.ExposureStatus.partially_hedged]))
        .order_by(models.Exposure.id.asc())
        .all()
    )

    for i, exp in enumerate(open_or_partial[: max(25, int(0.25 * len(open_or_partial)))]):
        kind = rng.choice(
            [
                models.TreasuryDecisionKind.hedge,
                models.TreasuryDecisionKind.do_not_hedge,
                models.TreasuryDecisionKind.roll,
                models.TreasuryDecisionKind.hedge,
            ]
        )
        td = create_treasury_decision(
            db=db,
            exposure_id=int(exp.id),
            decision_kind=kind,
            notes=rng.choice(
                [
                    "Decision based on current premiums and inventory cover.",
                    "Awaiting customer KYC refresh / documents.",
                    "Partial hedge due to liquidity constraints.",
                    "Hold for better execution window; reassess next week.",
                ]
            ),
            decided_at=datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=rng.randint(0, 45)),
            actor_user_id=actor_ids.get("finance"),
            request_id=f"seed-{company.slug}",
            ip=None,
            user_agent="seed_realistic_data",
        )

        gate = (td.kyc_gate_json or {})
        if not bool(gate.get("allowed")) and rng.random() < 0.35:
            create_kyc_override(
                db=db,
                decision=td,
                reason="Override autorizado para fins de execução institucional (seed).",
                actor_user_id=actor_ids.get("admin"),
                request_id=f"seed-{company.slug}",
                ip=None,
                user_agent="seed_realistic_data",
            )

    # ---- RFQs + Contracts for a subset of SO exposures ----
    so_exposures = (
        db.query(models.Exposure)
        .filter(models.Exposure.source_type == models.MarketObjectType.so)
        .order_by(models.Exposure.id.asc())
        .limit(max(20, int(0.20 * len(open_or_partial))))
        .all()
    )

    month_pool = [
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    ]

    for i, exp in enumerate(so_exposures):
        so = db.get(models.SalesOrder, int(exp.source_id))
        if so is None:
            continue
        if so.status != models.OrderStatus.active:
            continue

        # create an approval request for some awards (Inbox)
        try:
            if rng.random() < 0.25:
                # This will raise 409 and emit timeline; we want the request to exist.
                require_approval_or_raise(
                    db=db,
                    action="rfq.award",
                    subject_type="rfq",
                    subject_id=str(100000 + int(exp.id)),  # pseudo subject for inbox diversity
                    notional_usd=float(exp.quantity_mt) * float(rng.uniform(2300.0, 2800.0)),
                    context={
                        "company": company.slug,
                        "exposure_id": int(exp.id),
                        "hint": "seed",
                    },
                    requested_by_user_id=actor_ids.get("finance"),
                    correlation_id=correlation_id,
                    workflow_request_id=None,
                    request_id=f"seed-{company.slug}",
                    ip=None,
                    user_agent="seed_realistic_data",
                )
        except Exception:
            # expected (HTTPException 409)
            pass

        month_name = month_pool[(i + rng.randint(0, 3)) % len(month_pool)]
        year = _today_utc().year

        rfq_number = f"{company.code}-RFQ-{int(exp.id):05d}"
        cp = counterparties[(i * 2) % len(counterparties)]
        fixed_price = float(rng.uniform(2380.0, 2860.0))

        rfq, contract = _ensure_rfq_and_contract_for_so(
            db,
            company=company,
            rfq_number=rfq_number,
            deal_id=int(so.deal_id),
            so_id=int(so.id),
            quantity_mt=float(min(float(exp.quantity_mt), float(so.total_quantity_mt))),
            counterparty_id=int(cp.id),
            fixed_price=fixed_price,
            month_name=month_name,
            year=year,
            actor_user_id=actor_ids.get("finance"),
            correlation_id=correlation_id,
            rng=rng,
        )

        # Traceability: link contract to the exposure.
        existing_link = (
            db.query(models.ContractExposure)
            .filter(models.ContractExposure.contract_id == str(contract.contract_id))
            .filter(models.ContractExposure.exposure_id == int(exp.id))
            .first()
        )
        if existing_link is None:
            db.add(
                models.ContractExposure(
                    contract_id=str(contract.contract_id),
                    exposure_id=int(exp.id),
                    quantity_mt=float(min(float(exp.quantity_mt), float(so.total_quantity_mt))),
                )
            )
            db.commit()

    # Marker audit log
    audit_event(
        "seed.realistic_data.completed",
        actor_ids.get("admin"),
        {
            "company": company.slug,
            "code": company.code,
            "label": company.label,
            "scale": scale,
        },
        db=db,
        idempotency_key=_seed_marker_key(company),
        request_id=f"seed-{company.slug}",
        user_agent="seed_realistic_data",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Seed institutional-grade, coherent demo data for ALCAST Hedge Management. "
            "Generates realistic counterparties, deals, SO/PO, exposures, hedges, RFQs, contracts, "
            "timeline/governance events, and workflow inbox entries."
        )
    )
    parser.add_argument(
        "--company",
        default="all",
        choices=["all", *sorted(COMPANIES.keys())],
        help="Which legal company dataset to seed (default: all)",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Scale factor for volumes (default: 1.0).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260119,
        help="RNG seed for deterministic datasets (default: 20260119)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete previously seeded data for the selected company before seeding.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force run even if a seed marker already exists (still de-duplicates by unique keys).",
    )
    parser.add_argument(
        "--password",
        default="123",
        help="Password for seeded dev users (default: 123)",
    )
    parser.add_argument(
        "--lme-days",
        type=int,
        default=420,
        help="How many days of LME prices to ensure (default: 420)",
    )
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="Allow running even when ENVIRONMENT=production/prod",
    )

    args = parser.parse_args()

    _env_guard(allow_production=bool(args.allow_production))

    scale = float(args.scale)
    if scale <= 0:
        raise SystemExit("--scale must be > 0")

    rng = random.Random(int(args.seed))
    correlation_id = f"seed:{uuid.uuid4()}"

    targets: list[CompanySpec]
    if args.company == "all":
        targets = [COMPANIES[k] for k in sorted(COMPANIES.keys())]
    else:
        targets = [COMPANIES[str(args.company)]]

    db = SessionLocal()
    try:
        actor_ids = _ensure_roles_and_seed_users(db, password=str(args.password))

        _ensure_lme_prices(db, days=int(args.lme_days))

        for company in targets:
            if args.reset:
                _reset_company(db, company)

            if _already_seeded(db, company) and not args.force:
                print(
                    f"[{company.code}] seed marker already exists; skipping. "
                    "Use --reset to delete seeded data, or --force to re-run." 
                )
                continue

            # ensure marker is cleared when forcing without reset
            if args.force:
                db.query(models.AuditLog).filter(
                    models.AuditLog.idempotency_key == _seed_marker_key(company)
                ).delete(synchronize_session=False)
                db.commit()

            _seed_company(
                db,
                company=company,
                rng=rng,
                actor_ids=actor_ids,
                scale=scale,
                correlation_id=correlation_id,
            )

        # Summary
        deals = int(db.query(func.count(models.Deal.id)).scalar() or 0)
        sos = int(db.query(func.count(models.SalesOrder.id)).scalar() or 0)
        pos = int(db.query(func.count(models.PurchaseOrder.id)).scalar() or 0)
        exps = int(db.query(func.count(models.Exposure.id)).scalar() or 0)
        contracts = int(db.query(func.count(models.Contract.contract_id)).scalar() or 0)
        wf = int(db.query(func.count(models.WorkflowRequest.id)).scalar() or 0)

        print("Seed realistic data OK")
        print(f"- deals: {deals}")
        print(f"- sales_orders: {sos}")
        print(f"- purchase_orders: {pos}")
        print(f"- exposures: {exps}")
        print(f"- contracts: {contracts}")
        print(f"- workflow_requests: {wf}")

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
