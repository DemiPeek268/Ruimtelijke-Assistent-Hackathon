from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.services.helpers.db import connect_delta


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list]


class QueryRunner(Protocol):
    def execute(self, sql: str) -> QueryResult: ...


class DuckDBQueryRunner:
    """Runs SQL via DuckDB with the Delta extension loaded."""

    def execute(self, sql: str) -> QueryResult:
        with connect_delta() as con:
            cursor = con.execute(sql)
            columns = [d[0] for d in cursor.description] if cursor.description else []
            rows = [list(r) for r in cursor.fetchall()]
        return QueryResult(columns=columns, rows=rows)


def build_query_runner(user_token: str | None = None) -> QueryRunner:
    return DuckDBQueryRunner()
