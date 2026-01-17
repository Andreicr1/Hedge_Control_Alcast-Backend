"""Timeline v1 constants.

Canonical source:
- alcast_hedge_control_reference.md

Timeline v1 is intentionally locked. Do not add event types here unless an
explicitly authorized Timeline v2 expands the taxonomy.
"""

from __future__ import annotations

# Allowed Timeline v1 event types (frozen).
#
# From alcast_hedge_control_reference.md (Jan/2026):
# - SO_CREATED
# - PO_CREATED
# - CONTRACT_CREATED
# - EXPOSURE_UPDATED
# - MTM_REQUIRED
TIMELINE_V1_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "SO_CREATED",
        "PO_CREATED",
        "CONTRACT_CREATED",
        "EXPOSURE_UPDATED",
        "MTM_REQUIRED",
    }
)
