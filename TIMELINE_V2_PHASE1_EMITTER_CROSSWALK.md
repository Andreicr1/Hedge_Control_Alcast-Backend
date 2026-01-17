# Timeline v2 — Phase 1 (Planning Only) — System Emitters Crosswalk

**Status:** Planning-only. **No code / no schema changes** in this phase.

## Scope (Frozen)

- **Included:** system-generated events emitted from **existing write paths** only (RFQ, Customer/KYC, Counterparty controls, Inbox decisions, Contract creation via RFQ award, RFQ send attempts).
- **Excluded:** human annotations/comments/@mentions (explicitly deferred to a later phase).
- **Semantics:** append-only Timeline events; Timeline is **never** an execution surface.

**Institutional correction (locked):** “KYC” in this system applies to the **Sales side** (Customer / Sales Order (SO)), not to hedge counterparties (banks/brokers). Hedge counterparties may be subject to other controls (credit limits, counterparty risk, CSA, etc.), but those are not “KYC” in this sense.

## Existing Timeline Envelope (Current Backend)

Timeline events are stored in `timeline_events` with the following key fields (already present):

- `event_type` (string, 64)
- `occurred_at` (datetime)
- `subject_type` (string, 32)
- `subject_id` (int)
- `correlation_id` (string, 36)
- `idempotency_key` (string, 128, nullable; unique with `event_type`)
- `visibility` (`all` | `finance`)
- `payload` (json)
- `meta` (json)

Important behavior today:

- `POST /timeline/events` validates `event_type` against **Timeline v1** allowlist.
- `GET /timeline` and `GET /timeline/recent` return whatever is stored.

## Canonical v2 Event Naming (Proposal)

- Keep `SCREAMING_SNAKE_CASE` to match v1.
- New v2 event types are introduced **without changing** Timeline v1’s allowlist.
  - v2 events will be emitted internally from backend write paths (Phase 2) rather than relying on `POST /timeline/events`.

## Correlation, Idempotency, Visibility (Rules)

**Correlation (`correlation_id`)**

- One UUID per inbound request that causes Timeline emissions.
- All events emitted from the same request share the same `correlation_id`.

**Idempotency (`idempotency_key`)**

- **Mandatory** for all v2 system emitters.
- Deterministic and derived from stable domain identifiers, so retries do not duplicate events.
- Uniqueness is enforced by `(event_type, idempotency_key)`.

**Visibility (`visibility`)**

- Default to `finance` for Financeiro-only operational signals.
- Use `all` only when it is safe/intentional for non-finance roles to see the event.

**Guardrail:** Timeline emission must not change domain state beyond writing the Timeline row itself.

---

## 1) Timeline v2 Emitter Matrix (Authoritative)

Notes:

- “Emitter location” is the exact write path to hook in Phase 2.
- Payloads are **minimal and stable**; do not embed large snapshots.
- Subject selection is based on existing UI usage of `TimelinePanel`:
  - RFQ view uses `subject_type="rfq"` / `subject_id=<rfq.id>`.
  - Counterparty view uses `subject_type="counterparty"` / `subject_id=<counterparty.id>`.

## A. RFQ (Core)

| Action | Emitter location (write path) | event_type (v2) | subject_type / subject_id | Payload (minimal) | correlation_id | idempotency_key (deterministic) | visibility |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RFQ created successfully | `backend/app/api/routes/rfqs.py:create_rfq` (after commit) | `RFQ_CREATED` | `rfq` / `rfq.id` | `{ rfq_id, rfq_number, so_id, deal_id?, invited_counterparty_ids? }` | request UUID | `rfq:{rfq.id}:created` | `finance` |
| RFQ create blocked by KYC gate | `backend/app/api/routes/rfqs.py:create_rfq` (before raising 409) | `KYC_GATE_BLOCKED` | `so` / `so_id` | `{ blocked_action:"rfq_create", so_id, rfq_number, customer_id, customer_kyc_status?, reason_code, details }` | request UUID | `kyc_gate:block:rfq_create:{so_id}:{rfq_number}` | `finance` |
| Quote recorded on RFQ | `backend/app/api/routes/rfqs.py:add_quote` (after commit) | `RFQ_QUOTE_CREATED` | `rfq` / `rfq.id` | `{ rfq_id, quote_id, counterparty_id?, counterparty_name?, quote_price, price_type?, volume_mt?, channel?, status? }` | request UUID | `rfq_quote:{quote.id}:created` | `finance` |
| RFQ awarded (decision recorded) | `backend/app/api/routes/rfqs.py:award_quote` (after commit) | `RFQ_AWARDED` | `rfq` / `rfq.id` | `{ rfq_id, quote_id, decided_by_user_id, decided_at, winner_rank?, hedge_id?, decision_reason? }` | request UUID | `rfq:{rfq.id}:awarded` | `finance` |
| RFQ award blocked by KYC gate | `backend/app/api/routes/rfqs.py:award_quote` (before raising 409) | `KYC_GATE_BLOCKED` | `so` / `rfq.so_id` | `{ blocked_action:"contract_create", so_id, rfq_id, quote_id, customer_id, customer_kyc_status?, reason_code, details }` | request UUID | `kyc_gate:block:contract_create:{so_id}:{rfq_id}:{quote_id}` | `finance` |
| RFQ cancelled / marked failed | `backend/app/api/routes/rfqs.py:cancel_rfq` (after commit) | `RFQ_CANCELLED` | `rfq` / `rfq.id` | `{ rfq_id, reason, decided_by_user_id, decided_at }` | request UUID | `rfq:{rfq.id}:cancelled` | `finance` |

**Note (KYC gate blocked subject):** locked to `subject_type="so" subject_id=<so_id>`.

## B. RFQ Send (Attempts + Delivery)

| Action | Emitter location (write path) | event_type (v2) | subject_type / subject_id | Payload (minimal) | correlation_id | idempotency_key (deterministic) | visibility |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Send requested (creates 1+ attempts) | `backend/app/api/routes/rfq_send.py:send_rfq` (after commit) | `RFQ_SEND_REQUESTED` | `rfq` / `rfq.id` | `{ rfq_id, channel, attempt_ids, message_length }` | request UUID | `rfq:{rfq.id}:send_requested:{payload.idempotency_key or "none"}` | `finance` |
| Send attempt created | `backend/app/api/routes/rfq_send.py:send_rfq` (after commit; per attempt) | `RFQ_SEND_ATTEMPT_CREATED` | `rfq` / `rfq.id` | `{ rfq_id, attempt_id, channel, status, provider_message_id?, retry_of_attempt_id?, idempotency_key? }` | request UUID | `rfq_send_attempt:{attempt.id}:created` | `finance` |
| Send attempt status updated | `backend/app/api/routes/rfq_send.py:update_send_attempt_status` (after commit) | `RFQ_SEND_ATTEMPT_STATUS_UPDATED` | `rfq` / `rfq.id` | `{ rfq_id, attempt_id, status, provider_message_id?, error? }` | request UUID | `rfq_send_attempt:{attempt.id}:status:{payload.status}` | `finance` |
| RFQ deal confirmed (award flow) | `backend/app/api/routes/rfq_send.py:confirm_rfq_deal` (after commit) | `RFQ_AWARDED` | `rfq` / `rfq.id` | `{ rfq_id, quote_id, awarded_at, award_source:"confirm_rfq_deal" }` | request UUID | `rfq:{rfq.id}:awarded` | `finance` |

**Guardrail:** do not emit “retry”/“resend” events that imply workflow. Only reflect persisted writes (attempt created, status updated).

## C. Contract Creation (via RFQ Award)

Constraint: `Contract.contract_id` is a UUID string primary key; Timeline subjects require integer `subject_id`. Therefore, Contract events must attach to an integer subject (RFQ, Deal, Counterparty).

Recommendation: attach to **RFQ** so the existing RFQ TimelinePanel surfaces contract creation immediately.

| Action | Emitter location (write path) | event_type (v1-compatible) | subject_type / subject_id | Payload (minimal) | correlation_id | idempotency_key (deterministic) | visibility |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Contract created as result of RFQ award | `backend/app/api/routes/rfqs.py:award_quote` (after contract insert + commit; per contract) | `CONTRACT_CREATED` | `rfq` / `rfq.id` | `{ contract_id, rfq_id, deal_id, counterparty_id?, settlement_date?, trade_index?, quote_group_id? }` | request UUID | `contract:{contract.contract_id}:created` | `finance` |

## D. Customer / KYC (Sales-side)

| Action | Emitter location (write path) | event_type (v2) | subject_type / subject_id | Payload (minimal) | correlation_id | idempotency_key (deterministic) | visibility |
| --- | --- | --- | --- | --- | --- | --- | --- |
| KYC document uploaded for Customer | `backend/app/api/routes/customers.py:upload_customer_document` (after commit) | `KYC_DOCUMENT_UPLOADED` | `customer` / `customer_id` | `{ customer_id, document_id, filename, content_type, uploaded_by_email? }` | request UUID | `kyc_document:{doc.id}:uploaded` | `finance` |
| Customer KYC status changed | `backend/app/api/routes/customers.py:run_customer_credit_check` (after commit) | `KYC_STATUS_CHANGED` | `customer` / `customer_id` | `{ customer_id, kyc_status, reason_code?, details? }` | request UUID | `customer:{customer_id}:kyc_status:{payload.kyc_status}` | `finance` |

**Ownership (locked):** KYC is executed/owned by Financeiro (even if some current endpoints are role-gated differently today).

## E. Counterparty (Non-KYC Controls)

These are hedge counterparty operational controls/due-diligence signals. They must not be modeled as “KYC”.

| Action | Emitter location (write path) | event_type (v2) | subject_type / subject_id | Payload (minimal) | correlation_id | idempotency_key (deterministic) | visibility |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Counterparty created | `backend/app/api/routes/counterparties.py:create_counterparty` (after commit) | `COUNTERPARTY_CREATED` | `counterparty` / `cp.id` | `{ counterparty_id, name, type? }` | request UUID | `counterparty:{cp.id}:created` | `finance` |
| Counterparty document uploaded | `backend/app/api/routes/counterparties.py:upload_counterparty_document` (after commit) | `COUNTERPARTY_DOCUMENT_UPLOADED` | `counterparty` / `counterparty_id` | `{ counterparty_id, document_id, filename, content_type, uploaded_by_email? }` | request UUID | `counterparty_document:{doc.id}:uploaded` | `finance` |
| Counterparty check created (credit/sanctions/risk_flag) | `backend/app/api/routes/counterparties.py:run_counterparty_kyc_check` (after commit) | `COUNTERPARTY_CHECK_CREATED` | `counterparty` / `counterparty_id` | `{ counterparty_id, check_id, check_type, status, score?, expires_at }` | request UUID | `counterparty_check:{check.id}:created` | `finance` |

## F. Inbox Decisions (Audit-only)

| Action | Emitter location (write path) | event_type (v2) | subject_type / subject_id | Payload (minimal) | correlation_id | idempotency_key (deterministic) | visibility |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Decision recorded (no_hedge) | `backend/app/api/routes/inbox.py:inbox_create_decision` (after commit) | `INBOX_DECISION_RECORDED` | `exposure` / `exposure_id` | `{ exposure_id, decision:"no_hedge", justification, audit_log_id:log.id }` | request UUID | `inbox_decision:{log.id}:recorded` | `finance` |

## G. Cashflow Hooks

- **None in v0/v1**: Cashflow is read-only (`GET /cashflow`). No emitter in this phase.

---

## 2) v1 → v2 Compatibility Map

## v1 event types (frozen)

Timeline v1 allowlist in backend is:

- `SO_CREATED`
- `PO_CREATED`
- `CONTRACT_CREATED`
- `EXPOSURE_UPDATED`
- `MTM_REQUIRED`

## Compatibility guarantee

- **No changes** to v1 event names or meanings.
- v2 introduces **new event types** (e.g., `RFQ_CREATED`) that are safe to render in the current UI:
  - Frontend treats `event_type` as `TimelineV1EventType | string` and displays unknown types as raw text.

## “Becomes richer” in v2 (without breaking v1)

- `CONTRACT_CREATED` remains the same string, but gains a consistent payload schema (listed above) when emitted from RFQ award.

## Explicitly out-of-scope for this Phase 1 plan

- Auto-emission for v1 types from their respective domain write paths (`SO_CREATED`, `PO_CREATED`, `EXPOSURE_UPDATED`, `MTM_REQUIRED`).
  - These can be planned as a separate Phase 1.5 or later, to avoid scope drift.

---

## 3) Guardrails (Explicit)

- Emit only on:
  - successful domain writes (after commit), OR
  - explicitly blocked actions that already log audit (e.g., KYC gate blocks) **without mutating domain state**.
- No derived/recomputed timeline events (no backfills in Phase 2 unless explicitly authorized).
- No Timeline-driven side effects.
- No retries creating duplicates: idempotency keys are mandatory.

---

## 4) Tracker-Ready Backend Tickets (Planning Only)

## Ticket 1 — RFQ core emitters

- Implement emitters for: `RFQ_CREATED`, `RFQ_QUOTE_CREATED`, `RFQ_AWARDED`, `RFQ_CANCELLED`, `RFQ_KYC_GATE_BLOCKED`.
- AC:
  - Each action emits exactly once with deterministic idempotency.
  - Events share `correlation_id` per request.
  - `subject_type="rfq"` for RFQ-scoped events.

## Ticket 2 — RFQ send emitters

- Implement emitters for: `RFQ_SEND_REQUESTED`, `RFQ_SEND_ATTEMPT_CREATED`, `RFQ_SEND_ATTEMPT_STATUS_UPDATED`, `RFQ_DEAL_CONFIRMED`.
- AC:
  - Per-attempt events emitted with `attempt.id`-based idempotency.
  - Status update emits at most once per status value per attempt.

## Ticket 3 — Contract created emitter (v1-compatible)

- Emit `CONTRACT_CREATED` when contracts are created during RFQ award.
- AC:
  - One event per created contract.
  - Payload includes `contract_id` and `deal_id` at minimum.
  - Attached to `subject_type="rfq" subject_id=<rfq.id>`.

## Ticket 4 — Counterparty/KYC emitters

- Emit (Customer/KYC): `KYC_DOCUMENT_UPLOADED`, `KYC_STATUS_CHANGED`.
- Emit (Counterparty, non-KYC): `COUNTERPARTY_CREATED`, `COUNTERPARTY_DOCUMENT_UPLOADED`, `COUNTERPARTY_CHECK_CREATED`.
- AC:
  - One event per created row (doc/check) in their respective domain.
  - Customer KYC events attach to `customer`.
  - Counterparty events attach to `counterparty`.

## Ticket 5 — Inbox decision emitter

- Emit: `INBOX_DECISION_RECORDED`.
- AC:
  - One event per audit log decision.
  - Subject is `exposure`.

---

## Open Questions (Must Lock Before Phase 2)

1. **Subject choice for KYC gate blocked events**: locked to `so` (Sales Order (SO)).
1. **Visibility defaults**: locked to `finance` for new v2 system events.
1. **Award flow consolidation**: locked to a single canonical `RFQ_AWARDED` with `award_source` in payload.
