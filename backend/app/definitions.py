"""Metric version / definition CRUD and publish-time validation."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List

import duckdb

from . import formula

# Whitelists keep base-metric SQL fully controlled: only identifiers from
# these lists can ever end up in a generated query.
_ALLOWED_TABLES = {
    "orders",
    "refunds JOIN orders USING (order_id)",
}
_ALLOWED_TIME_FIELDS = {
    "orders.order_date",
    "refunds.refund_date",
}
_ALLOWED_AMOUNT_FIELDS = {
    "orders.paid_amount",
    "refunds.refund_amount",
}
_ALLOWED_AGGREGATIONS = {"sum", "count"}


class DefinitionError(ValueError):
    """Raised when a definition set fails structural validation."""


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------

def list_versions(conn: duckdb.DuckDBPyConnection) -> List[dict]:
    rows = conn.execute(
        """
        SELECT version_id, label, status, created_at, published_at
        FROM metric_versions ORDER BY created_at
        """
    ).fetchall()
    return [
        {
            "version_id": r[0],
            "label": r[1],
            "status": r[2],
            "created_at": str(r[3]),
            "published_at": str(r[4]) if r[4] else None,
        }
        for r in rows
    ]


def get_version(conn: duckdb.DuckDBPyConnection, version_id: str) -> dict | None:
    row = conn.execute(
        "SELECT version_id, label, status, created_at, published_at "
        "FROM metric_versions WHERE version_id = ?",
        [version_id],
    ).fetchone()
    if not row:
        return None
    return {
        "version_id": row[0],
        "label": row[1],
        "status": row[2],
        "created_at": str(row[3]),
        "published_at": str(row[4]) if row[4] else None,
    }


def require_version(conn: duckdb.DuckDBPyConnection, version_id: str) -> dict:
    version = get_version(conn, version_id)
    if version is None:
        raise DefinitionError(f"版本不存在: {version_id}")
    return version


def list_definitions(conn: duckdb.DuckDBPyConnection, version_id: str) -> List[dict]:
    require_version(conn, version_id)
    rows = conn.execute(
        """
        SELECT metric_key, metric_name, kind, grain, time_field, aggregation,
               source_table, amount_field, formula
        FROM metric_definitions WHERE version_id = ?
        ORDER BY CASE kind WHEN 'base' THEN 0 ELSE 1 END, metric_key
        """,
        [version_id],
    ).fetchall()
    return [
        {
            "metric_key": r[0],
            "metric_name": r[1],
            "kind": r[2],
            "grain": r[3],
            "time_field": r[4],
            "aggregation": r[5],
            "source_table": r[6],
            "amount_field": r[7],
            "formula": r[8],
        }
        for r in rows
    ]


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def validate_definition_set(base: List[dict], derived: List[dict]) -> None:
    """Structural validation run on every save and again before publish.

    Checks: unique keys, whitelisted base fields, parseable formulas,
    references to existing metrics, and acyclic dependency graph.
    """
    keys: List[str] = [d["metric_key"] for d in base] + [d["metric_key"] for d in derived]
    if len(keys) != len(set(keys)):
        dupes = sorted({k for k in keys if keys.count(k) > 1})
        raise DefinitionError(f"指标 key 重复: {', '.join(dupes)}")
    if not base:
        raise DefinitionError("至少需要一个基础指标")

    known = set(keys)
    for d in base:
        if d["source_table"] not in _ALLOWED_TABLES:
            raise DefinitionError(f"基础指标 {d['metric_key']} 的来源表不在白名单内")
        if d["time_field"] not in _ALLOWED_TIME_FIELDS:
            raise DefinitionError(f"基础指标 {d['metric_key']} 的时间字段不在白名单内")
        if d["aggregation"] not in _ALLOWED_AGGREGATIONS:
            raise DefinitionError(f"基础指标 {d['metric_key']} 的聚合方式不受支持")
        if d["aggregation"] == "sum" and d["amount_field"] not in _ALLOWED_AMOUNT_FIELDS:
            raise DefinitionError(f"基础指标 {d['metric_key']} 的金额字段不在白名单内")

    # Parse formulas first; a syntax error is reported with its position.
    asts: Dict[str, formula.Node] = {}
    for d in derived:
        try:
            asts[d["metric_key"]] = formula.validate(d["formula"], known)
        except formula.FormulaError as exc:
            raise DefinitionError(f"指标 {d['metric_key']} 的公式非法: {exc}") from exc

    # Cycle detection via iterative DFS over the reference graph.
    graph = {key: sorted(formula.references(asts[key])) for key in asts}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {key: WHITE for key in graph}

    def visit(start: str) -> None:
        stack = [(start, iter(graph[start]))]
        color[start] = GRAY
        while stack:
            node, it = stack[-1]
            advanced = False
            for nxt in it:
                if nxt not in graph:  # base metric or unknown; unknown already rejected
                    continue
                if color[nxt] == GRAY:
                    cycle = [k for k, c in color.items() if c == GRAY]
                    raise DefinitionError(f"指标依赖存在循环: {' -> '.join(cycle + [nxt])}")
                if color[nxt] == WHITE:
                    color[nxt] = GRAY
                    stack.append((nxt, iter(graph[nxt])))
                    advanced = True
                    break
            if not advanced:
                color[node] = BLACK
                stack.pop()

    for key in graph:
        if color[key] == WHITE:
            visit(key)


# --------------------------------------------------------------------------
# Mutations (drafts only; published rows are never touched)
# --------------------------------------------------------------------------

def create_draft_from(conn: duckdb.DuckDBPyConnection, source_version_id: str,
                      new_version_id: str, label: str) -> dict:
    source = require_version(conn, source_version_id)
    if get_version(conn, new_version_id) is not None:
        raise DefinitionError(f"版本 id 已存在: {new_version_id}")
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    conn.execute(
        "INSERT INTO metric_versions (version_id, label, status, created_at) "
        "VALUES (?, ?, 'draft', ?)",
        [new_version_id, label, now],
    )
    conn.execute(
        """
        INSERT INTO metric_definitions
          (version_id, metric_key, metric_name, kind, grain, time_field,
           aggregation, source_table, amount_field, formula)
        SELECT ?, metric_key, metric_name, kind, grain, time_field,
               aggregation, source_table, amount_field, formula
        FROM metric_definitions WHERE version_id = ?
        """,
        [new_version_id, source["version_id"]],
    )
    return get_version(conn, new_version_id)


def _replace_definitions(conn: duckdb.DuckDBPyConnection, version_id: str,
                         base: List[dict], derived: List[dict]) -> None:
    conn.execute("DELETE FROM metric_definitions WHERE version_id = ?", [version_id])
    for d in base:
        conn.execute(
            """
            INSERT INTO metric_definitions
              (version_id, metric_key, metric_name, kind, grain, time_field,
               aggregation, source_table, amount_field, formula)
            VALUES (?, ?, ?, 'base', ?, ?, ?, ?, ?, NULL)
            """,
            [version_id, d["metric_key"], d["metric_name"], d["grain"],
             d["time_field"], d["aggregation"], d["source_table"], d["amount_field"]],
        )
    for d in derived:
        conn.execute(
            """
            INSERT INTO metric_definitions
              (version_id, metric_key, metric_name, kind, grain, time_field,
               aggregation, source_table, amount_field, formula)
            VALUES (?, ?, ?, 'derived', NULL, NULL, NULL, NULL, NULL, ?)
            """,
            [version_id, d["metric_key"], d["metric_name"], d["formula"]],
        )


def save_draft(conn: duckdb.DuckDBPyConnection, version_id: str,
               base: List[dict], derived: List[dict]) -> None:
    """Persist a draft snapshot.

    Structural validation is deliberately NOT enforced here: an analyst may
    save a half-finished draft. The hard gate runs at publish time, so an
    invalid definition set can never freeze into a published version.
    """
    version = require_version(conn, version_id)
    if version["status"] != "draft":
        raise DefinitionError("已发布版本已冻结，不能修改；请基于它创建新版本")
    keys = [d["metric_key"] for d in base] + [d["metric_key"] for d in derived]
    if len(keys) != len(set(keys)):
        dupes = sorted({k for k in keys if keys.count(k) > 1})
        raise DefinitionError(f"指标 key 重复: {', '.join(dupes)}")
    _replace_definitions(conn, version_id, base, derived)


def publish(conn: duckdb.DuckDBPyConnection, version_id: str) -> dict:
    version = require_version(conn, version_id)
    if version["status"] == "published":
        raise DefinitionError("该版本已经发布")
    defs = list_definitions(conn, version_id)
    base = [d for d in defs if d["kind"] == "base"]
    derived = [d for d in defs if d["kind"] == "derived"]
    # Re-validate at publish time so nothing invalid can ever freeze.
    validate_definition_set(base, derived)
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    conn.execute(
        "UPDATE metric_versions SET status = 'published', published_at = ? "
        "WHERE version_id = ?",
        [now, version_id],
    )
    return get_version(conn, version_id)
