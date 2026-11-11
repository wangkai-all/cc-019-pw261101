"""End-to-end API smoke tests through the FastAPI ASGI app."""
import pytest

from fastapi.testclient import TestClient

from app import main
from app import db as db_mod


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "api.duckdb")
    main.init_db()
    with TestClient(main.app) as c:
        yield c


def test_compare_endpoint_and_freeze(client):
    payload = {
        "left_version_id": "v1",
        "right_version_id": "v2",
        "start_date": "2026-10-28",
        "end_date": "2026-11-05",
        "store_id": None,
    }
    resp = client.post("/api/compare", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["left"]["version"]["version_id"] == "v1"
    assert body["right"]["version"]["version_id"] == "v2"
    # Definitions are echoed back so the UI can show what was actually used.
    left_refund = next(
        d for d in body["left"]["definitions"] if d["metric_key"] == "refund_amount"
    )
    right_refund = next(
        d for d in body["right"]["definitions"] if d["metric_key"] == "refund_amount"
    )
    assert left_refund["time_field"] == "orders.order_date"
    assert right_refund["time_field"] == "refunds.refund_date"


def test_frozen_version_rejects_edits(client):
    resp = client.put(
        "/api/versions/v1/definitions",
        json={"base": [], "derived": []},
    )
    assert resp.status_code == 400
    assert "冻结" in resp.json()["detail"]


def test_validate_endpoint_blocks_bad_formula(client):
    good_base = [
        {"metric_key": "paid_amount", "metric_name": "支付额",
         "grain": "store_id, date", "time_field": "orders.order_date",
         "aggregation": "sum", "source_table": "orders",
         "amount_field": "orders.paid_amount"},
    ]
    resp = client.post(
        "/api/validate",
        json={"base": good_base,
              "derived": [{"metric_key": "x", "metric_name": "x",
                           "formula": "paid_amount ** 2"}]},
    )
    assert resp.json()["valid"] is False


def test_drill_endpoint(client):
    resp = client.post(
        "/api/drill",
        json={"version_id": "v2", "date": "2026-11-02", "store_id": "S01"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["orders"] == []  # no payment that day
    assert [r["refund_id"] for r in body["refunds"]] == ["R1"]
