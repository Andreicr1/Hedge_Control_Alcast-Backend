# Timeline v2 — Phase 2 (Execution) — Backend Ticket Pack

**Status:** Planning-only tickets. **No implementation** in this document.

This ticket pack is derived from the approved Phase 1 crosswalk and the locked decisions:
- KYC gate blocked events anchor on Sales Order (SO) (subject_type `so`, subject_id `so_id`).
- Default visibility for new v2 system events is `finance`.
- RFQ award flows emit a single canonical `RFQ_AWARDED` with `award_source` in payload.

**Institutional correction (locked):** KYC applies to Customers / Sales Orders (SO), not to hedge counterparties.

---

## Shared Implementation Notes (Applies to all tickets)

### Where Timeline rows are written
- Timeline events are stored in `timeline_events` (already migrated).
- Current public write endpoint `POST /timeline/events` is **v1-only** (validates `event_type` against v1 allowlist).
- Phase 2 emitters therefore must write Timeline rows via an internal service (not via `POST /timeline/events`).

### Correlation ID
- Use a single UUID per request that causes emissions.
- Suggested rule:
  - If `X-Request-ID` header exists and is a valid UUID, reuse it as `correlation_id`.
  - Else generate a UUID4.
- All events emitted from one request share the same `correlation_id`.

### Idempotency
- Mandatory for all v2 system emitters.
- Deterministic keys as specified per ticket.
- Enforced uniqueness: `(event_type, idempotency_key)`.

### Visibility
- Default `visibility = "finance"` for all new v2 system events.

### Guardrails
- Emit only after successful persistence (`db.commit()` succeeded), OR for explicit gate blocks (no domain state mutation).
- No retries altering domain state; Timeline events are append-only.

### Tests
- Add/extend tests in `backend/tests/` to assert:
  - event exists exactly once under idempotent replays
  - correlation_id is stable within a request
  - correct subject_type/subject_id
  - correct visibility

---

## Ticket 1 — RFQ Core Emitters

**Goal:** Emit v2 RFQ lifecycle events from RFQ write paths.

**Emitter locations:**
- `backend/app/api/routes/rfqs.py`
  - `create_rfq`
  - `add_quote`
  - `award_quote`
  - `cancel_rfq`

### Events

1. `RFQ_CREATED`
- When: after `create_rfq` commit
- Subject: `rfq` / `rfq.id`
- Visibility: `finance`
- Idempotency: `rfq:{rfq.id}:created`
- Payload:
  - `rfq_id`, `rfq_number`, `so_id`, optional `deal_id`, optional `invited_counterparty_ids`

1. `KYC_GATE_BLOCKED`
- When: in `create_rfq` immediately before raising 409
- Subject: `so` / `so_id`
- Visibility: `finance`
- Idempotency: `kyc_gate:block:rfq_create:{so_id}:{rfq_number}`
- Payload:
  - `blocked_action: "rfq_create"`, `so_id`, `rfq_number`, `customer_id`, optional `customer_kyc_status`, `reason_code`, `details`

1. `RFQ_QUOTE_CREATED`
- When: after `add_quote` commit
- Subject: `rfq` / `rfq.id`
- Visibility: `finance`
- Idempotency: `rfq_quote:{quote.id}:created`
- Payload:
  - `rfq_id`, `quote_id`, optional `counterparty_id`, optional `counterparty_name`, `quote_price`, optional `price_type`, optional `volume_mt`, optional `channel`, optional `status`

1. `RFQ_AWARDED`
- When: after `award_quote` commit
- Subject: `rfq` / `rfq.id`
- Visibility: `finance`
- Idempotency: `rfq:{rfq.id}:awarded`
- Payload:
  - `rfq_id`, `quote_id`, `decided_by_user_id`, `decided_at`, optional `winner_rank`, optional `hedge_id`, optional `decision_reason`, `award_source: "award_quote"`

1. `KYC_GATE_BLOCKED` (award)
- When: in `award_quote` immediately before raising 409
- Subject: `so` / `rfq.so_id`
- Visibility: `finance`
- Idempotency: `kyc_gate:block:contract_create:{so_id}:{rfq_id}:{quote_id}`
- Payload:
  - `blocked_action: "contract_create"`, `so_id`, `rfq_id`, `quote_id`, `customer_id`, optional `customer_kyc_status`, `reason_code`, `details`

1. `RFQ_CANCELLED`
- When: after `cancel_rfq` commit
- Subject: `rfq` / `rfq.id`
- Visibility: `finance`
- Idempotency: `rfq:{rfq.id}:cancelled`
- Payload:
  - `rfq_id`, `reason`, `decided_by_user_id`, `decided_at`

### Acceptance Criteria
- Each event is emitted exactly once per action (idempotent replays return the existing Timeline row).
- KYC gate blocked events attach to the Sales Order (SO) subject as locked.
- Award emits canonical `RFQ_AWARDED` with `award_source`.

---

## Ticket 2 — RFQ Send Emitters

**Goal:** Emit v2 RFQ send events from RFQ send attempt write paths.

**Emitter locations:**
- `backend/app/api/routes/rfq_send.py`
  - `send_rfq`
  - `update_send_attempt_status`
  - `confirm_rfq_deal`

### Events

1. `RFQ_SEND_REQUESTED`
- When: after `send_rfq` commit
- Subject: `rfq` / `rfq.id`
- Visibility: `finance`
- Idempotency: `rfq:{rfq.id}:send_requested:{payload.idempotency_key or "none"}`
- Payload:
  - `rfq_id`, `channel`, `attempt_ids`, `message_length`

1. `RFQ_SEND_ATTEMPT_CREATED`
- When: after `send_rfq` commit, per created attempt
- Subject: `rfq` / `rfq.id`
- Visibility: `finance`
- Idempotency: `rfq_send_attempt:{attempt.id}:created`
- Payload:
  - `rfq_id`, `attempt_id`, `channel`, `status`, optional `provider_message_id`, optional `retry_of_attempt_id`, optional `idempotency_key`

1. `RFQ_SEND_ATTEMPT_STATUS_UPDATED`
- When: after `update_send_attempt_status` commit
- Subject: `rfq` / `rfq.id`
- Visibility: `finance`
- Idempotency: `rfq_send_attempt:{attempt.id}:status:{payload.status}`
- Payload:
  - `rfq_id`, `attempt_id`, `status`, optional `provider_message_id`, optional `error`

1. `RFQ_AWARDED` (canonical award flow)
- When: after `confirm_rfq_deal` commit
- Subject: `rfq` / `rfq.id`
- Visibility: `finance`
- Idempotency: `rfq:{rfq.id}:awarded`
- Payload:
  - `rfq_id`, `quote_id`, `awarded_at`, `award_source: "confirm_rfq_deal"`

### Acceptance Criteria
- No duplication under retries (idempotency enforced).
- `confirm_rfq_deal` emits canonical `RFQ_AWARDED` (not a separate taxonomy).

---

## Ticket 3 — Contract Created Emitter (v1-compatible)

**Goal:** Emit `CONTRACT_CREATED` when contracts are created during RFQ award.

**Emitter location:**
- `backend/app/api/routes/rfqs.py:award_quote` (after contract insert + commit; per created contract)

### Event

`CONTRACT_CREATED`
- When: after commit
- Subject: `rfq` / `rfq.id`
- Visibility: `finance`
- Idempotency: `contract:{contract.contract_id}:created`
- Payload:
  - `contract_id`, `rfq_id`, `deal_id`, optional `counterparty_id`, optional `settlement_date`, optional `trade_index`, optional `quote_group_id`

### Acceptance Criteria
- One event per created contract.
- Uses RFQ subject because Timeline `subject_id` is integer and contract_id is UUID string.

---

## Ticket 4 — Customer / KYC Emitters

**Goal:** Emit v2 system events for Customer KYC actions (Sales-side).

**Emitter locations:**
- `backend/app/api/routes/customers.py`
  - `upload_customer_document`
  - `run_customer_credit_check`

### Events

1. `KYC_DOCUMENT_UPLOADED`
- Subject: `customer` / `customer_id`
- Visibility: `finance`
- Idempotency: `kyc_document:{doc.id}:uploaded`
- Payload: `customer_id`, `document_id`, `filename`, `content_type`, optional `uploaded_by_email`

1. `KYC_STATUS_CHANGED`
- Subject: `customer` / `customer_id`
- Visibility: `finance`
- Idempotency: `customer:{customer_id}:kyc_status:{payload.kyc_status}`
- Payload: `customer_id`, `kyc_status`, optional `reason_code`, optional `details`

### Acceptance Criteria
- One event per created row / persisted status change.
- No Timeline event emitted on purely read-only endpoints.

---

## Ticket 4A — Counterparty Controls (Non-KYC)

**Goal:** Emit v2 system events for hedge counterparty controls/due-diligence signals (explicitly not modeled as “KYC”).

**Emitter locations:**
- `backend/app/api/routes/counterparties.py`
  - `create_counterparty`
  - `upload_counterparty_document`
  - `run_counterparty_kyc_check`

### Events

1. `COUNTERPARTY_CREATED`
- Subject: `counterparty` / `cp.id`
- Visibility: `finance`
- Idempotency: `counterparty:{cp.id}:created`
- Payload: `counterparty_id`, `name`, optional `type`

1. `COUNTERPARTY_DOCUMENT_UPLOADED`
- Subject: `counterparty` / `counterparty_id`
- Visibility: `finance`
- Idempotency: `counterparty_document:{doc.id}:uploaded`
- Payload: `counterparty_id`, `document_id`, `filename`, `content_type`, optional `uploaded_by_email`

1. `COUNTERPARTY_CHECK_CREATED`
- Subject: `counterparty` / `counterparty_id`
- Visibility: `finance`
- Idempotency: `counterparty_check:{check.id}:created`
- Payload: `counterparty_id`, `check_id`, `check_type`, `status`, optional `score`, `expires_at`

### Acceptance Criteria
- One event per created row.
- No KYC_* event types are emitted for hedge counterparties.

---

## Ticket 5 — Inbox Decision Emitter

**Goal:** Emit v2 system events for audit-only Inbox decisions.

**Emitter location:**
- `backend/app/api/routes/inbox.py:inbox_create_decision` (after audit log insert + commit)

### Event

`INBOX_DECISION_RECORDED`
- Subject: `exposure` / `exposure_id`
- Visibility: `finance`
- Idempotency: `inbox_decision:{log.id}:recorded`
- Payload: `exposure_id`, `decision`, `justification`, `audit_log_id`

### Acceptance Criteria
- One event per recorded decision.
- Timeline emission does not mutate Exposure or create RFQs/Contracts.

---

## Optional Ticket 6 — v2 Taxonomy Documentation (Non-code)

**Goal:** Provide a single canonical list of v2 event types and payload shapes for downstream consumers.

**Deliverable:** an internal markdown doc enumerating:
- event_type list
- payload schemas
- subject rules
- visibility defaults
- idempotency rules

(No schema or code changes.)
