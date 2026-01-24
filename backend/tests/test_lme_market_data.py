from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_ingest_requires_token():
    payload = {
        "symbol": "P4Y00",
        "name": "Aluminium Hg 3M",
        "market": "LME",
        "price": 2271.0,
        "price_type": "live",
        "ts_price": "2026-01-18T14:32:00Z",
        "source": "barchart_excel",
    }

    r = client.post("/api/ingest/lme/price", json=payload)
    assert r.status_code == 401

    r = client.post(
        "/api/ingest/lme/price",
        json=payload,
        headers={"Authorization": "Bearer wrong"},
    )
    assert r.status_code == 403


def test_ingest_and_live_and_official_flow():
    base_headers = {"Authorization": "Bearer test-ingest-token"}

    cash = {
        "symbol": "P3Y00",
        "name": "Aluminium Hg Cash",
        "market": "LME",
        "price": 2245.5,
        "price_type": "live",
        "ts_price": "2026-01-18T14:32:00Z",
        "source": "barchart_excel",
    }
    three_month = {
        "symbol": "P4Y00",
        "name": "Aluminium Hg 3M",
        "market": "LME",
        "price": 2271.0,
        "price_type": "live",
        "ts_price": "2026-01-18T14:32:00Z",
        "source": "barchart_excel",
    }
    official = {
        "symbol": "Q7Y00",
        "name": "Aluminium Hg Official",
        "market": "LME",
        "price": 2233.0,
        "price_type": "official",
        "ts_price": "2026-01-17T00:00:00Z",
        "source": "barchart_excel",
    }

    r = client.post("/api/ingest/lme/price", json=cash, headers=base_headers)
    assert r.status_code == 201

    r = client.post("/api/ingest/lme/price", json=three_month, headers=base_headers)
    assert r.status_code == 201

    r = client.post("/api/ingest/lme/price", json=official, headers=base_headers)
    assert r.status_code == 201

    live = client.get("/api/market/lme/aluminum/live")
    assert live.status_code == 200
    body = live.json()
    assert body["cash"]["symbol"] == "P3Y00"
    assert body["three_month"]["symbol"] == "P4Y00"

    off = client.get("/api/market/lme/aluminum/official/latest")
    assert off.status_code == 200
    off_body = off.json()
    assert off_body["symbol"] == "Q7Y00"
    assert off_body["date"] == "2026-01-17"


def test_ingest_rejects_price_type_mismatch():
    payload = {
        "symbol": "Q7Y00",
        "name": "Aluminium Hg Official",
        "market": "LME",
        "price": 2233.0,
        "price_type": "live",
        "ts_price": datetime(2026, 1, 18, tzinfo=timezone.utc).isoformat(),
        "source": "barchart_excel",
    }

    r = client.post(
        "/api/ingest/lme/price",
        json=payload,
        headers={"Authorization": "Bearer test-ingest-token"},
    )
    assert r.status_code == 422


def test_history_cash_falls_back_to_official_when_no_p3y00_close_history():
    base_headers = {"Authorization": "Bearer test-ingest-token"}

    official = {
        "symbol": "Q7Y00",
        "name": "Aluminium Hg Official",
        "market": "LME",
        "price": 2968.0,
        "price_type": "official",
        "ts_price": "2025-12-31T00:00:00Z",
        "source": "barchart_excel_cashhistorical",
    }

    r = client.post("/api/ingest/lme/price", json=official, headers=base_headers)
    assert r.status_code == 201

    hist = client.get("/api/market/lme/aluminum/history/cash")
    assert hist.status_code == 200
    body = hist.json()
    assert isinstance(body, list)
    assert any(p.get("date") == "2025-12-31" and float(p.get("price")) == 2968.0 for p in body)


def test_history_3m_prefers_close_over_live_same_day():
    base_headers = {"Authorization": "Bearer test-ingest-token"}

    # Close for the day
    close_payload = {
        "symbol": "P4Y00",
        "name": "Aluminium Hg 3M",
        "market": "LME",
        "price": 2000.00,
        "price_type": "close",
        "ts_price": "2026-01-10T00:00:00Z",
        "source": "test",
    }
    r = client.post("/api/ingest/lme/price", json=close_payload, headers=base_headers)
    assert r.status_code == 201

    # Newer intraday live quote on the same day (must not affect close-series history)
    live_payload = {
        **close_payload,
        "price": 1995.00,
        "price_type": "live",
        "ts_price": "2026-01-10T12:34:56Z",
    }
    r = client.post("/api/ingest/lme/price", json=live_payload, headers=base_headers)
    assert r.status_code == 201

    r = client.get("/api/market/lme/aluminum/history/3m")
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
    assert data[0]["date"] == "2026-01-10"
    assert float(data[0]["price"]) == 2000.00
