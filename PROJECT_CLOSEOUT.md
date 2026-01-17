# Alcast Hedge Control — Project Close‑Out Note (v1.0)

**Status:** Completed / Closed

**Date:** 2026‑01‑13

## Scope Delivered (In‑Scope)

- **Core domain flows:** SO/PO origination, exposure aggregation, finance decision points, RFQ orchestration, contract creation, MTM and settlements logic.
- **Governance:** RBAC enforcement for read/write boundaries; audit logging for sensitive actions.
- **Timeline v2 (backend):** deterministic idempotency keys, correlation ID propagation, default `visibility="finance"`, and emitters wired across RFQ/customer/counterparty/inbox flows.
- **Dashboard (real data, no mocks):** `/dashboard/summary` and related endpoints are DB‑backed and enforce RBAC; frontend dashboard consumes real data.

## Scope De‑Scoped (Explicit Non‑Requirements for v1.0)

These items are explicitly **not required** to consider the initiative complete:

- **Timeline human collaboration layer:** comments, annotations, @mentions, and attachments.
- **Formal exports & reconciliation packs:** CSV/PDF/Excel export formats and complete reconciliation workflows.
- **Cashflow scenarios/sensitivity:** stress testing and what‑if analysis.
- **Multi‑level approval workflows:** institutional control is via RBAC + audit, not an approvals engine.

## Roadmap Deferred (Future Enhancements)

- Dedicated collaboration UX on top of Timeline (human notes, threads, mentions).
- Export bundles and downstream integrations (data lake/ERP reconciliation feeds, PDF packs).
- Additional analytics (scenario/sensitivity; advanced risk dashboards).
- Stronger auth posture (SSO/MFA) if required by IT policy.

## Acceptance Gate (Completion Checks)

- **Dashboard is DB‑backed:** validated via tests that seed DB rows and assert they appear in `/dashboard/summary`.
- **RBAC is enforced:** validated that roles outside Finance/Auditoria are denied access where appropriate.

To run the focused acceptance tests in the backend venv:

- `\.venv\Scripts\python -m pytest -q tests\test_dashboard_real_queries.py`

## Closure

With the real dashboard implemented and acceptance checks in place, the remaining gaps are either explicitly de‑scoped non‑requirements or deferred roadmap items. The initiative is therefore formally **completed**.