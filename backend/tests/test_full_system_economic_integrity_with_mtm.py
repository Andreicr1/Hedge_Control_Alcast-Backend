from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import desc

from app import models
from app.api import deps
from app.main import app
from app.services.mtm_contract_snapshot_service import execute_mtm_contract_snapshot_run


def _stub_user(role_name: models.RoleName):
    class StubUser:
        def __init__(self):
            self.id = 1
            self.email = f"{role_name.value}@test.com"
            self.active = True
            self.role = type("Role", (), {"name": role_name})()

    return StubUser()


def _set_role(role_name: models.RoleName) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(role_name)


def _assert_premium_absent_or_zero(payload: Any) -> None:
    if isinstance(payload, dict):
        for k, v in payload.items():
            if isinstance(k, str) and "premium" in k.lower():
                if v is None:
                    continue
                if isinstance(v, (int, float)) and float(v) == 0.0:
                    continue
                raise AssertionError(f"Premium field must be None/0.0: {k}={v!r}")
            _assert_premium_absent_or_zero(v)
        return

    if isinstance(payload, list):
        for item in payload:
            _assert_premium_absent_or_zero(item)


def _seed_counterparty_pass_checks(db, counterparty_id: int) -> None:
    expires_at = datetime.utcnow() + timedelta(hours=24)
    for check_type in ("credit", "sanctions", "risk_flag"):
        db.add(
            models.KycCheck(
                owner_type=models.DocumentOwnerType.counterparty,
                owner_id=counterparty_id,
                check_type=check_type,
                status="pass",
                score=700 if check_type == "credit" else None,
                details_json={"seed": True, "check_type": check_type},
                expires_at=expires_at,
            )
        )


def _seed_lme_prices_for_test(db) -> None:
    # Contract MTM uses P3Y00 close.
    for day in range(10, 31):
        ts = datetime(2026, 1, day, 0, 0, 0, tzinfo=timezone.utc)
        db.add(
            models.LMEPrice(
                symbol="P3Y00",
                name="LME Aluminium Cash Settlement",
                market="LME",
                price=2100.0,
                price_type="close",
                ts_price=ts,
                source="westmetall",
            )
        )

    # Cashflow analytic defaults to Q7Y00 official (for variable pricing projection).
    for d in (date(2026, 1, 14), date(2026, 1, 30)):
        ts = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc)
        db.add(
            models.LMEPrice(
                symbol="Q7Y00",
                name="LME Aluminium Cash Settlement Official",
                market="LME",
                price=2100.0,
                price_type="official",
                ts_price=ts,
                source="official_seed",
            )
        )


client = TestClient(app)


def test_full_system_economic_integrity_with_mtm(db_session):
    """Institutional end-to-end: Deal→SO→Exposure→RFQ→Contract→MTM snapshots→Cashflow analytic."""

    uid = uuid.uuid4().hex[:8]

    # ---- Create Deal + Customer + SO (commercial) ----
    _set_role(models.RoleName.comercial)

    r_deal = client.post(
        "/api/deals",
        json={
            "reference_name": f"E2E-{uid}",
            "commodity": "AL",
            "company": "ALCAST",
            "economic_period": "2026-01",
            "currency": "USD",
        },
    )
    assert r_deal.status_code == 201, r_deal.text
    deal = r_deal.json()

    r_cust = client.post(
        "/api/customers",
        json={
            "name": f"Customer {uid}",
            "kyc_status": "approved",
            "sanctions_flag": False,
            "active": True,
        },
    )
    assert r_cust.status_code == 201, r_cust.text
    cust = r_cust.json()

    r_so = client.post(
        "/api/sales-orders",
        json={
            "so_number": f"SO-{uid}",
            "deal_id": int(deal["id"]),
            "customer_id": int(cust["id"]),
            "product": "AL",
            "total_quantity_mt": 10.0,
            "unit": "MT",
            "pricing_type": "AVGInter",
            "pricing_period": "2026-01",
            "expected_delivery_date": "2026-02-15",
            "status": "active",
        },
    )
    assert r_so.status_code == 201, r_so.text
    so = r_so.json()

    _assert_premium_absent_or_zero(deal)
    _assert_premium_absent_or_zero(cust)
    _assert_premium_absent_or_zero(so)

    assert so["deal_id"] == deal["id"]
    assert so["customer_id"] == cust["id"]
    assert float(so["total_quantity_mt"]) == 10.0

    # ---- Verify exposure created from SO (finance) ----
    _set_role(models.RoleName.financeiro)

    r_exps = client.get("/api/exposures", params={"limit": 50})
    assert r_exps.status_code == 200, r_exps.text
    exposures = r_exps.json()
    assert isinstance(exposures, list)
    assert len(exposures) >= 1

    so_exposures = [
        e
        for e in exposures
        if e.get("source_type") == "so" and int(e.get("source_id")) == int(so["id"])
    ]
    assert len(so_exposures) == 1
    exposure = so_exposures[0]
    assert float(exposure["quantity_mt"]) == pytest.approx(10.0)
    assert "Premium" not in (exposure.get("pricing_reference") or "")

    rfq_period_bucket = None
    for k in ("delivery_date", "sale_date", "payment_date"):
        v = exposure.get(k)
        if v:
            rfq_period_bucket = str(v)[:7]
            break
    assert rfq_period_bucket and rfq_period_bucket != "unknown"

    _assert_premium_absent_or_zero(exposure)

    # ---- Create counterparty + RFQ + quotes (finance) ----
    r_cp = client.post(
        "/api/counterparties",
        json={
            "name": f"CP-{uid}",
            "type": "bank",
            "kyc_status": "approved",
            "sanctions_flag": False,
            "active": True,
        },
    )
    assert r_cp.status_code == 201, r_cp.text
    cp = r_cp.json()

    _assert_premium_absent_or_zero(cp)

    _seed_counterparty_pass_checks(db_session, int(cp["id"]))
    db_session.commit()

    rfq_number = f"RFQ-E2E-{uid}"

    r_rfq = client.post(
        "/api/rfqs",
        json={
            "rfq_number": rfq_number,
            "deal_id": int(deal["id"]),
            "so_id": int(so["id"]),
            "quantity_mt": 10.0,
            "period": rfq_period_bucket,
            "status": "pending",
            "invitations": [{"counterparty_id": int(cp["id"]), "counterparty_name": cp["name"]}],
            "trade_specs": [
                {
                    "trade_type": "Swap",
                    "leg1": {
                        "side": "buy",
                        "price_type": "Fix",
                        "quantity_mt": 10.0,
                        "fixing_date": "2026-01-15",
                    },
                    "leg2": {
                        "side": "sell",
                        "price_type": "AVGInter",
                        "quantity_mt": 10.0,
                        "start_date": "2026-01-10",
                        "end_date": "2026-01-31",
                    },
                    "sync_ppt": False,
                }
            ],
        },
    )
    assert r_rfq.status_code == 201, r_rfq.text
    rfq = r_rfq.json()

    invs = rfq.get("invitations") or []
    assert len(invs) == 1
    assert int(invs[0].get("counterparty_id")) == int(cp["id"])

    # Governance: correlation must be captured in immutable audit trail.
    db_session.expire_all()
    ev = (
        db_session.query(models.TimelineEvent)
        .filter(
            models.TimelineEvent.event_type == "RFQ_CREATED",
            models.TimelineEvent.subject_type == "rfq",
            models.TimelineEvent.subject_id == int(rfq["id"]),
        )
        .order_by(desc(models.TimelineEvent.id))
        .first()
    )
    assert ev is not None
    payload = ev.payload or {}
    assert payload.get("rfq_number") == rfq_number
    assert int(payload.get("so_id")) == int(so["id"])
    assert int(payload.get("deal_id")) == int(deal["id"])
    invited_ids = payload.get("invited_counterparty_ids") or []
    assert int(cp["id"]) in [int(x) for x in invited_ids]

    _assert_premium_absent_or_zero(rfq)

    quote_group_id = f"g-{uid}"

    r_buy = client.post(
        f"/api/rfqs/{int(rfq['id'])}/quotes",
        json={
            "counterparty_id": int(cp["id"]),
            "counterparty_name": cp["name"],
            "quote_price": 2000.0,
            "price_type": "Fix",
            "volume_mt": 10.0,
            "status": "quoted",
            "quote_group_id": quote_group_id,
            "leg_side": "buy",
        },
    )
    assert r_buy.status_code == 201, r_buy.text
    buy = r_buy.json()

    r_sell = client.post(
        f"/api/rfqs/{int(rfq['id'])}/quotes",
        json={
            "counterparty_id": int(cp["id"]),
            "counterparty_name": cp["name"],
            "quote_price": 1.0,
            "price_type": "AVGInter",
            "volume_mt": 10.0,
            "status": "quoted",
            "quote_group_id": quote_group_id,
            "leg_side": "sell",
        },
    )
    assert r_sell.status_code == 201, r_sell.text

    _assert_premium_absent_or_zero(buy)

    # ---- Award RFQ (approval flow if required) ----
    award_payload: dict[str, Any] = {"quote_id": int(buy["id"]), "motivo": "E2E award"}
    r_award_1 = client.post(f"/api/rfqs/{int(rfq['id'])}/award", json=award_payload)

    if r_award_1.status_code == 409:
        detail = r_award_1.json().get("detail") or {}
        assert detail.get("code") == "approval_required"
        wf_id = int(detail["workflow_request_id"])

        r_dec = client.post(
            f"/api/workflows/requests/{wf_id}/decisions",
            json={"decision": "approved", "justification": "E2E ok"},
        )
        assert r_dec.status_code == 201, r_dec.text

        award_payload["workflow_request_id"] = wf_id
        r_award_2 = client.post(f"/api/rfqs/{int(rfq['id'])}/award", json=award_payload)
        assert r_award_2.status_code == 200, r_award_2.text
    else:
        assert r_award_1.status_code == 200, r_award_1.text

    # API requests use a separate DB session; reset ours to see committed rows.
    db_session.rollback()
    db_session.expire_all()

    rfq_db = db_session.get(models.Rfq, int(rfq["id"]))
    assert rfq_db is not None
    assert rfq_db.status == models.RfqStatus.awarded

    contracts = (
        db_session.query(models.Contract).filter(models.Contract.rfq_id == int(rfq["id"]))
    ).all()
    assert len(contracts) >= 1

    contract = contracts[0]
    assert contract.status == models.ContractStatus.active.value
    assert int(contract.deal_id) == int(deal["id"])
    assert int(contract.counterparty_id) == int(cp["id"])

    legs = (contract.trade_snapshot or {}).get("legs") or []
    assert len(legs) == 2

    fixed_legs = [leg for leg in legs if leg.get("price_type") == "Fix"]
    assert len(fixed_legs) == 1
    assert fixed_legs[0].get("side") == "buy"
    assert float(fixed_legs[0].get("price")) == pytest.approx(2000.0)
    assert float(fixed_legs[0].get("volume_mt")) == pytest.approx(10.0)

    # Contract must be linked to the exposure produced by the SO (auditability).
    links = (
        db_session.query(models.ContractExposure)
        .filter(models.ContractExposure.contract_id == str(contract.contract_id))
        .all()
    )
    assert len(links) >= 1
    assert any(int(link.exposure_id) == int(exposure["id"]) for link in links)

    # ---- Seed market data (no mocks; authoritative input data) ----
    _seed_lme_prices_for_test(db_session)
    db_session.commit()

    # Create a non-active contract to prove snapshot run is active-only.
    db_session.add(
        models.Contract(
            contract_id=f"TEST-SETTLED-{uid}",
            deal_id=int(deal["id"]),
            rfq_id=int(rfq["id"]),
            counterparty_id=int(cp["id"]),
            status=models.ContractStatus.settled.value,
            trade_index=0,
            quote_group_id=quote_group_id,
            trade_snapshot=contract.trade_snapshot,
            settlement_date=date(2026, 1, 31),
            settlement_meta=None,
        )
    )
    db_session.commit()

    # ---- Materialize MTM snapshots for two dates (service surface) ----
    for as_of_date in (date(2026, 1, 15), date(2026, 1, 31)):
        res = execute_mtm_contract_snapshot_run(
            db_session,
            as_of_date=as_of_date,
            filters={"deal_id": int(deal["id"])},
            requested_by_user_id=1,
            dry_run=False,
        )
        assert hasattr(res, "written")
        assert res.written == 1
        assert res.skipped_not_computable == 0

        # Determinism: rerun with same inputs => no new writes.
        res2 = execute_mtm_contract_snapshot_run(
            db_session,
            as_of_date=as_of_date,
            filters={"deal_id": int(deal["id"])},
            requested_by_user_id=1,
            dry_run=False,
        )
        assert hasattr(res2, "written")
        assert res2.written == 0
        assert res2.skipped_existing >= 1

        db_session.commit()

        snap = (
            db_session.query(models.MtmContractSnapshot)
            .filter(models.MtmContractSnapshot.contract_id == str(contract.contract_id))
            .filter(models.MtmContractSnapshot.as_of_date == as_of_date)
            .one()
        )

        expected_ref = as_of_date - timedelta(days=1)
        refs = snap.references or {}
        used_ref = refs.get("observation_end_used") or refs.get("last_published_cash_date")
        assert used_ref == expected_ref.isoformat()

        # Active-only: settled contract must not produce snapshots.
        settled_snap = (
            db_session.query(models.MtmContractSnapshot)
            .filter(models.MtmContractSnapshot.contract_id == f"TEST-SETTLED-{uid}")
            .filter(models.MtmContractSnapshot.as_of_date == as_of_date)
            .all()
        )
        assert settled_snap == []

        # No premium anywhere in snapshot references.
        _assert_premium_absent_or_zero(refs)

    # ---- Cashflow analytic coherence (two dates) ----
    for as_of_date in (date(2026, 1, 15), date(2026, 1, 31)):
        r_cf = client.get(
            "/api/cashflow/analytic",
            params={
                "deal_id": int(deal["id"]),
                "as_of": as_of_date.isoformat(),
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
                "limit": 2000,
            },
        )
        assert r_cf.status_code == 200, r_cf.text
        lines = r_cf.json()
        assert isinstance(lines, list)

        contract_lines = [
            line
            for line in lines
            if line.get("entity_type") == "contract"
            and line.get("entity_id") == str(contract.contract_id)
        ]
        assert len(contract_lines) == 1

        line = contract_lines[0]
        snap = (
            db_session.query(models.MtmContractSnapshot)
            .filter(models.MtmContractSnapshot.contract_id == str(contract.contract_id))
            .filter(models.MtmContractSnapshot.as_of_date == as_of_date)
            .one()
        )

        assert line["valuation_method"] == "mtm"
        assert line["valuation_reference_date"] == (as_of_date - timedelta(days=1)).isoformat()

        expected_mtm = float(snap.mtm_usd)
        assert float(line["amount"]) == pytest.approx(abs(expected_mtm))
        assert line["direction"] == ("inflow" if expected_mtm >= 0 else "outflow")

        # No premium-like keys should appear in analytic output.
        _assert_premium_absent_or_zero(lines)

    # ---- Explicit governance hard-stop: mismatch triggers 409 (no silent divergence) ----
    bad = (
        db_session.query(models.MtmContractSnapshot)
        .filter(models.MtmContractSnapshot.contract_id == str(contract.contract_id))
        .filter(models.MtmContractSnapshot.as_of_date == date(2026, 1, 15))
        .one()
    )
    refs_bad = dict(bad.references or {})
    refs_bad["observation_end_used"] = "2026-01-13"  # expected 2026-01-14 for as_of=2026-01-15
    bad.references = refs_bad
    db_session.add(bad)
    db_session.commit()

    r_cf_bad = client.get(
        "/api/cashflow/analytic",
        params={
            "deal_id": int(deal["id"]),
            "as_of": "2026-01-15",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        },
    )
    assert r_cf_bad.status_code == 409
    body = r_cf_bad.json()
    assert body["detail"]["code"] == "valuation_reference_mismatch"
