"""DuckDB connection management, schema and demo data seeding."""
from __future__ import annotations

import os
from pathlib import Path

import duckdb

DB_PATH = Path(os.environ.get("WORKBENCH_DB", Path(__file__).resolve().parent.parent / "data.duckdb"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS stores (
    store_id   VARCHAR PRIMARY KEY,
    store_name VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id    VARCHAR PRIMARY KEY,
    store_id    VARCHAR NOT NULL,
    order_date  DATE    NOT NULL,
    paid_amount DECIMAL(14, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS refunds (
    refund_id    VARCHAR PRIMARY KEY,
    order_id     VARCHAR NOT NULL REFERENCES orders(order_id),
    refund_date  DATE    NOT NULL,
    refund_amount DECIMAL(14, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS metric_versions (
    version_id   VARCHAR PRIMARY KEY,
    label        VARCHAR NOT NULL,
    status       VARCHAR NOT NULL CHECK (status IN ('draft', 'published')),
    created_at   TIMESTAMP NOT NULL,
    published_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS metric_definitions (
    version_id      VARCHAR NOT NULL REFERENCES metric_versions(version_id),
    metric_key      VARCHAR NOT NULL,
    metric_name     VARCHAR NOT NULL,
    kind            VARCHAR NOT NULL CHECK (kind IN ('base', 'derived')),
    grain           VARCHAR,
    time_field      VARCHAR,
    aggregation     VARCHAR,
    source_table    VARCHAR,
    amount_field    VARCHAR,
    formula         VARCHAR,
    PRIMARY KEY (version_id, metric_key)
);
"""


def get_conn() -> duckdb.DuckDBPyConnection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(DB_PATH))
    conn.execute(_SCHEMA)
    return conn


# --------------------------------------------------------------------------
# Demo data
# --------------------------------------------------------------------------

_STORES = [
    ("S01", "南京西路店"),
    ("S02", "陆家嘴店"),
]

# (order_id, store_id, order_date, paid_amount)
_ORDERS = [
    ("O1001", "S01", "2026-10-28", "300.00"),
    ("O1002", "S01", "2026-10-30", "200.00"),
    ("O1003", "S01", "2026-11-01", "500.00"),
    ("O1004", "S02", "2026-10-29", "400.00"),
    ("O1005", "S02", "2026-11-01", "100.00"),
]

# (refund_id, order_id, refund_date, refund_amount)
_REFUNDS = [
    ("R1", "O1001", "2026-11-02", "50.00"),   # 跨月退款
    ("R2", "O1001", "2026-11-05", "70.00"),   # 同一订单第二次退款
    ("R3", "O1002", "2026-10-31", "30.00"),   # 当月退款
    ("R4", "O1004", "2026-11-03", "400.00"),  # 全额退款，跨月
    ("R5", "O1003", "2026-11-04", "20.00"),   # 同日还有支付
]

# Metric keys shared by every version.
PAID_AMOUNT = "paid_amount"
REFUND_AMOUNT = "refund_amount"
NET_SALES = "net_sales"
REFUND_RATE = "refund_rate"

_BASE_SPECS = [
    {
        "metric_key": PAID_AMOUNT,
        "metric_name": "支付额",
        "grain": "store_id, date",
        "source_table": "orders",
        "time_field": "orders.order_date",
        "amount_field": "orders.paid_amount",
        "aggregation": "sum",
    },
    # refund time_field differs per version and is filled in below.
    {
        "metric_key": REFUND_AMOUNT,
        "metric_name": "退款额",
        "grain": "store_id, date",
        "source_table": "refunds JOIN orders USING (order_id)",
        "time_field": "refunds.refund_date",
        "amount_field": "refunds.refund_amount",
        "aggregation": "sum",
    },
]

_DERIVED_SPECS = [
    {
        "metric_key": NET_SALES,
        "metric_name": "净销售额",
        "formula": "paid_amount - refund_amount",
    },
    {
        "metric_key": REFUND_RATE,
        "metric_name": "退款率（按金额）",
        "formula": "refund_amount / paid_amount",
    },
]


def _seed_definitions(conn: duckdb.DuckDBPyConnection, version_id: str,
                      refund_time_field: str) -> None:
    for spec in _BASE_SPECS:
        spec = dict(spec)
        if spec["metric_key"] == REFUND_AMOUNT:
            spec["time_field"] = refund_time_field
        conn.execute(
            """
            INSERT INTO metric_definitions
              (version_id, metric_key, metric_name, kind, grain, time_field,
               aggregation, source_table, amount_field, formula)
            VALUES (?, ?, ?, 'base', ?, ?, ?, ?, ?, NULL)
            """,
            (version_id, spec["metric_key"], spec["metric_name"], spec["grain"],
             spec["time_field"], spec["aggregation"], spec["source_table"],
             spec["amount_field"]),
        )
    for spec in _DERIVED_SPECS:
        conn.execute(
            """
            INSERT INTO metric_definitions
              (version_id, metric_key, metric_name, kind, grain, time_field,
               aggregation, source_table, amount_field, formula)
            VALUES (?, ?, ?, 'derived', NULL, NULL, NULL, NULL, NULL, ?)
            """,
            (version_id, spec["metric_key"], spec["metric_name"], spec["formula"]),
        )


def seed_demo(conn: duckdb.DuckDBPyConnection) -> None:
    """Insert demo rows and the two frozen published versions (idempotent)."""
    for row in _STORES:
        conn.execute("INSERT OR IGNORE INTO stores VALUES (?, ?)", row)
    for row in _ORDERS:
        conn.execute("INSERT OR IGNORE INTO orders VALUES (?, ?, CAST(? AS DATE), ?)", row)
    for row in _REFUNDS:
        conn.execute(
            "INSERT OR IGNORE INTO refunds VALUES (?, ?, CAST(? AS DATE), ?)", row
        )

    existing = conn.execute("SELECT COUNT(*) FROM metric_versions").fetchone()[0]
    if existing:
        return

    # V1: refunds are attributed back to the original order's payment date.
    conn.execute(
        """
        INSERT INTO metric_versions
          (version_id, label, status, created_at, published_at)
        VALUES ('v1', 'V1 退款扣回原订单支付日', 'published',
                TIMESTAMP '2026-10-01 09:00:00', TIMESTAMP '2026-10-01 09:00:00')
        """
    )
    _seed_definitions(conn, "v1", refund_time_field="orders.order_date")

    # V2: refunds are attributed to the actual refund date.
    conn.execute(
        """
        INSERT INTO metric_versions
          (version_id, label, status, created_at, published_at)
        VALUES ('v2', 'V2 退款扣在实际退款日', 'published',
                TIMESTAMP '2026-11-01 09:00:00', TIMESTAMP '2026-11-01 09:00:00')
        """
    )
    _seed_definitions(conn, "v2", refund_time_field="refunds.refund_date")


def init_db() -> duckdb.DuckDBPyConnection:
    conn = get_conn()
    seed_demo(conn)
    return conn
