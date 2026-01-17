# Cashflow v0 — Cross-Domain Alignment Note (PLANNING-ONLY, LOCKED)

Date: 2026-01-12

This note is a **planning-only** artifact. It introduces **no implementation** and authorizes **no code changes**.

## 1) Domain Roles (Source-of-Truth vs Read Models)

### Contracts (Source of Truth)
- **What it is:** The financial anchor. A Contract represents exactly **one trade (1:1)**.
- **Owns:** Contract identity, linkage (`deal_id`, `rfq_id`, `counterparty_id`), and settlement intent (`settlement_date`, optional `settlement_meta`).
- **Not:** An event stream; not a UI projection.

### MTM (Derived valuation, point-in-time)
- **What it is:** A **valuation** of a Contract as-of a date ($t$). It can be computed on demand and/or snapshotted.
- **Owns:** The meaning of “estimated current value” for a Contract under a defined methodology.
- **Not:** Cashflow by itself. MTM is a **value at a point in time**, not a schedule of future flows.

### Settlements (Derived read slice, settlement-centric)
- **What it is:** A **read-only** view of Contracts that are **settling today** or **upcoming**.
- **Owns:** Presenting settlement-related values for operational visibility.
- **Not:** A generalized cashflow ledger; not a booking system.

### Timeline (Append-only audit-like event stream)
- **What it is:** An append-only stream of **what happened** (events), with server-side visibility enforcement.
- **Owns:** Event traceability, correlation, and corrections (supersedes chains).
- **Not:** A projection engine, not a financial calculator.

### Cashflow v0 (Derived forward-looking read model)
- **What it is:** A **forward-looking** read model of **expected cash movements by future settlement date**, derived from Contracts + existing valuation/settlement signals.
- **Visibility:** **Financeiro + Auditoria**.
- **Not:** Source of truth, not booking, not approvals, not workflow.

## 2) Event vs Projection (Hard Boundary)

- **Event (Timeline):** “Something occurred” at a timestamp (`occurred_at`).
  - Examples (Timeline v1 allowlist): `SO_CREATED`, `PO_CREATED`, `CONTRACT_CREATED`, `EXPOSURE_UPDATED`, `MTM_REQUIRED`.
  - Events can trigger awareness but **do not encode projected financial flows**.

- **Projection (Cashflow):** “Given today’s knowledge, what cash movement is expected on date D?”
  - Projections are **read-only** and **derived**, and may change as market data updates.

Rule: **Timeline never becomes a cashflow source-of-truth.** Cashflow never emits events in v0.

## 3) Estimate (MTM proxy) vs Final Settlement (Realized)

### Estimated / MTM Proxy
- **Meaning:** Best-effort valuation-derived estimate of what settlement might be, based on available published market observations.
- **Stability:** Not stable; can move with market data and methodology updates.
- **Labeling:** Must be explicitly labeled as **`projected_*`** or **`estimated_*`**.

### Final Settlement
- **Meaning:** The value determined by the settlement rule when the underlying observation window is complete and authoritative data is available.
- **Stability:** Stable once settled/fully observable.
- **Labeling:** Must be explicitly labeled as **`final_*`** or **`realized_*`**.

Rule: Cashflow UI/API must never present a single ambiguous “value”. It must distinguish **projected** vs **final**.

## 4) Naming Conventions (to avoid ambiguity)

### Recommended terms
- **Cashflow (domain):** “Cashflow Projetado” (forward-looking) and “Liquidação” (settlement outcome).
- **Projection item:** `CashflowProjectionItem` (or `CashflowItemRead` with explicit projected/final fields).
- **Projected value field:** `projected_value_usd` (or `estimated_settlement_value_usd`).
- **Final settlement field:** `final_settlement_value_usd` (or `realized_settlement_value_usd`).
- **Methodology field:** `projected_methodology` / `final_methodology`.
- **As-of date:** `valuation_as_of_date` for projections.

### Forbidden ambiguous names
- `cashflow_value`
- `settlement_value` (without `projected_` or `final_` qualifier)
- `pnl` in Cashflow v0

## 5) Cross-Domain Alignment Rules (LOCKED for v0 planning)

1) **Contracts remain the anchor**: all Cashflow items must trace back to `contract_id`.
2) **MTM is valuation-only**: used as an input signal to projections, never as booking.
3) **Settlements are a read slice**: Cashflow may reuse the same underlying derived values conceptually, but does not replace settlements.
4) **Timeline is events-only**: Timeline events can inform “why a projection exists”, but not compute it.
5) **No scenarios/sensitivity in v0**: explicitly out of scope.
6) **RBAC**: Cashflow visibility is **Financeiro + Auditoria**, enforced server-side (in execution phase).

## 6) Non-goals (Explicit)

- No accounting/booking engine.
- No approvals/workflows.
- No recomputation or replacement of MTM/settlement logic.
- No new emitters or Timeline events for Cashflow in v0.

---

End of planning artifact.
