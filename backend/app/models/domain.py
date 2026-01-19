# ruff: noqa: E501
import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    and_,
    event,
    func,
)
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship, validates

from app.database import Base


class RoleName(PyEnum):
    admin = "admin"
    compras = "compras"
    vendas = "vendas"
    financeiro = "financeiro"
    estoque = "estoque"
    auditoria = "auditoria"


class OrderStatus(PyEnum):
    draft = "draft"
    active = "active"
    completed = "completed"
    cancelled = "cancelled"


class PricingType(PyEnum):
    fixed = "fixed"
    tbf = "tbf"
    monthly_average = "monthly_average"
    lme_premium = "lme_premium"


class PriceType(PyEnum):
    AVG = "AVG"
    AVG_INTER = "AVGInter"
    FIX = "Fix"
    C2R = "C2R"


class CounterpartyType(PyEnum):
    bank = "bank"
    broker = "broker"


class DocumentOwnerType(PyEnum):
    customer = "customer"
    supplier = "supplier"
    counterparty = "counterparty"


class TreasuryDecisionKind(PyEnum):
    hedge = "hedge"
    do_not_hedge = "do_not_hedge"
    roll = "roll"
    close = "close"


class RfqStatus(PyEnum):
    draft = "draft"
    pending = "pending"
    sent = "sent"
    quoted = "quoted"
    awarded = "awarded"
    expired = "expired"
    failed = "failed"


class RfqInstitutionalState(PyEnum):
    CREATED = "CREATED"
    SENDING = "SENDING"
    SENT = "SENT"
    PARTIAL_RESPONSE = "PARTIAL_RESPONSE"
    CLOSED = "CLOSED"
    ARCHIVED = "ARCHIVED"


class HedgeStatus(PyEnum):
    active = "active"
    closed = "closed"
    cancelled = "cancelled"


class SendStatus(PyEnum):
    queued = "queued"
    sent = "sent"
    failed = "failed"


class MarketObjectType(PyEnum):
    hedge = "hedge"
    po = "po"
    so = "so"
    portfolio = "portfolio"
    exposure = "exposure"
    net = "net"


class ExposureType(PyEnum):
    active = "active"  # risco de queda (derivado de SO)
    passive = "passive"  # risco de alta (derivado de PO)


class ExposureStatus(PyEnum):
    open = "open"
    partially_hedged = "partially_hedged"
    hedged = "hedged"
    closed = "closed"


class HedgeTaskStatus(PyEnum):
    pending = "pending"
    in_progress = "in_progress"
    hedged = "hedged"
    completed = "completed"
    cancelled = "cancelled"


class DealLifecycleStatus(PyEnum):
    open = "open"
    partially_hedged = "partially_hedged"
    hedged = "hedged"
    closed = "closed"


class WhatsAppDirection(PyEnum):
    inbound = "inbound"
    outbound = "outbound"


class WhatsAppStatus(PyEnum):
    queued = "queued"
    sent = "sent"
    delivered = "delivered"
    failed = "failed"
    received = "received"


class DealStatus(PyEnum):
    open = "open"
    partially_fixed = "partially_fixed"
    fixed = "fixed"
    settled = "settled"


class DealEntityType(PyEnum):
    so = "so"
    po = "po"
    hedge = "hedge"


class DealDirection(PyEnum):
    buy = "buy"
    sell = "sell"


class DealAllocationType(PyEnum):
    auto = "auto"
    manual = "manual"


class ContractStatus(PyEnum):
    active = "active"
    settled = "settled"
    cancelled = "cancelled"


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Supabase schema stores roles.name as VARCHAR (not a Postgres ENUM).
    name: Mapped[RoleName] = mapped_column(
        Enum(RoleName, native_enum=False), unique=True, nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(255))

    users = relationship("User", back_populates="role")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    role = relationship("Role", back_populates="users")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    rfq_id: Mapped[int | None] = mapped_column(ForeignKey("rfqs.id"), nullable=True)
    payload_json: Mapped[str | None] = mapped_column(Text)

    # Optional request context (added via later migration; safe to keep nullable).
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Optional idempotency (used by new workflow/events; safe to keep nullable).
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        unique=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", lazy="joined")


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Deterministic identifier derived from export request inputs.
    export_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    inputs_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    export_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    as_of: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    filters: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Artifact references (e.g., storage_uri/checksum) are only considered valid when status='done'.
    artifacts: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="queued", index=True
    )

    requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    requested_by = relationship("User", foreign_keys=[requested_by_user_id], lazy="joined")


class DocumentMonthlySequence(Base):
    __tablename__ = "document_monthly_sequences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_type: Mapped[str] = mapped_column(String(16), nullable=False)
    year_month: Mapped[str] = mapped_column(String(6), nullable=False)  # YYYYMM
    last_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("doc_type", "year_month", name="uq_doc_seq_doc_type_year_month"),
    )


class WorkflowRequest(Base):
    __tablename__ = "workflow_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Deterministic request key derived from action+subject+context.
    request_key: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    inputs_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    subject_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # forward-only: pending -> approved|rejected -> executed
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="pending", index=True
    )

    notional_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    required_role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    sla_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    requested_by = relationship("User", foreign_keys=[requested_by_user_id], lazy="joined")
    decisions = relationship("WorkflowDecision", back_populates="workflow_request")


class WorkflowDecision(Base):
    __tablename__ = "workflow_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    workflow_request_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_requests.id"), nullable=False, index=True
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    workflow_request = relationship("WorkflowRequest", back_populates="decisions")
    decided_by = relationship("User", foreign_keys=[decided_by_user_id], lazy="joined")


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    __table_args__ = (
        UniqueConstraint(
            "event_type",
            "idempotency_key",
            name="uq_timeline_events_event_type_idempotency_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # What happened
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # Primary subject (entity)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    subject_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Correlation / correction
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    supersedes_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("timeline_events.id"), nullable=True, index=True
    )

    # Idempotency (optional)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Who/where
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    audit_log_id: Mapped[int | None] = mapped_column(
        ForeignKey("audit_logs.id"), nullable=True, index=True
    )

    # Visibility: 'all' (default) or 'finance'
    visibility: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="all", index=True
    )

    # Payload + metadata
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    actor = relationship("User", foreign_keys=[actor_user_id], lazy="joined")
    audit_log = relationship("AuditLog", foreign_keys=[audit_log_id], lazy="joined")
    supersedes = relationship("TimelineEvent", remote_side=[id], lazy="joined")


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    trade_name: Mapped[str | None] = mapped_column(String(255))
    code: Mapped[str | None] = mapped_column(String(32), unique=True)
    legal_name: Mapped[str | None] = mapped_column(String(255))
    entity_type: Mapped[str | None] = mapped_column(String(64))
    tax_id: Mapped[str | None] = mapped_column(String(32), index=True)
    tax_id_type: Mapped[str | None] = mapped_column(String(32))
    tax_id_country: Mapped[str | None] = mapped_column(String(32))
    state_registration: Mapped[str | None] = mapped_column(String(64))
    address_line: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str | None] = mapped_column(String(8))
    country: Mapped[str | None] = mapped_column(String(64))
    postal_code: Mapped[str | None] = mapped_column(String(32))
    country_incorporation: Mapped[str | None] = mapped_column(String(64))
    country_operation: Mapped[str | None] = mapped_column(String(64))
    country_residence: Mapped[str | None] = mapped_column(String(64))
    credit_limit: Mapped[float | None] = mapped_column(Float)
    credit_score: Mapped[int | None] = mapped_column(Integer)
    kyc_status: Mapped[str | None] = mapped_column(String(32), default="pending")
    kyc_notes: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(String(255), index=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), index=True)
    base_currency: Mapped[str | None] = mapped_column(String(8))
    payment_terms: Mapped[str | None] = mapped_column(String(128))
    risk_rating: Mapped[str | None] = mapped_column(String(64))
    sanctions_flag: Mapped[bool | None] = mapped_column(Boolean)
    internal_notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    documents = relationship(
        "KycDocument",
        back_populates="supplier",
        primaryjoin=lambda: and_(
            foreign(KycDocument.owner_id) == Supplier.id,
            KycDocument.owner_type == DocumentOwnerType.supplier,
        ),
        viewonly=True,
    )
    purchase_orders = relationship("PurchaseOrder", back_populates="supplier")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    trade_name: Mapped[str | None] = mapped_column(String(255))
    code: Mapped[str | None] = mapped_column(String(32), unique=True)
    legal_name: Mapped[str | None] = mapped_column(String(255))
    entity_type: Mapped[str | None] = mapped_column(String(64))
    tax_id: Mapped[str | None] = mapped_column(String(32), index=True)
    tax_id_type: Mapped[str | None] = mapped_column(String(32))
    tax_id_country: Mapped[str | None] = mapped_column(String(32))
    state_registration: Mapped[str | None] = mapped_column(String(64))
    address_line: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str | None] = mapped_column(String(8))
    country: Mapped[str | None] = mapped_column(String(64))
    postal_code: Mapped[str | None] = mapped_column(String(32))
    country_incorporation: Mapped[str | None] = mapped_column(String(64))
    country_operation: Mapped[str | None] = mapped_column(String(64))
    country_residence: Mapped[str | None] = mapped_column(String(64))
    credit_limit: Mapped[float | None] = mapped_column(Float)
    credit_score: Mapped[int | None] = mapped_column(Integer)
    kyc_status: Mapped[str | None] = mapped_column(String(32), default="pending")
    kyc_notes: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(String(255), index=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), index=True)
    base_currency: Mapped[str | None] = mapped_column(String(8))
    payment_terms: Mapped[str | None] = mapped_column(String(128))
    risk_rating: Mapped[str | None] = mapped_column(String(64))
    sanctions_flag: Mapped[bool | None] = mapped_column(Boolean)
    internal_notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    documents = relationship(
        "KycDocument",
        back_populates="customer",
        primaryjoin=lambda: and_(
            foreign(KycDocument.owner_id) == Customer.id,
            KycDocument.owner_type == DocumentOwnerType.customer,
        ),
        viewonly=True,
    )
    sales_orders = relationship("SalesOrder", back_populates="customer")


class WarehouseLocation(Base):
    __tablename__ = "warehouse_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    type: Mapped[str | None] = mapped_column(String(64))
    current_stock_mt: Mapped[float | None] = mapped_column(Float)
    capacity_mt: Mapped[float | None] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    po_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id"), nullable=False, index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    product: Mapped[str | None] = mapped_column(String(255))
    total_quantity_mt: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(16), default="MT")
    unit_price: Mapped[float | None] = mapped_column(Float)
    pricing_type: Mapped[PriceType] = mapped_column(
        # Stored as VARCHAR in Supabase schema.
        Enum(PriceType, native_enum=False),
        default=PriceType.AVG,
        nullable=False,
    )
    pricing_period: Mapped[str | None] = mapped_column(String(32))
    lme_premium: Mapped[float] = mapped_column(Float, default=0.0)
    premium: Mapped[float | None] = mapped_column(Float)
    reference_price: Mapped[str | None] = mapped_column(String(64))
    fixing_deadline: Mapped[Date | None] = mapped_column(Date)
    expected_delivery_date: Mapped[Date | None] = mapped_column(Date)
    location: Mapped[str | None] = mapped_column(String(128))
    avg_cost: Mapped[float | None] = mapped_column(Float)
    status: Mapped[OrderStatus] = mapped_column(
        # Stored as VARCHAR in Supabase schema.
        Enum(OrderStatus, native_enum=False), default=OrderStatus.draft, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    supplier = relationship("Supplier", back_populates="purchase_orders")
    exposures = relationship(
        "Exposure",
        back_populates="purchase_order",
        primaryjoin=lambda: and_(
            foreign(Exposure.source_id) == PurchaseOrder.id,
            Exposure.source_type == MarketObjectType.po,
        ),
        viewonly=True,
    )


class SalesOrder(Base):
    __tablename__ = "sales_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    so_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id"), nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    product: Mapped[str | None] = mapped_column(String(255))
    total_quantity_mt: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(16), default="MT")
    unit_price: Mapped[float | None] = mapped_column(Float)
    pricing_type: Mapped[PriceType] = mapped_column(
        # Stored as VARCHAR in Supabase schema.
        Enum(PriceType, native_enum=False),
        default=PriceType.AVG,
        nullable=False,
    )
    pricing_period: Mapped[str | None] = mapped_column(String(32))
    lme_premium: Mapped[float] = mapped_column(Float, default=0.0)
    premium: Mapped[float | None] = mapped_column(Float)
    reference_price: Mapped[str | None] = mapped_column(String(64))
    fixing_deadline: Mapped[Date | None] = mapped_column(Date)
    expected_delivery_date: Mapped[Date | None] = mapped_column(Date)
    location: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[OrderStatus] = mapped_column(
        # Stored as VARCHAR in Supabase schema.
        Enum(OrderStatus, native_enum=False), default=OrderStatus.draft, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    customer = relationship("Customer", back_populates="sales_orders")
    rfqs = relationship("Rfq", back_populates="sales_order")
    hedges = relationship("Hedge", back_populates="sales_order")
    exposures = relationship(
        "Exposure",
        back_populates="sales_order",
        primaryjoin=lambda: and_(
            foreign(Exposure.source_id) == SalesOrder.id,
            Exposure.source_type == MarketObjectType.so,
        ),
        viewonly=True,
    )


class Counterparty(Base):
    __tablename__ = "counterparties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    rfq_channel_type: Mapped[str | None] = mapped_column(String(32), default="BROKER_LME")
    # Stored as VARCHAR in Supabase schema.
    type: Mapped[CounterpartyType] = mapped_column(
        Enum(CounterpartyType, native_enum=False), nullable=False
    )
    trade_name: Mapped[str | None] = mapped_column(String(255))
    legal_name: Mapped[str | None] = mapped_column(String(255))
    entity_type: Mapped[str | None] = mapped_column(String(64))
    contact_name: Mapped[str | None] = mapped_column(String(255))
    contact_email: Mapped[str | None] = mapped_column(String(255), index=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), index=True)
    address_line: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str | None] = mapped_column(String(64))
    country: Mapped[str | None] = mapped_column(String(64))
    postal_code: Mapped[str | None] = mapped_column(String(32))
    country_incorporation: Mapped[str | None] = mapped_column(String(64))
    country_operation: Mapped[str | None] = mapped_column(String(64))
    tax_id: Mapped[str | None] = mapped_column(String(64), index=True)
    tax_id_type: Mapped[str | None] = mapped_column(String(32))
    tax_id_country: Mapped[str | None] = mapped_column(String(32))
    base_currency: Mapped[str | None] = mapped_column(String(8))
    payment_terms: Mapped[str | None] = mapped_column(String(128))
    risk_rating: Mapped[str | None] = mapped_column(String(64))
    sanctions_flag: Mapped[bool | None] = mapped_column(Boolean)
    kyc_status: Mapped[str | None] = mapped_column(String(32))
    kyc_notes: Mapped[str | None] = mapped_column(Text)
    internal_notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    hedges = relationship("Hedge", back_populates="counterparty")
    quotes = relationship("RfqQuote", back_populates="counterparty")

    documents = relationship(
        "KycDocument",
        primaryjoin=lambda: and_(
            foreign(KycDocument.owner_id) == Counterparty.id,
            KycDocument.owner_type == DocumentOwnerType.counterparty,
        ),
        viewonly=True,
    )


class WhatsAppMessage(Base):
    __tablename__ = "whatsapp_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rfq_id: Mapped[int | None] = mapped_column(ForeignKey("rfqs.id"), nullable=True, index=True)
    counterparty_id: Mapped[int | None] = mapped_column(
        ForeignKey("counterparties.id"), nullable=True, index=True
    )
    direction: Mapped[WhatsAppDirection] = mapped_column(Enum(WhatsAppDirection), nullable=False)
    status: Mapped[WhatsAppStatus] = mapped_column(
        Enum(WhatsAppStatus), default=WhatsAppStatus.queued, nullable=False
    )
    message_id: Mapped[str | None] = mapped_column(String(128), index=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    content_text: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    rfq = relationship("Rfq", back_populates="whatsapp_messages")
    counterparty = relationship("Counterparty", viewonly=True)


class Rfq(Base):
    __tablename__ = "rfqs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id"), nullable=False, index=True)
    rfq_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    so_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.id"), nullable=False)
    quantity_mt: Mapped[float] = mapped_column(Float, nullable=False)
    period: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[RfqStatus] = mapped_column(
        # Stored as VARCHAR in Supabase schema.
        Enum(RfqStatus, native_enum=False), default=RfqStatus.pending, nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    awarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    message_text: Mapped[str | None] = mapped_column(Text)
    winner_quote_id: Mapped[int | None] = mapped_column(ForeignKey("rfq_quotes.id"))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    winner_rank: Mapped[int | None] = mapped_column(Integer)
    hedge_id: Mapped[int | None] = mapped_column(ForeignKey("hedges.id"))
    hedge_reference: Mapped[str | None] = mapped_column(String(128))
    trade_specs: Mapped[list[dict] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sales_order = relationship("SalesOrder", back_populates="rfqs")
    counterparty_quotes = relationship(
        "RfqQuote",
        back_populates="rfq",
        foreign_keys="RfqQuote.rfq_id",
        cascade="all, delete-orphan",
    )
    invitations = relationship("RfqInvitation", back_populates="rfq", cascade="all, delete-orphan")
    winner_quote = relationship("RfqQuote", foreign_keys=[winner_quote_id], viewonly=True)
    decided_by_user = relationship("User", foreign_keys=[decided_by], viewonly=True)
    hedge = relationship("Hedge", foreign_keys=[hedge_id], viewonly=True)
    whatsapp_messages = relationship(
        "WhatsAppMessage", back_populates="rfq", cascade="all, delete-orphan"
    )
    send_attempts = relationship(
        "RfqSendAttempt", back_populates="rfq", cascade="all, delete-orphan"
    )

    @property
    def institutional_state(self) -> RfqInstitutionalState:
        """Deterministic institutional RFQ state derived from persisted fields.

        This is a compatibility layer while the RFQ state machine is normalized.
        It does not write anything; it only maps current DB state to the
        institutional vocabulary.
        """

        status = self.status
        if isinstance(status, RfqStatus):
            status_value = status.value
        else:
            status_value = str(status)
        status_value = status_value.split(".")[-1].lower()

        if status_value == "expired":
            return RfqInstitutionalState.ARCHIVED

        if status_value in {"awarded", "failed"}:
            return RfqInstitutionalState.CLOSED

        if status_value == "quoted":
            return RfqInstitutionalState.PARTIAL_RESPONSE

        quotes = list(getattr(self, "counterparty_quotes", None) or [])
        if quotes:
            return RfqInstitutionalState.PARTIAL_RESPONSE

        if status_value == "sent":
            attempts = list(getattr(self, "send_attempts", None) or [])
            has_pending_attempt = False
            for a in attempts:
                av = getattr(getattr(a, "status", None), "value", None) or str(
                    getattr(a, "status", "")
                )
                av = av.split(".")[-1].lower()
                if av in {"queued", "sending"}:
                    has_pending_attempt = True
                    break

            if not has_pending_attempt:
                msgs = list(getattr(self, "whatsapp_messages", None) or [])
                for m in msgs:
                    mv = getattr(getattr(m, "status", None), "value", None) or str(
                        getattr(m, "status", "")
                    )
                    mv = mv.split(".")[-1].lower()
                    if mv in {"queued"}:
                        has_pending_attempt = True
                        break

            return (
                RfqInstitutionalState.SENDING if has_pending_attempt else RfqInstitutionalState.SENT
            )

        return RfqInstitutionalState.CREATED


class Contract(Base):
    __tablename__ = "contracts"

    contract_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # Human-friendly monthly sequence for UI/search (keeps UUID primary key stable).
    contract_number: Mapped[str | None] = mapped_column(String(50), unique=True, index=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id"), nullable=False, index=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id"), nullable=False, index=True)
    counterparty_id: Mapped[int | None] = mapped_column(
        ForeignKey("counterparties.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default=ContractStatus.active.value, index=True)
    trade_index: Mapped[int | None] = mapped_column(Integer)
    quote_group_id: Mapped[str | None] = mapped_column(String(64), index=True)
    trade_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    settlement_date: Mapped[Date | None] = mapped_column(Date)
    settlement_meta: Mapped[dict | None] = mapped_column(JSON)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    deal = relationship("Deal", viewonly=True)
    rfq = relationship("Rfq", viewonly=True)
    counterparty = relationship("Counterparty", viewonly=True)
    exposure_links = relationship(
        "ContractExposure", back_populates="contract", cascade="all, delete-orphan"
    )

    @validates("status")
    def _validate_status(self, _key, value: str | ContractStatus | None):
        if value is None:
            return ContractStatus.active.value
        if isinstance(value, ContractStatus):
            value = value.value
        allowed = {s.value for s in ContractStatus}
        if value not in allowed:
            raise ValueError(f"Invalid contract status: {value}")
        return value

    def _validate_invariants(self) -> None:
        if not isinstance(self.trade_snapshot, dict) or not self.trade_snapshot:
            raise ValueError("Contract.trade_snapshot must be a non-empty dict")

        if self.trade_index is not None and int(self.trade_index) < 0:
            raise ValueError("Contract.trade_index must be >= 0")

        if self.status == ContractStatus.settled.value and self.settlement_date is None:
            raise ValueError("Contract.settlement_date is required when status=settled")


@event.listens_for(Contract, "before_insert")
def _contract_before_insert(_mapper, _connection, target: Contract):
    target._validate_invariants()


@event.listens_for(Contract, "before_update")
def _contract_before_update(_mapper, _connection, target: Contract):
    target._validate_invariants()


class RfqQuote(Base):
    __tablename__ = "rfq_quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id"), nullable=False)
    counterparty_id: Mapped[int | None] = mapped_column(ForeignKey("counterparties.id"))
    counterparty_name: Mapped[str | None] = mapped_column(String(255))
    quote_price: Mapped[float] = mapped_column(Float, nullable=False)
    price_type: Mapped[str | None] = mapped_column(String(128))
    volume_mt: Mapped[float | None] = mapped_column(Float)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    channel: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="quoted")
    quote_group_id: Mapped[str | None] = mapped_column(String(64), index=True)
    leg_side: Mapped[str | None] = mapped_column(String(8))  # buy | sell
    quoted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    rfq = relationship("Rfq", back_populates="counterparty_quotes", foreign_keys=[rfq_id])
    counterparty = relationship("Counterparty", back_populates="quotes")


class RfqInvitation(Base):
    __tablename__ = "rfq_invitations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id"), nullable=False)
    counterparty_id: Mapped[int] = mapped_column(ForeignKey("counterparties.id"), nullable=False)
    counterparty_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="sent")
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    message_text: Mapped[str | None] = mapped_column(Text)

    rfq = relationship("Rfq", back_populates="invitations")
    counterparty = relationship("Counterparty")


class RfqSendAttempt(Base):
    """
    Tracks each attempt to send an RFQ to a counterparty.
    Supports retry tracking, idempotency, and multi-channel delivery.
    """

    __tablename__ = "rfq_send_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)  # email, api, whatsapp
    status: Mapped[SendStatus] = mapped_column(
        Enum(SendStatus), default=SendStatus.queued, nullable=False
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(128))
    error: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str | None] = mapped_column(
        Text
    )  # JSON string with channel-specific metadata
    idempotency_key: Mapped[str | None] = mapped_column(String(128), index=True)
    retry_of_attempt_id: Mapped[int | None] = mapped_column(
        Integer
    )  # Points to parent attempt if this is a retry
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    rfq = relationship("Rfq", back_populates="send_attempts")

    @property
    def metadata_dict(self) -> dict:
        """Parse metadata_json to dict for API responses."""
        import json

        if self.metadata_json:
            try:
                return json.loads(self.metadata_json)
            except json.JSONDecodeError:
                return {}
        return {}


class Hedge(Base):
    __tablename__ = "hedges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    so_id: Mapped[int | None] = mapped_column(ForeignKey("sales_orders.id"))
    counterparty_id: Mapped[int] = mapped_column(ForeignKey("counterparties.id"), nullable=False)
    quantity_mt: Mapped[float] = mapped_column(Float, nullable=False)
    contract_price: Mapped[float] = mapped_column(Float, nullable=False)
    current_market_price: Mapped[float | None] = mapped_column(Float)
    mtm_value: Mapped[float | None] = mapped_column(Float)
    period: Mapped[str] = mapped_column(String(20), nullable=False)
    instrument: Mapped[str | None] = mapped_column(String(128))
    maturity_date: Mapped[Date | None] = mapped_column(Date)
    reference_code: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[HedgeStatus] = mapped_column(
        Enum(HedgeStatus), default=HedgeStatus.active, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sales_order = relationship("SalesOrder", back_populates="hedges")
    counterparty = relationship("Counterparty", back_populates="hedges")
    exposure_links = relationship(
        "HedgeExposure", back_populates="hedge", cascade="all, delete-orphan"
    )


class KycDocument(Base):
    __tablename__ = "kyc_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_type: Mapped[DocumentOwnerType] = mapped_column(Enum(DocumentOwnerType), nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(128))
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSON)

    customer = relationship(
        "Customer",
        back_populates="documents",
        primaryjoin=lambda: and_(
            foreign(KycDocument.owner_id) == Customer.id,
            KycDocument.owner_type == DocumentOwnerType.customer,
        ),
        viewonly=True,
    )
    supplier = relationship(
        "Supplier",
        back_populates="documents",
        primaryjoin=lambda: and_(
            foreign(KycDocument.owner_id) == Supplier.id,
            KycDocument.owner_type == DocumentOwnerType.supplier,
        ),
        viewonly=True,
    )

    counterparty = relationship(
        "Counterparty",
        primaryjoin=lambda: and_(
            foreign(KycDocument.owner_id) == Counterparty.id,
            KycDocument.owner_type == DocumentOwnerType.counterparty,
        ),
        viewonly=True,
    )


class CreditCheck(Base):
    __tablename__ = "credit_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_type: Mapped[DocumentOwnerType] = mapped_column(Enum(DocumentOwnerType), nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    bureau: Mapped[str] = mapped_column(String(128))
    score: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(64))
    raw_response: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KycCheck(Base):
    __tablename__ = "kyc_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_type: Mapped[DocumentOwnerType] = mapped_column(Enum(DocumentOwnerType), nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    check_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    score: Mapped[int | None] = mapped_column(Integer)
    details_json: Mapped[dict | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MtmRecord(Base):
    __tablename__ = "mtm_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    as_of_date: Mapped[Date] = mapped_column(Date, nullable=False)
    object_type: Mapped[MarketObjectType] = mapped_column(Enum(MarketObjectType), nullable=False)
    object_id: Mapped[int | None] = mapped_column(Integer)
    forward_price: Mapped[float | None] = mapped_column(Float)
    fx_rate: Mapped[float | None] = mapped_column(Float)
    mtm_value: Mapped[float] = mapped_column(Float, nullable=False)
    methodology: Mapped[str | None] = mapped_column(String(128))
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MarketPrice(Base):
    __tablename__ = "market_prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_month: Mapped[str | None] = mapped_column(String(16))
    price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    fx: Mapped[bool] = mapped_column(Boolean, default=False)


class Exposure(Base):
    __tablename__ = "exposures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[MarketObjectType] = mapped_column(Enum(MarketObjectType), nullable=False)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    exposure_type: Mapped[ExposureType] = mapped_column(Enum(ExposureType), nullable=False)
    quantity_mt: Mapped[float] = mapped_column(Float, nullable=False)
    product: Mapped[str | None] = mapped_column(String(255))
    payment_date: Mapped[Date | None] = mapped_column(Date)
    delivery_date: Mapped[Date | None] = mapped_column(Date)
    sale_date: Mapped[Date | None] = mapped_column(Date)
    status: Mapped[ExposureStatus] = mapped_column(
        Enum(ExposureStatus), default=ExposureStatus.open, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    purchase_order = relationship(
        "PurchaseOrder",
        back_populates="exposures",
        primaryjoin=lambda: and_(
            foreign(Exposure.source_id) == PurchaseOrder.id,
            Exposure.source_type == MarketObjectType.po,
        ),
        viewonly=True,
    )
    sales_order = relationship(
        "SalesOrder",
        back_populates="exposures",
        primaryjoin=lambda: and_(
            foreign(Exposure.source_id) == SalesOrder.id,
            Exposure.source_type == MarketObjectType.so,
        ),
        viewonly=True,
    )
    tasks = relationship("HedgeTask", back_populates="exposure", cascade="all, delete-orphan")
    hedge_links = relationship(
        "HedgeExposure", back_populates="exposure", cascade="all, delete-orphan"
    )
    contract_links = relationship(
        "ContractExposure", back_populates="exposure", cascade="all, delete-orphan"
    )

    treasury_decisions = relationship(
        "TreasuryDecision",
        back_populates="exposure",
        cascade="all, delete-orphan",
        order_by="TreasuryDecision.id.desc()",
    )


class TreasuryDecision(Base):
    __tablename__ = "treasury_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    exposure_id: Mapped[int] = mapped_column(ForeignKey("exposures.id"), nullable=False)
    decision_kind: Mapped[TreasuryDecisionKind] = mapped_column(
        Enum(TreasuryDecisionKind, native_enum=False),
        nullable=False,
        index=True,
    )

    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text)

    # Captures non-blocking KYC evaluation output at decision time.
    kyc_gate_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    exposure = relationship("Exposure", back_populates="treasury_decisions")
    created_by_user = relationship("User", lazy="joined")
    kyc_override = relationship(
        "TreasuryKycOverride",
        back_populates="decision",
        uselist=False,
        cascade="all, delete-orphan",
    )


class TreasuryKycOverride(Base):
    __tablename__ = "treasury_kyc_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    decision_id: Mapped[int] = mapped_column(
        ForeignKey("treasury_decisions.id"),
        nullable=False,
        unique=True,
        index=True,
    )

    reason: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    decision = relationship("TreasuryDecision", back_populates="kyc_override")
    created_by_user = relationship("User", lazy="joined")


class HedgeTask(Base):
    __tablename__ = "hedge_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exposure_id: Mapped[int] = mapped_column(ForeignKey("exposures.id"), nullable=False)
    status: Mapped[HedgeTaskStatus] = mapped_column(
        Enum(HedgeTaskStatus), default=HedgeTaskStatus.pending, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    exposure = relationship("Exposure", back_populates="tasks")


class HedgeExposure(Base):
    __tablename__ = "hedge_exposures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hedge_id: Mapped[int] = mapped_column(ForeignKey("hedges.id"), nullable=False)
    exposure_id: Mapped[int] = mapped_column(ForeignKey("exposures.id"), nullable=False)
    quantity_mt: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    hedge = relationship("Hedge", back_populates="exposure_links")
    exposure = relationship("Exposure", back_populates="hedge_links")


class ContractExposure(Base):
    __tablename__ = "contract_exposures"
    __table_args__ = (UniqueConstraint("contract_id", "exposure_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_id: Mapped[str] = mapped_column(
        ForeignKey("contracts.contract_id"), nullable=False, index=True
    )
    exposure_id: Mapped[int] = mapped_column(
        ForeignKey("exposures.id"), nullable=False, index=True
    )
    quantity_mt: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    contract = relationship("Contract", back_populates="exposure_links")
    exposure = relationship("Exposure", back_populates="contract_links")


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deal_uuid: Mapped[str] = mapped_column(
        String(36), unique=True, default=lambda: str(uuid.uuid4()), index=True
    )
    commodity: Mapped[str | None] = mapped_column(String(255), index=True)
    # Human-friendly label for users (free text). Used for quick search and UI display.
    reference_name: Mapped[str | None] = mapped_column(String(255), index=True)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    status: Mapped[DealStatus] = mapped_column(
        # Stored as VARCHAR in Supabase schema.
        Enum(DealStatus, native_enum=False), default=DealStatus.open, nullable=False, index=True
    )
    lifecycle_status: Mapped[DealLifecycleStatus] = mapped_column(
        Enum(DealLifecycleStatus),
        default=DealLifecycleStatus.open,
        nullable=False,
        index=True,
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    links = relationship("DealLink", back_populates="deal", cascade="all, delete-orphan")
    pnl_snapshots = relationship(
        "DealPNLSnapshot", back_populates="deal", cascade="all, delete-orphan"
    )


class DealLink(Base):
    __tablename__ = "deal_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id"), nullable=False, index=True)
    # Stored as VARCHAR in Supabase schema.
    entity_type: Mapped[DealEntityType] = mapped_column(
        Enum(DealEntityType, native_enum=False), nullable=False
    )
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # Stored as VARCHAR in Supabase schema.
    direction: Mapped[DealDirection] = mapped_column(
        Enum(DealDirection, native_enum=False), nullable=False
    )
    quantity_mt: Mapped[float | None] = mapped_column(Float)
    allocation_type: Mapped[DealAllocationType] = mapped_column(
        # Stored as VARCHAR in Supabase schema.
        Enum(DealAllocationType, native_enum=False),
        default=DealAllocationType.auto,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    deal = relationship("Deal", back_populates="links")


class DealPNLSnapshot(Base):
    __tablename__ = "deal_pnl_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id"), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    physical_revenue: Mapped[float] = mapped_column(Float, default=0.0)
    physical_cost: Mapped[float] = mapped_column(Float, default=0.0)
    hedge_pnl_realized: Mapped[float] = mapped_column(Float, default=0.0)
    hedge_pnl_mtm: Mapped[float] = mapped_column(Float, default=0.0)
    net_pnl: Mapped[float] = mapped_column(Float, default=0.0)

    deal = relationship("Deal", back_populates="pnl_snapshots")


class PnlSnapshotRun(Base):
    __tablename__ = "pnl_snapshot_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    as_of_date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    scope_filters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    inputs_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    requested_by = relationship("User", foreign_keys=[requested_by_user_id], lazy="joined")
    contract_snapshots = relationship(
        "PnlContractSnapshot",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class PnlContractSnapshot(Base):
    __tablename__ = "pnl_contract_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "contract_id",
            "as_of_date",
            "currency",
            name="uq_pnl_contract_snapshots_contract_date_currency",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("pnl_snapshot_runs.id"),
        nullable=False,
        index=True,
    )
    as_of_date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    contract_id: Mapped[str] = mapped_column(
        ForeignKey("contracts.contract_id"),
        nullable=False,
        index=True,
    )
    deal_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, server_default="USD")

    unrealized_pnl_usd: Mapped[float] = mapped_column(Float, nullable=False)
    methodology: Mapped[str | None] = mapped_column(String(128))
    data_quality_flags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    inputs_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run = relationship("PnlSnapshotRun", back_populates="contract_snapshots")


class PnlContractRealized(Base):
    __tablename__ = "pnl_contract_realized"
    __table_args__ = (
        UniqueConstraint(
            "contract_id",
            "settlement_date",
            "currency",
            name="uq_pnl_contract_realized_contract_settlement_currency",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_id: Mapped[str] = mapped_column(
        ForeignKey("contracts.contract_id"),
        nullable=False,
        index=True,
    )
    settlement_date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    deal_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, server_default="USD")

    realized_pnl_usd: Mapped[float] = mapped_column(Float, nullable=False)
    methodology: Mapped[str | None] = mapped_column(String(128))
    inputs_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_hint: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FxPolicyMap(Base):
    __tablename__ = "fx_policy_map"
    __table_args__ = (UniqueConstraint("policy_key", name="uq_fx_policy_map_policy_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Canonical key, e.g. "BRL:^USDBRL@barchart_excel_usdbrl".
    policy_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    reporting_currency: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    fx_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    fx_source: Mapped[str] = mapped_column(String(64), nullable=False)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    created_by = relationship("User", foreign_keys=[created_by_user_id], lazy="joined")


class FinancePipelineRun(Base):
    __tablename__ = "finance_pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    pipeline_version: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    as_of_date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    scope_filters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, server_default="materialize")
    emit_exports: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")

    inputs_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    # Forward-only status machine: queued -> running -> done|failed
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="queued", index=True
    )

    requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    requested_by = relationship("User", foreign_keys=[requested_by_user_id], lazy="joined")
    steps = relationship(
        "FinancePipelineStep",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class FinancePipelineStep(Base):
    __tablename__ = "finance_pipeline_steps"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "step_name",
            name="uq_finance_pipeline_steps_run_step",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    run_id: Mapped[int] = mapped_column(
        ForeignKey("finance_pipeline_runs.id"),
        nullable=False,
        index=True,
    )
    step_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Forward-only status machine: pending -> running -> done|failed|skipped
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="pending", index=True
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional per-step output references (e.g., P&L snapshot run ids/hashes).
    artifacts: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    run = relationship("FinancePipelineRun", back_populates="steps")
