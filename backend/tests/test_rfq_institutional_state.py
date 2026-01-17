from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base


def _make_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
    return SessionLocal


def _seed_so(db):
    seed_time = datetime(2026, 1, 1, 0, 0, 0)
    customer = models.Customer(name="Cust 1", created_at=seed_time)
    db.add(customer)
    db.flush()

    deal = models.Deal(
        commodity="AL",
        currency="USD",
        status=models.DealStatus.open,
        lifecycle_status=models.DealLifecycleStatus.open,
        created_at=seed_time,
    )
    db.add(deal)
    db.flush()

    so = models.SalesOrder(
        so_number="SO-1",
        deal_id=deal.id,
        customer_id=customer.id,
        product="AL",
        total_quantity_mt=10.0,
        unit_price=1000.0,
        pricing_type=models.PricingType.monthly_average,
        status=models.OrderStatus.draft,
        created_at=seed_time,
    )
    db.add(so)
    db.flush()
    return so


def test_rfq_institutional_state_created_from_pending():
    SessionLocal = _make_session()
    with SessionLocal() as db:
        so = _seed_so(db)
        rfq = models.Rfq(
            deal_id=so.deal_id,
            rfq_number="RFQ-1",
            so_id=so.id,
            quantity_mt=10.0,
            period="2026-01",
            status=models.RfqStatus.pending,
            created_at=datetime(2026, 1, 1, 0, 0, 0),
        )
        db.add(rfq)
        db.commit()
        db.refresh(rfq)

        assert rfq.institutional_state == models.RfqInstitutionalState.CREATED


def test_rfq_institutional_state_sending_when_attempt_queued():
    SessionLocal = _make_session()
    with SessionLocal() as db:
        so = _seed_so(db)
        rfq = models.Rfq(
            deal_id=so.deal_id,
            rfq_number="RFQ-1",
            so_id=so.id,
            quantity_mt=10.0,
            period="2026-01",
            status=models.RfqStatus.sent,
            sent_at=datetime(2026, 1, 1, 0, 0, 0),
            created_at=datetime(2026, 1, 1, 0, 0, 0),
        )
        db.add(rfq)
        db.flush()

        db.add(
            models.RfqSendAttempt(
                rfq_id=rfq.id,
                channel="api",
                status=models.SendStatus.queued,
                created_at=datetime(2026, 1, 1, 0, 0, 0),
            )
        )
        db.commit()
        db.refresh(rfq)

        assert rfq.institutional_state == models.RfqInstitutionalState.SENDING


def test_rfq_institutional_state_sent_when_no_pending_attempts():
    SessionLocal = _make_session()
    with SessionLocal() as db:
        so = _seed_so(db)
        rfq = models.Rfq(
            deal_id=so.deal_id,
            rfq_number="RFQ-1",
            so_id=so.id,
            quantity_mt=10.0,
            period="2026-01",
            status=models.RfqStatus.sent,
            sent_at=datetime(2026, 1, 1, 0, 0, 0),
            created_at=datetime(2026, 1, 1, 0, 0, 0),
        )
        db.add(rfq)
        db.flush()

        db.add(
            models.RfqSendAttempt(
                rfq_id=rfq.id,
                channel="api",
                status=models.SendStatus.sent,
                created_at=datetime(2026, 1, 1, 0, 0, 0),
            )
        )
        db.commit()
        db.refresh(rfq)

        assert rfq.institutional_state == models.RfqInstitutionalState.SENT


def test_rfq_institutional_state_partial_response_from_quoted():
    SessionLocal = _make_session()
    with SessionLocal() as db:
        so = _seed_so(db)
        rfq = models.Rfq(
            deal_id=so.deal_id,
            rfq_number="RFQ-1",
            so_id=so.id,
            quantity_mt=10.0,
            period="2026-01",
            status=models.RfqStatus.quoted,
            created_at=datetime(2026, 1, 1, 0, 0, 0),
        )
        db.add(rfq)
        db.commit()
        db.refresh(rfq)

        assert rfq.institutional_state == models.RfqInstitutionalState.PARTIAL_RESPONSE


def test_rfq_institutional_state_partial_response_when_quote_exists_even_if_status_sent():
    SessionLocal = _make_session()
    with SessionLocal() as db:
        so = _seed_so(db)
        rfq = models.Rfq(
            deal_id=so.deal_id,
            rfq_number="RFQ-1",
            so_id=so.id,
            quantity_mt=10.0,
            period="2026-01",
            status=models.RfqStatus.sent,
            sent_at=datetime(2026, 1, 1, 0, 0, 0),
            created_at=datetime(2026, 1, 1, 0, 0, 0),
        )
        db.add(rfq)
        db.flush()

        db.add(
            models.RfqQuote(
                rfq_id=rfq.id,
                counterparty_name="CP 1",
                quote_price=100.0,
                channel="api",
                status="quoted",
            )
        )
        db.commit()
        db.refresh(rfq)

        assert rfq.institutional_state == models.RfqInstitutionalState.PARTIAL_RESPONSE


def test_rfq_institutional_state_closed_for_awarded_and_archived_for_expired():
    SessionLocal = _make_session()
    with SessionLocal() as db:
        so = _seed_so(db)

        rfq_awarded = models.Rfq(
            deal_id=so.deal_id,
            rfq_number="RFQ-A",
            so_id=so.id,
            quantity_mt=10.0,
            period="2026-01",
            status=models.RfqStatus.awarded,
            created_at=datetime(2026, 1, 1, 0, 0, 0),
        )
        rfq_expired = models.Rfq(
            deal_id=so.deal_id,
            rfq_number="RFQ-E",
            so_id=so.id,
            quantity_mt=10.0,
            period="2026-01",
            status=models.RfqStatus.expired,
            created_at=datetime(2026, 1, 1, 0, 0, 0),
        )

        db.add_all([rfq_awarded, rfq_expired])
        db.commit()
        db.refresh(rfq_awarded)
        db.refresh(rfq_expired)

        assert rfq_awarded.institutional_state == models.RfqInstitutionalState.CLOSED
        assert rfq_expired.institutional_state == models.RfqInstitutionalState.ARCHIVED
