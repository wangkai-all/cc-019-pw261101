"""Metric computation engine.

Design notes for the tricky cases:

* Base metrics are aggregated independently in SQL and merged on the
  (date, store) key in Python. Joining orders to refunds inside one query
  would multiply the paid amount by the number of refunds on an order
  (the "one order, several refunds" trap).
* The merge is a full outer join over keys: a day with refunds but no
  payment still produces a row, with paid_amount defaulting to zero.
* Derived metrics are evaluated in topological order. Division by zero
  (refund rate with no payment that day) evaluates to None and is
  serialized as null, which the UI renders as blank.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple

import duckdb

from . import definitions as defs_mod
from . import formula

MONEY_Q = Decimal("0.01")
RATE_Q = Decimal("0.0001")


def _q_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _q_rate(value: Decimal) -> Decimal:
    return value.quantize(RATE_Q, rounding=ROUND_HALF_UP)


def _to_decimal(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _store_column(source_table: str) -> str:
    """refunds has no store_id of its own; its store comes via orders."""
    if source_table == "orders":
        return "orders.store_id"
    return "orders.store_id"


def _base_series(conn: duckdb.DuckDBPyConnection, spec: dict,
                 start: str, end: str, store_id: Optional[str]
                 ) -> Dict[Tuple[str, str], Decimal]:
    """Aggregate one base metric into {(date, store_id): amount}."""
    table = spec["source_table"]
    time_field = spec["time_field"]
    amount_field = spec["amount_field"]
    agg = spec["aggregation"]
    store_col = _store_column(table)
    # All identifiers have been whitelisted at save/publish time.
    expr = "COUNT(*)" if agg == "count" else f"SUM({amount_field})"
    sql = f"""
        SELECT CAST({time_field} AS DATE) AS d, stores.store_id, {expr}
        FROM {table}
        JOIN stores ON stores.store_id = {store_col}
        WHERE {time_field} BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
    """
    params: list = [start, end]
    if store_id is not None:
        sql += " AND stores.store_id = ?"
        params.append(store_id)
    sql += " GROUP BY 1, 2"
    rows = conn.execute(sql, params).fetchall()
    return {(str(r[0]), r[1]): _to_decimal(r[2] or 0) for r in rows}


def _topo_order(base_keys: List[str], derived: List[dict]) -> List[str]:
    order = list(base_keys)
    pending = {d["metric_key"]: formula.parse(d["formula"]) for d in derived}
    resolved = set(order)
    # Formulas were validated at save/publish time, so this always terminates.
    while pending:
        progressed = False
        for key in list(pending):
            if formula.references(pending[key]) <= resolved:
                order.append(key)
                resolved.add(key)
                del pending[key]
                progressed = True
        if not progressed:  # pragma: no cover - validation prevents this
            raise defs_mod.DefinitionError("无法确定指标计算顺序")
    return order


def run_query(conn: duckdb.DuckDBPyConnection, version_id: str, start: str,
              end: str, store_id: Optional[str]) -> dict:
    version = defs_mod.require_version(conn, version_id)
    all_defs = defs_mod.list_definitions(conn, version_id)
    base_defs = [d for d in all_defs if d["kind"] == "base"]
    derived_defs = [d for d in all_defs if d["kind"] == "derived"]
    base_keys = [d["metric_key"] for d in base_defs]

    # 1. Independent base series (no order-refund join that inflates payment).
    series: Dict[str, Dict[Tuple[str, str], Decimal]] = {}
    all_keys = set()
    for spec in base_defs:
        s = _base_series(conn, spec, start, end, store_id)
        series[spec["metric_key"]] = s
        all_keys.update(s.keys())

    # 2. Full outer merge: refund-only days keep their row.
    rows: List[dict] = []
    for key in sorted(all_keys, key=lambda k: (k[0], k[1])):
        date, sid = key
        values: Dict[str, Optional[Decimal]] = {}
        for bk in base_keys:
            values[bk] = series[bk].get(key, Decimal("0"))
        rows.append({"date": date, "store_id": sid, "_values": values})

    # 3. Derived metrics in dependency order.
    asts = {d["metric_key"]: formula.parse(d["formula"]) for d in derived_defs}
    calc_order = _topo_order(base_keys, derived_defs)
    for row in rows:
        for key in calc_order:
            if key in asts:
                row["_values"][key] = formula.evaluate(asts[key], row["_values"])

    # 4. Serialize with fixed rounding and null-on-undefined semantics.
    money_keys = set(base_keys) | {
        d["metric_key"] for d in derived_defs
        if "/" not in (d["formula"] or "")
    }
    rate_keys = {d["metric_key"] for d in derived_defs} - money_keys

    def serialize(values: Dict[str, Optional[Decimal]]) -> Dict[str, Optional[str]]:
        out: Dict[str, Optional[str]] = {}
        for key, val in values.items():
            if val is None:
                out[key] = None
            elif key in rate_keys:
                out[key] = str(_q_rate(val))
            else:
                out[key] = str(_q_money(val))
        return out

    data_rows = [
        {"date": r["date"], "store_id": r["store_id"], "metrics": serialize(r["_values"])}
        for r in rows
    ]

    # Totals row: money summed, rate recomputed from totals (never an
    # average of daily rates); null when its denominator totals zero.
    total_values: Dict[str, Optional[Decimal]] = {bk: Decimal("0") for bk in base_keys}
    for r in rows:
        for bk in base_keys:
            total_values[bk] += r["_values"][bk]
    for key in calc_order:
        if key in asts:
            total_values[key] = formula.evaluate(asts[key], total_values)
    totals = serialize(total_values)

    store_rows = conn.execute(
        "SELECT store_id, store_name FROM stores ORDER BY store_id"
    ).fetchall()
    stores = [{"store_id": r[0], "store_name": r[1]} for r in store_rows]

    return {
        "version": version,
        "definitions": all_defs,
        "stores": stores,
        "rows": data_rows,
        "totals": totals,
        "metric_order": calc_order,
    }


def drill_down(conn: duckdb.DuckDBPyConnection, version_id: str, date: str,
               store_id: str) -> dict:
    """Return the raw orders and refunds behind one (date, store) cell.

    Inclusion follows the version's own time-field rules, so V1 and V2 can
    surface different refund rows for the same day.
    """
    version = defs_mod.require_version(conn, version_id)
    all_defs = {d["metric_key"]: d for d in defs_mod.list_definitions(conn, version_id)}
    paid_spec = all_defs["paid_amount"]
    refund_spec = all_defs["refund_amount"]

    orders = conn.execute(
        f"""
        SELECT order_id, store_id, CAST(order_date AS VARCHAR), paid_amount
        FROM orders
        WHERE store_id = ? AND {paid_spec['time_field']} = CAST(? AS DATE)
        ORDER BY order_id
        """,
        [store_id, date],
    ).fetchall()
    order_rows = [
        {"order_id": r[0], "store_id": r[1], "order_date": r[2],
         "paid_amount": str(_q_money(_to_decimal(r[3])))}
        for r in orders
    ]

    refund_tf = refund_spec["time_field"]
    # When refunds are attributed to the order date (V1), show every refund
    # of the day's orders; when attributed to refund date (V2), only refunds
    # actually processed on that day.
    if refund_tf == "orders.order_date":
        sql = """
            SELECT r.refund_id, r.order_id, CAST(r.refund_date AS VARCHAR),
                   r.refund_amount
            FROM refunds r JOIN orders o USING (order_id)
            WHERE o.store_id = ? AND o.order_date = CAST(? AS DATE)
            ORDER BY r.refund_id
        """
    else:
        sql = """
            SELECT r.refund_id, r.order_id, CAST(r.refund_date AS VARCHAR),
                   r.refund_amount
            FROM refunds r JOIN orders o USING (order_id)
            WHERE o.store_id = ? AND r.refund_date = CAST(? AS DATE)
            ORDER BY r.refund_id
        """
    refunds = conn.execute(sql, [store_id, date]).fetchall()
    refund_rows = [
        {"refund_id": r[0], "order_id": r[1], "refund_date": r[2],
         "refund_amount": str(_q_money(_to_decimal(r[3])))}
        for r in refunds
    ]

    return {
        "version": version,
        "date": date,
        "store_id": store_id,
        "refund_time_field": refund_tf,
        "orders": order_rows,
        "refunds": refund_rows,
    }
