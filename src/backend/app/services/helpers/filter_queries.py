"""Database query functions for filter validation.

Each filter targets a single table (`Filter.table`). Scope filters from the
same table are AND-ed into the WHERE clause; scope filters from other tables
are dropped (their semantics across tables would require a join we don't
attempt here).
"""

from __future__ import annotations

import duckdb

from app.models.state import Filter


def _predicate_for_filter(filter_obj: Filter) -> str:
    op = filter_obj.operator.strip().upper()
    if op == "LIKE":
        return f'"{filter_obj.column}" LIKE ?'
    return f'"{filter_obj.column}" = ?'


def _build_grouped_where_clause(filters: list[Filter] | None) -> tuple[str, list[str]]:
    """Build WHERE fragment with OR-within-column, AND-across-columns semantics."""
    if not filters:
        return "", []

    grouped: dict[str, list[Filter]] = {}
    for filter_obj in filters:
        grouped.setdefault(filter_obj.column, []).append(filter_obj)

    group_clauses: list[str] = []
    params: list[str] = []
    for column_filters in grouped.values():
        predicates = [_predicate_for_filter(f) for f in column_filters]
        group_clauses.append(f"({' OR '.join(predicates)})")
        params.extend(f.value for f in column_filters)

    return " AND ".join(group_clauses), params


def _same_table_scope(
    table: str | None, scope_filters: list[Filter] | None
) -> tuple[str, list[str]]:
    """Build a scope WHERE fragment restricted to filters on the same table."""
    if not scope_filters or not table:
        return "", []
    relevant = [f for f in scope_filters if (f.table or table) == table]
    if not relevant:
        return "", []
    where, params = _build_grouped_where_clause(relevant)
    if not where:
        return "", []
    return f" AND {where}", params


def check_value_exists(
    con: duckdb.DuckDBPyConnection,
    filter_obj: Filter,
    scope_filters: list[Filter] | None = None,
) -> bool:
    """Check whether the filter's value exists in its column, scoped by parents."""
    table = filter_obj.table
    if not table:
        return True  # Without a table we cannot validate; assume OK.

    scope_sql, scope_params = _same_table_scope(table, scope_filters)
    op = filter_obj.operator.strip().upper()
    where = (
        f'"{filter_obj.column}" LIKE ?'
        if op == "LIKE"
        else f'"{filter_obj.column}" = ?'
    )
    query = f"SELECT 1 FROM {table} WHERE {where}{scope_sql} LIMIT 1"
    params = [filter_obj.value] + scope_params
    return con.execute(query, params).fetchone() is not None


def fetch_distinct_values(
    con: duckdb.DuckDBPyConnection,
    filter_obj: Filter,
    scope_filters: list[Filter] | None = None,
) -> list[str]:
    """Return all distinct non-null values for the filter's column, scoped."""
    table = filter_obj.table
    if not table:
        return []
    scope_sql, scope_params = _same_table_scope(table, scope_filters)
    column = filter_obj.column
    query = (
        f'SELECT DISTINCT "{column}" FROM {table} '
        f'WHERE "{column}" IS NOT NULL{scope_sql} '
        f'ORDER BY "{column}"'
    )
    rows = con.execute(query, scope_params).fetchall()
    return [str(r[0]) for r in rows]


def check_combination_has_results(
    con: duckdb.DuckDBPyConnection,
    filters: list[Filter],
) -> bool:
    """Return True if grouped filter combination matches at least one row.

    Filters from different tables are validated independently — if every
    per-table subset yields rows, the combination passes.
    """
    if not filters:
        return True

    by_table: dict[str, list[Filter]] = {}
    for f in filters:
        if not f.table:
            continue
        by_table.setdefault(f.table, []).append(f)

    for table, group in by_table.items():
        where, params = _build_grouped_where_clause(group)
        if not where:
            continue
        query = f"SELECT 1 FROM {table} WHERE {where} LIMIT 1"
        if con.execute(query, params).fetchone() is None:
            return False
    return True
