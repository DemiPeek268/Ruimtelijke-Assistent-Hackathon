"""Unit tests for app/services/query_runner.py."""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


class TestDuckDBQueryRunner:
    def test_execute_returns_columns_and_rows(self):
        from app.services.query_runner import DuckDBQueryRunner

        mock_cursor = MagicMock()
        mock_cursor.description = [("col_a",), ("col_b",)]
        mock_cursor.fetchall.return_value = [(1, "x"), (2, "y")]

        mock_con = MagicMock()
        mock_con.execute.return_value = mock_cursor

        with patch("app.services.helpers.db.duckdb.connect", return_value=mock_con):
            result = DuckDBQueryRunner().execute("SELECT col_a, col_b FROM t")

        assert result.columns == ["col_a", "col_b"]
        assert result.rows == [[1, "x"], [2, "y"]]
        mock_con.close.assert_called_once()

    def test_execute_handles_no_description(self):
        """A statement without a result-set (e.g. a DDL) yields empty columns."""
        from app.services.query_runner import DuckDBQueryRunner

        mock_cursor = MagicMock()
        mock_cursor.description = None
        mock_cursor.fetchall.return_value = []

        mock_con = MagicMock()
        mock_con.execute.return_value = mock_cursor

        with patch("app.services.helpers.db.duckdb.connect", return_value=mock_con):
            result = DuckDBQueryRunner().execute("CREATE TABLE foo (x INT)")

        assert result.columns == []
        assert result.rows == []


class TestBuildQueryRunner:
    def test_returns_duckdb_runner(self):
        from app.services.query_runner import DuckDBQueryRunner, build_query_runner

        runner = build_query_runner()
        assert isinstance(runner, DuckDBQueryRunner)

    def test_ignores_user_token_argument(self):
        from app.services.query_runner import DuckDBQueryRunner, build_query_runner

        runner = build_query_runner(user_token="some-token")
        assert isinstance(runner, DuckDBQueryRunner)
