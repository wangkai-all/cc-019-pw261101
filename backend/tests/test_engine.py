"""Engine and validation tests.

Run with: .venv/bin/pytest -q
"""
from decimal import Decimal

import pytest

from app import definitions as defs_mod
from app import engine, formula
from app.db import init_db


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    db_file = tmp_path / "test.duckdb"
    monkeypatch.setattr("app.db.DB_PATH", db_file)
    c = init_db()
    yield c
    c.close()


# --------------------------------------------------------------------------
# Formula parser
# --------------------------------------------------------------------------

def test_formula_allows_only_math_and_refs():
    node = formula.validate("a + b * 2", {"a", "b"})
    assert formula.evaluate(node, {"a": Decimal("1"), "b": Decimal("3")}) == Decimal("7")


@pytest.mark.parametrize("bad", [
    "a + ",
    "a ** 2",
    "foo(a)",
    "a.__class__",
    "import os",
    "a # comment",
    "a +; b",
    "",
])
def test_formula_rejects_illegal_syntax(bad):
    with pytest.raises(formula.FormulaError):
        formula.parse(bad)


def test_formula_unknown_reference():
    with pytest.raises(formula.FormulaError, match="不存在"):
        formula.validate("a + ghost", {"a"})


def test_division_by_zero_is_none():
    node = formula.parse("a / b")
    assert formula.evaluate(node, {"a": Decimal("5"), "b": Decimal("0")}) is None
    assert formula.evaluate(node, {"a": Decimal("5"), "b": None}) is None


# --------------------------------------------------------------------------
# Definition validation
# --------------------------------------------------------------------------

def _base_defs():
    return [
        {"metric_key": "paid_amount", "metric_name": "支付额", "grain": "store_id, date",
         "time_field": "orders.order_date", "aggregation": "sum",
         "source_table": "orders", "amount_field": "orders.paid_amount"},
        {"metric_key": "refund_amount", "metric_name": "退款额", "grain": "store_id, date",
         "time_field": "refunds.refund_date", "aggregation": "sum",
         "source_table": "refunds JOIN orders USING (order_id)",
         "amount_field": "refunds.refund_amount"},
    ]


def test_validation_catches_cycle():
    derived = [
        {"metric_key": "x", "metric_name": "x", "formula": "y + 1"},
        {"metric_key": "y", "metric_name": "y", "formula": "x + 1"},
    ]
    with pytest.raises(defs_mod.DefinitionError, match="循环"):
        defs_mod.validate_definition_set(_base_defs(), derived)


def test_validation_catches_missing_dependency():
    derived = [{"metric_key": "x", "metric_name": "x", "formula": "ghost - 1"}]
    with pytest.raises(defs_mod.DefinitionError, match="不存在"):
        defs_mod.validate_definition_set(_base_defs(), derived)


def test_validation_rejects_non_whitelisted_table():
    base = _base_defs()
    base[0]["source_table"] = "orders; DROP TABLE stores;--"
    with pytest.raises(defs_mod.DefinitionError):
        defs_mod.validate_definition_set(base, [])


# --------------------------------------------------------------------------
# Version freeze / lifecycle
# --------------------------------------------------------------------------

def test_published_version_is_frozen(conn):
    with pytest.raises(defs_mod.DefinitionError, match="冻结"):
        defs_mod.save_draft(conn, "v1", _base_defs(), [])


def test_draft_publish_lifecycle(conn):
    v = defs_mod.create_draft_from(conn, "v1", "v3", "试验版")
    assert v["status"] == "draft"
    defs = defs_mod.list_definitions(conn, "v3")
    base = [d for d in defs if d["kind"] == "base"]
    derived = [d for d in defs if d["kind"] == "derived"]
    # Tamper into an invalid draft: saving is allowed, publishing is blocked.
    derived[0] = dict(derived[0], formula="ghost + 1")
    defs_mod.save_draft(conn, "v3", base, derived)
    with pytest.raises(defs_mod.DefinitionError, match="不存在"):
        defs_mod.publish(conn, "v3")
    # Repair and publish; historical v1 stays untouched.
    derived[0] = dict(derived[0], formula="paid_amount - refund_amount")
    defs_mod.save_draft(conn, "v3", base, derived)
    published = defs_mod.publish(conn, "v3")
    assert published["status"] == "published"
    v1 = {d["metric_key"]: d for d in defs_mod.list_definitions(conn, "v1")}
    assert v1["refund_amount"]["time_field"] == "orders.order_date"


# --------------------------------------------------------------------------
# Engine: the three tricky cases
# --------------------------------------------------------------------------

def _row_map(result):
    return {(r["date"], r["store_id"]): r["metrics"] for r in result["rows"]}


def test_multi_refund_does_not_inflate_payment(conn):
    """O1001 paid 300 with two refunds (50+70): payment must stay 300."""
    res = engine.run_query(conn, "v1", "2026-10-28", "2026-10-28", "S01")
    row = _row_map(res)[("2026-10-28", "S01")]
    assert row["paid_amount"] == "300.00"
    # V1 attributes both refunds back to the order date 10-28.
    assert row["refund_amount"] == "120.00"
    assert row["net_sales"] == "180.00"
    assert row["refund_rate"] == "0.4000"


def test_refund_only_day_kept_and_blank_rate(conn):
    """2026-11-02 at S01 has only a refund: row survives, rate is null."""
    res = engine.run_query(conn, "v2", "2026-11-02", "2026-11-02", "S01")
    row = _row_map(res)[("2026-11-02", "S01")]
    assert row["paid_amount"] == "0.00"
    assert row["refund_amount"] == "50.00"
    assert row["net_sales"] == "-50.00"
    assert row["refund_rate"] is None


def test_cross_month_refund_differs_between_versions(conn):
    # O1001 (10-28) gets refunds on 11-02 and 11-05.
    v1 = engine.run_query(conn, "v1", "2026-11-02", "2026-11-02", "S01")
    v2 = engine.run_query(conn, "v2", "2026-11-02", "2026-11-02", "S01")
    # V1: no order placed that day -> no row at all for that attribution.
    assert ("2026-11-02", "S01") not in _row_map(v1)
    row = _row_map(v2)[("2026-11-02", "S01")]
    assert row["refund_amount"] == "50.00"


def test_totals_rate_is_recomputed_not_averaged(conn):
    res = engine.run_query(conn, "v2", "2026-10-28", "2026-11-05", None)
    totals = res["totals"]
    # Totals over both stores: paid 1500, refunds 570.
    assert totals["paid_amount"] == "1500.00"
    assert totals["refund_amount"] == "570.00"
    assert totals["net_sales"] == "930.00"
    assert totals["refund_rate"] == str(
        (Decimal("570") / Decimal("1500")).quantize(Decimal("0.0001")))


def test_drill_down_follows_version_rules(conn):
    v1 = engine.drill_down(conn, "v1", "2026-10-28", "S01")
    refund_ids = {r["refund_id"] for r in v1["refunds"]}
    assert refund_ids == {"R1", "R2"}  # both refunds of the day's order
    v2 = engine.drill_down(conn, "v2", "2026-11-02", "S01")
    assert {r["refund_id"] for r in v2["refunds"]} == {"R1"}
