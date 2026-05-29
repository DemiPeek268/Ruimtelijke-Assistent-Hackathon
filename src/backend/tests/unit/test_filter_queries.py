"""Unit tests for filter_queries.py — all DB calls are mocked."""

import pytest
from unittest.mock import MagicMock
from app.models.state import Filter
from app.services.helpers.filter_queries import (
    check_combination_has_results,
    check_value_exists,
    fetch_distinct_values,
)

pytestmark = pytest.mark.unit


def _make_filter(
    column: str, value: str, operator: str = "=", table: str | None = None
) -> Filter:
    return Filter(column=column, operator=operator, value=value, table=table)


def _mock_con(fetchone="UNSET", fetchall=None):
    """Return a MagicMock DuckDB connection with preconfigured return values."""
    con = MagicMock()
    if fetchone != "UNSET":
        con.execute.return_value.fetchone.return_value = fetchone
    if fetchall is not None:
        con.execute.return_value.fetchall.return_value = fetchall
    return con


class TestCheckValueExists:
    def test_returns_true_when_row_found(self):
        con = _mock_con(fetchone=(1,))
        filter_obj = Filter(
            column="gemeente_Gemeentenaam",
            operator="=",
            value="Amsterdam",
            table="gemeente",
        )
        result = check_value_exists(con, filter_obj)
        assert result is True

    def test_returns_false_when_no_row(self):
        con = _mock_con(fetchone=None)  # fetchone returns None → value not found
        filter_obj = Filter(
            column="gemeente_Gemeentenaam",
            operator="=",
            value="Nonexistent",
            table="gemeente",
        )
        result = check_value_exists(con, filter_obj)
        assert result is False

    def test_uses_like_operator(self):
        con = _mock_con(fetchone=(1,))
        filter_obj = Filter(
            column="gemeente_Gemeentenaam",
            operator="LIKE",
            value="%delft%",
            table="gemeente",
        )
        check_value_exists(con, filter_obj)
        call_args = con.execute.call_args
        query = call_args[0][0]
        assert "LIKE" in query

    def test_uses_eq_operator_by_default(self):
        con = _mock_con(fetchone=(1,))
        filter_obj = Filter(
            column="gemeente_Gemeentenaam",
            operator="=",
            value="Delft",
            table="gemeente",
        )
        check_value_exists(con, filter_obj)
        call_args = con.execute.call_args
        query = call_args[0][0]
        assert "=" in query

    def test_with_scope_filters(self):
        con = _mock_con(fetchone=(1,))
        scope = [_make_filter("gemeente_Gemeentenaam", "Delft", table="gemeente")]
        filter_obj = Filter(
            column="gemeente_Code", operator="=", value="Centrum", table="gemeente"
        )
        result = check_value_exists(con, filter_obj, scope_filters=scope)
        assert result is True
        call_args = con.execute.call_args
        query = call_args[0][0]
        # Scope filter should appear in the query
        assert "gemeente_Gemeentenaam" in query

    def test_with_like_scope_filter(self):
        con = _mock_con(fetchone=(1,))
        scope = [
            _make_filter(
                "gemeente_Gemeentenaam", "Delft", operator="LIKE", table="gemeente"
            )
        ]
        filter_obj = Filter(
            column="gemeente_Code", operator="=", value="Centrum", table="gemeente"
        )
        check_value_exists(con, filter_obj, scope_filters=scope)
        query = con.execute.call_args[0][0]
        assert "LIKE" in query


class TestFetchDistinctValues:
    def test_returns_string_list(self):
        con = _mock_con(fetchall=[("Amsterdam",), ("Rotterdam",), ("Delft",)])
        filter_obj = Filter(
            column="gemeente_Gemeentenaam", operator="=", value="", table="gemeente"
        )
        result = fetch_distinct_values(con, filter_obj)
        assert result == ["Amsterdam", "Rotterdam", "Delft"]

    def test_empty_result_returns_empty_list(self):
        con = _mock_con(fetchall=[])
        filter_obj = Filter(
            column="gemeente_Gemeentenaam", operator="=", value="", table="gemeente"
        )
        result = fetch_distinct_values(con, filter_obj)
        assert result == []

    def test_with_scope_filters(self):
        con = _mock_con(fetchall=[("Binnenstad",), ("Noord",)])
        scope = [_make_filter("gemeente_Gemeentenaam", "Delft", table="gemeente")]
        filter_obj = Filter(
            column="gemeente_Code", operator="=", value="", table="gemeente"
        )
        result = fetch_distinct_values(con, filter_obj, scope_filters=scope)
        assert "Binnenstad" in result
        call_args = con.execute.call_args
        query = call_args[0][0]
        assert "gemeente_Gemeentenaam" in query

    def test_converts_values_to_string(self):
        con = _mock_con(fetchall=[(2023,), (2022,)])
        filter_obj = Filter(
            column="verkeer_totaal_2020", operator="=", value="", table="verkeer"
        )
        result = fetch_distinct_values(con, filter_obj)
        assert result == ["2023", "2022"]

    def test_multiple_scope_filters_same_column(self):
        con = _mock_con(fetchall=[("Centrum",)])
        scope = [
            _make_filter("gemeente_Gemeentenaam", "Delft", table="gemeente"),
            _make_filter("gemeente_Gemeentenaam", "Leiden", table="gemeente"),
        ]
        filter_obj = Filter(
            column="gemeente_Code", operator="=", value="", table="gemeente"
        )
        result = fetch_distinct_values(con, filter_obj, scope_filters=scope)
        assert result == ["Centrum"]
        query = con.execute.call_args[0][0]
        assert "OR" in query


class TestCheckCombinationHasResults:
    def test_empty_filters_returns_true(self):
        con = MagicMock()
        result = check_combination_has_results(con, [])
        assert result is True
        con.execute.assert_not_called()

    def test_returns_true_when_row_found(self):
        con = _mock_con(fetchone=(1,))
        filters = [_make_filter("gemeente_Gemeentenaam", "Delft")]
        result = check_combination_has_results(con, filters)
        assert result is True

    def test_returns_false_when_no_row(self):
        con = _mock_con(fetchone=None)  # fetchone returns None → no matching rows
        filters = [
            _make_filter("gemeente_Gemeentenaam", "Delft", table="gemeente"),
            _make_filter("gemeente_Code", "Nonexistent", table="gemeente"),
        ]
        result = check_combination_has_results(con, filters)
        assert result is False

    def test_multiple_filters_different_columns_and_logic(self):
        con = _mock_con(fetchone=(1,))
        filters = [
            _make_filter("gemeente_Gemeentenaam", "Delft", table="gemeente"),
            _make_filter("gemeente_Code", "Centrum", table="gemeente"),
        ]
        check_combination_has_results(con, filters)
        query = con.execute.call_args[0][0]
        # Different columns in same table should be ANDed
        assert "AND" in query

    def test_multiple_filters_same_column_or_logic(self):
        con = _mock_con(fetchone=(1,))
        filters = [
            _make_filter("gemeente_Gemeentenaam", "Delft", table="gemeente"),
            _make_filter("gemeente_Gemeentenaam", "Leiden", table="gemeente"),
        ]
        check_combination_has_results(con, filters)
        query = con.execute.call_args[0][0]
        assert "OR" in query
