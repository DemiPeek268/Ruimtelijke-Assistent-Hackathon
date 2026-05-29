"""Unit tests for ExecuteQueryNode — connect_delta is mocked."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.nodes.execute_query import ExecuteQueryNode

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skip(
        reason="Mocks _load_metadata / normalized-column helpers and build_joined_sql, "
        "all removed in the data/ multi-table migration. Needs rewrite."
    ),
]


def _make_con_mock(count: int, columns=None, numeric_cols=None):
    """
    Create a MagicMock DuckDB connection that responds to common queries.

    count         : number of rows to return from COUNT query
    columns       : list of (col_name, col_type) for information_schema query
    numeric_cols  : list of col names that should get MIN/MAX/AVG stats
    """
    if columns is None:
        columns = [("h3_id", "VARCHAR"), ("value", "INTEGER")]
    if numeric_cols is None:
        numeric_cols = ["value"]

    def execute_side_effect(query, params=None):
        mock = MagicMock()
        if "SELECT COUNT" in query:
            mock.fetchone.return_value = (count,)
        elif "information_schema.columns" in query:
            mock.fetchall.return_value = columns
        elif "MIN(" in query or "MAX(" in query:
            mock.fetchone.return_value = (0, 255, 127.5)
        else:
            # SELECT * queries → return rows based on count
            rows = [("abc123", 42)] * min(count, 15)
            mock.fetchall.return_value = rows
            mock.description = [("h3_id",), ("value",)]
        return mock

    con = MagicMock()
    con.execute.side_effect = execute_side_effect
    return con


def _mock_connect_delta(con_mock):
    """Return a context manager mock that yields con_mock."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=con_mock)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


def _make_metadata() -> dict:
    """Mock metadata with a mix of normalized and non-normalized columns."""
    return {
        "kolommen": {
            "verkeer_totaal_2020": {"genormaliseerd": True},
            "geluid_2020_value_mean": {"genormaliseerd": True},
            "gemeente_Gemeentenaam": {"genormaliseerd": False},
            "h3_id": {},
        },
    }


def _make_node_with_metadata(tmp_path, metadata: dict) -> ExecuteQueryNode:
    """Create an ExecuteQueryNode whose normalized-col lookup uses the given metadata."""
    with patch(
        "app.services.nodes.execute_query._load_metadata", return_value=metadata
    ):
        return ExecuteQueryNode()


class TestRowsToDicts:
    def test_converts_cursor_result_to_dicts(self):
        cursor = MagicMock()
        cursor.description = [("h3_id",), ("value",)]
        cursor.fetchall.return_value = [("abc123", 42), ("def456", 17)]

        node = ExecuteQueryNode()
        result = node._rows_to_dicts(cursor)

        assert len(result) == 2
        assert result[0] == {"h3_id": "abc123", "value": 42}
        assert result[1] == {"h3_id": "def456", "value": 17}

    def test_empty_cursor_returns_empty_list(self):
        cursor = MagicMock()
        cursor.description = [("h3_id",)]
        cursor.fetchall.return_value = []

        node = ExecuteQueryNode()
        result = node._rows_to_dicts(cursor)

        assert result == []

    def test_single_column(self):
        cursor = MagicMock()
        cursor.description = [("h3_id",)]
        cursor.fetchall.return_value = [("abc123",)]

        node = ExecuteQueryNode()
        result = node._rows_to_dicts(cursor)

        assert result == [{"h3_id": "abc123"}]


class TestExecuteQueryMethod:
    def test_empty_result_returns_empty_tuple(self):
        con_mock = _make_con_mock(count=0)
        node = ExecuteQueryNode()
        state = {"intent_analysis": None}

        with patch(
            "app.services.nodes.execute_query.connect_delta",
            return_value=_mock_connect_delta(con_mock),
        ):
            sample, count, summary, all_rows = node._execute_query(
                "SELECT * FROM dataset", state
            )

        assert sample == []
        assert count == 0
        assert summary is None
        assert all_rows == []

    def test_small_result_returns_all_rows(self):
        con_mock = _make_con_mock(count=5)
        node = ExecuteQueryNode()
        state = {"intent_analysis": None}

        with patch(
            "app.services.nodes.execute_query.connect_delta",
            return_value=_mock_connect_delta(con_mock),
        ):
            sample, count, summary, all_rows = node._execute_query(
                "SELECT * FROM dataset", state
            )

        assert count == 5
        assert summary is None

    def test_large_result_returns_sample_and_summary(self):
        con_mock = _make_con_mock(count=150)
        node = ExecuteQueryNode()
        state = {"intent_analysis": None}

        with patch(
            "app.services.nodes.execute_query.connect_delta",
            return_value=_mock_connect_delta(con_mock),
        ):
            sample, count, summary, all_rows = node._execute_query(
                "SELECT * FROM dataset", state
            )

        assert count == 150
        assert summary is not None
        assert "value" in summary

    def test_strips_trailing_semicolons(self):
        con_mock = _make_con_mock(count=0)
        node = ExecuteQueryNode()
        state = {"intent_analysis": None}

        with patch(
            "app.services.nodes.execute_query.connect_delta",
            return_value=_mock_connect_delta(con_mock),
        ):
            node._execute_query("SELECT * FROM dataset;", state)
            # Find the CREATE TEMP TABLE call and verify the SQL has no semicolons
            temp_call = next(
                c
                for c in con_mock.execute.call_args_list
                if "CREATE TEMP TABLE" in str(c)
            )
            query_arg = temp_call[0][0]  # first positional arg
            sql_part = query_arg.split("CREATE TEMP TABLE _results AS ", 1)[1]
            assert not sql_part.rstrip().endswith(";")

    def test_non_numeric_columns_excluded_from_summary(self):
        con_mock = _make_con_mock(
            count=150,
            columns=[("h3_id", "VARCHAR"), ("value", "INTEGER")],
        )
        node = ExecuteQueryNode()
        state = {"intent_analysis": None}

        with patch(
            "app.services.nodes.execute_query.connect_delta",
            return_value=_mock_connect_delta(con_mock),
        ):
            _, _, summary, _ = node._execute_query("SELECT * FROM dataset", state)

        assert summary is not None
        assert "h3_id" not in summary
        assert "value" in summary

    def test_h3_load_exception_triggers_install(self):
        """If LOAD h3 fails, should INSTALL then LOAD."""
        con_mock = MagicMock()
        load_calls = []

        def execute_side_effect(query, params=None):
            load_calls.append(query)
            if (
                query == "LOAD h3;"
                and len([c for c in load_calls if c == "LOAD h3;"]) == 1
            ):
                raise Exception("h3 not installed")
            m = MagicMock()
            if "SELECT COUNT" in query:
                m.fetchone.return_value = (0,)
            else:
                m.fetchall.return_value = []
                m.description = []
            return m

        con_mock.execute.side_effect = execute_side_effect
        node = ExecuteQueryNode()
        state = {"intent_analysis": None}

        with patch(
            "app.services.nodes.execute_query.connect_delta",
            return_value=_mock_connect_delta(con_mock),
        ):
            node._execute_query("SELECT * FROM dataset", state)

        # Should have called INSTALL h3
        assert any("INSTALL h3" in c for c in load_calls)


class TestIsColumnCategorical:
    def test_varchar_column_is_categorical(self):
        con = MagicMock()
        con.execute.return_value.fetchone.return_value = ("VARCHAR",)
        node = ExecuteQueryNode()

        assert node._is_column_categorical(con, "category_col") is True

    def test_integer_column_is_not_categorical(self):
        con = MagicMock()
        con.execute.return_value.fetchone.return_value = ("INTEGER",)
        node = ExecuteQueryNode()

        assert node._is_column_categorical(con, "value_col") is False

    def test_missing_column_is_not_categorical(self):
        con = MagicMock()
        con.execute.return_value.fetchone.return_value = None
        node = ExecuteQueryNode()

        assert node._is_column_categorical(con, "missing") is False


class TestPickAggregationValueColumn:
    def test_picks_first_non_h3_non_level_column(self):
        result = ExecuteQueryNode._pick_aggregation_value_column(
            ["h3_id", "gemeentenaam", "woningen_sum"], "gemeentenaam"
        )
        assert result == "woningen_sum"

    def test_skips_year_int(self):
        result = ExecuteQueryNode._pick_aggregation_value_column(
            ["h3_id", "year_int", "gemeentenaam", "value"], "gemeentenaam"
        )
        assert result == "value"

    def test_returns_none_when_no_candidate(self):
        result = ExecuteQueryNode._pick_aggregation_value_column(
            ["h3_id", "gemeentenaam"], "gemeentenaam"
        )
        assert result is None


class TestSampleAggregation:
    def _make_cursor(self, rows, columns):
        cursor = MagicMock()
        cursor.description = [(col,) for col in columns]
        cursor.fetchall.return_value = rows
        return cursor

    def test_numeric_query_contains_round_and_desc(self):
        node = ExecuteQueryNode()
        con = MagicMock()
        con.execute.return_value = self._make_cursor(
            [("Amsterdam", 42.56)], ["gemeentenaam", "value"]
        )

        node._sample_aggregation(con, "gemeentenaam", "value", is_categorical=False)

        query = con.execute.call_args[0][0]
        assert "ROUND" in query
        assert "DESC" in query

    def test_numeric_query_returns_rows_as_dicts(self):
        node = ExecuteQueryNode()
        con = MagicMock()
        con.execute.return_value = self._make_cursor(
            [("Amsterdam", 42.56)], ["gemeentenaam", "value"]
        )

        result = node._sample_aggregation(
            con, "gemeentenaam", "value", is_categorical=False
        )

        assert result == [{"gemeentenaam": "Amsterdam", "value": 42.56}]

    def test_categorical_query_uses_distinct_without_round(self):
        node = ExecuteQueryNode()
        con = MagicMock()
        con.execute.return_value = self._make_cursor(
            [("Amsterdam", "bos")], ["gemeentenaam", "lgn_cat"]
        )

        node._sample_aggregation(con, "gemeentenaam", "lgn_cat", is_categorical=True)

        query = con.execute.call_args[0][0]
        assert "DISTINCT" in query
        assert "ROUND" not in query
        assert "DESC" not in query

    def test_categorical_query_orders_by_level_col(self):
        node = ExecuteQueryNode()
        con = MagicMock()
        con.execute.return_value = self._make_cursor(
            [("Amsterdam", "bos"), ("Rotterdam", "water")],
            ["gemeentenaam", "lgn_cat"],
        )

        node._sample_aggregation(con, "gemeentenaam", "lgn_cat", is_categorical=True)

        query = con.execute.call_args[0][0]
        assert 'ORDER BY "gemeentenaam"' in query


class TestExecuteQueryNodeRun:
    async def test_no_sql_query_returns_error(self):
        node = ExecuteQueryNode()
        state = {"sql_query": None}

        with patch(
            "app.services.nodes.base.adispatch_custom_event", new_callable=AsyncMock
        ):
            state_update = await node.run(state, {})

        assert state_update["query_result"].error == "Geen SQL query gegenereerd"

    async def test_successful_execution_returns_results(self):
        node = ExecuteQueryNode()
        state = {"sql_query": "SELECT * FROM dataset"}

        with (
            patch.object(
                node,
                "_execute_query",
                return_value=(
                    [{"h3_id": "abc", "value": 42}],
                    1,
                    None,
                    [{"h3_id": "abc", "value": 42}],
                ),
            ),
            patch(
                "app.services.nodes.base.adispatch_custom_event", new_callable=AsyncMock
            ),
        ):
            state_update = await node.run(state, {})

        assert state_update["query_result"].count == 1
        assert state_update["query_result"].error is None

    async def test_exception_returns_error_state(self):
        node = ExecuteQueryNode()
        state = {"sql_query": "SELECT * FROM dataset"}

        with (
            patch.object(node, "_execute_query", side_effect=Exception("query failed")),
            patch(
                "app.services.nodes.base.adispatch_custom_event", new_callable=AsyncMock
            ),
        ):
            state_update = await node.run(state, {})

        assert "query failed" in state_update["query_result"].error

    async def test_dispatches_map_data_when_rows_present(self):
        node = ExecuteQueryNode()
        state = {"sql_query": "SELECT * FROM dataset"}
        dispatched = []

        async def capture(name, data, config=None):
            dispatched.append(name)

        with (
            patch.object(
                node,
                "_execute_query",
                return_value=([{"h3_id": "abc"}], 1, None, [{"h3_id": "abc"}]),
            ),
            patch(
                "app.services.nodes.base.adispatch_custom_event", side_effect=capture
            ),
        ):
            await node.run(state, {})

        assert "map_data" in dispatched


# ---------------------------------------------------------------------------
# Tests for normalization helpers
# ---------------------------------------------------------------------------


class TestLoadNormalizedColNames:
    def test_returns_normalized_column_names(self, tmp_path):
        metadata = _make_metadata()
        node = _make_node_with_metadata(tmp_path, metadata)

        result = node._normalized_col_names

        assert result == {"verkeer_totaal_2020", "geluid_2020_value_mean"}

    def test_no_normalized_columns_returns_empty_set(self, tmp_path):
        metadata = {
            "kolommen": {
                "gemeentenaam": {"genormaliseerd": False},
                "h3_id": {},
            },
        }
        node = _make_node_with_metadata(tmp_path, metadata)

        assert node._normalized_col_names == set()

    def test_all_columns_normalized(self, tmp_path):
        metadata = {
            "kolommen": {
                "col_a": {"genormaliseerd": True},
                "col_b": {"genormaliseerd": True},
            },
        }
        node = _make_node_with_metadata(tmp_path, metadata)

        assert node._normalized_col_names == {"col_a", "col_b"}

    def test_genormaliseerd_falsy_values_excluded(self, tmp_path):
        metadata = {
            "kolommen": {
                "col_none": {"genormaliseerd": None},
                "col_zero": {"genormaliseerd": 0},
                "col_empty": {"genormaliseerd": ""},
                "col_true": {"genormaliseerd": True},
            },
        }
        node = _make_node_with_metadata(tmp_path, metadata)

        assert node._normalized_col_names == {"col_true"}

    def test_empty_kolommen_dict_returns_empty_set(self, tmp_path):
        node = _make_node_with_metadata(tmp_path, {"kolommen": {}})

        assert node._normalized_col_names == set()

    def test_genormaliseerd_truthy_non_bool_values_included(self, tmp_path):
        metadata = {
            "kolommen": {
                "col_int": {"genormaliseerd": 1},
                "col_str": {"genormaliseerd": "yes"},
            },
        }
        node = _make_node_with_metadata(tmp_path, metadata)

        assert node._normalized_col_names == {"col_int", "col_str"}


class TestGetNormalizedResultColumns:
    def test_returns_matching_columns(self, tmp_path):
        node = _make_node_with_metadata(tmp_path, _make_metadata())

        result = node._get_normalized_result_columns(
            ["verkeer_totaal_2020", "gemeente_Gemeentenaam", "geluid_2020_value_mean"]
        )

        assert result == ["verkeer_totaal_2020", "geluid_2020_value_mean"]

    def test_preserves_input_order(self, tmp_path):
        node = _make_node_with_metadata(tmp_path, _make_metadata())

        result = node._get_normalized_result_columns(
            ["geluid_2020_value_mean", "gemeente_Gemeentenaam", "verkeer_totaal_2020"]
        )

        assert result == ["geluid_2020_value_mean", "verkeer_totaal_2020"]

    def test_no_matches_returns_empty_list(self, tmp_path):
        node = _make_node_with_metadata(tmp_path, _make_metadata())

        result = node._get_normalized_result_columns(["gemeente_Gemeentenaam", "h3_id"])

        assert result == []

    def test_empty_result_columns_returns_empty_list(self, tmp_path):
        node = _make_node_with_metadata(tmp_path, _make_metadata())

        result = node._get_normalized_result_columns([])

        assert result == []

    def test_case_sensitive_match(self, tmp_path):
        node = _make_node_with_metadata(tmp_path, _make_metadata())

        result = node._get_normalized_result_columns(
            ["Woningen_Count", "BEVOLKING_INDEX"]
        )

        assert result == []

    def test_all_result_columns_are_normalized(self, tmp_path):
        node = _make_node_with_metadata(tmp_path, _make_metadata())

        result = node._get_normalized_result_columns(
            ["verkeer_totaal_2020", "geluid_2020_value_mean"]
        )

        assert result == ["verkeer_totaal_2020", "geluid_2020_value_mean"]


class TestConvertNormalizedColumns:
    def test_executes_update_for_each_column(self, tmp_path):
        node = _make_node_with_metadata(tmp_path, _make_metadata())
        con = MagicMock()

        node._convert_normalized_columns(con, ["col_a", "col_b"])

        assert con.execute.call_count == 2
        con.execute.assert_any_call(
            'UPDATE _results SET "col_a" = ROUND("col_a" * 100.0 / 255)'
        )
        con.execute.assert_any_call(
            'UPDATE _results SET "col_b" = ROUND("col_b" * 100.0 / 255)'
        )

    def test_empty_list_executes_nothing(self, tmp_path):
        node = _make_node_with_metadata(tmp_path, _make_metadata())
        con = MagicMock()

        node._convert_normalized_columns(con, [])

        con.execute.assert_not_called()

    def test_column_names_are_quoted(self, tmp_path):
        node = _make_node_with_metadata(tmp_path, _make_metadata())
        con = MagicMock()

        node._convert_normalized_columns(con, ["col with spaces"])

        con.execute.assert_called_once_with(
            'UPDATE _results SET "col with spaces" = ROUND("col with spaces" * 100.0 / 255)'
        )

    def test_single_column(self, tmp_path):
        node = _make_node_with_metadata(tmp_path, _make_metadata())
        con = MagicMock()

        node._convert_normalized_columns(con, ["only_col"])

        con.execute.assert_called_once_with(
            'UPDATE _results SET "only_col" = ROUND("only_col" * 100.0 / 255)'
        )

    def test_execution_order_matches_input_order(self, tmp_path):
        node = _make_node_with_metadata(tmp_path, _make_metadata())
        con = MagicMock()

        node._convert_normalized_columns(con, ["alpha", "beta", "gamma"])

        calls = [c.args[0] for c in con.execute.call_args_list]
        assert '"alpha"' in calls[0]
        assert '"beta"' in calls[1]
        assert '"gamma"' in calls[2]

    def test_large_column_list_executes_n_times(self, tmp_path):
        node = _make_node_with_metadata(tmp_path, _make_metadata())
        con = MagicMock()

        node._convert_normalized_columns(con, [f"col_{i}" for i in range(10)])

        assert con.execute.call_count == 10


class TestCategoricalSummary:
    """Tests for the categorical column stats path in _execute_query (added in c4e3868)."""

    def _make_categorical_con_mock(
        self,
        count: int = 150,
        non_null_count: int = 150,
        cat_col: str = "gemeente_Gemeentenaam",
    ):
        """Mock that includes a VARCHAR column (non-h3_id) to exercise the categorical path."""
        cols_only = [("h3_id",), (cat_col,), ("value",)]
        cols_with_types = [
            ("h3_id", "VARCHAR"),
            (cat_col, "VARCHAR"),
            ("value", "INTEGER"),
        ]

        def execute_side_effect(query, params=None):
            mock = MagicMock()
            q = query
            if params is not None:
                mock.fetchone.return_value = None
            elif "data_type" in q and "information_schema" in q:
                mock.fetchall.return_value = cols_with_types
            elif "information_schema" in q:
                mock.fetchall.return_value = cols_only
            elif "COUNT(DISTINCT" in q:
                mock.fetchone.return_value = (8,)
            elif "COUNT(*)" in q and "IS NOT NULL" in q:
                mock.fetchone.return_value = (non_null_count,)
            elif "COUNT(*)" in q:
                mock.fetchone.return_value = (count,)
            elif "GROUP BY" in q:
                mock.fetchall.return_value = [
                    ("Leiden", 80),
                    ("Delft", 65),
                    ("Gouda", 42),
                ]
            elif "MIN(" in q:
                mock.fetchone.return_value = (0, 255, 127.5)
            elif "USING SAMPLE" in q:
                rows = [("abc123", "Leiden", 42)] * 10
                mock.fetchall.return_value = rows
                mock.description = [("h3_id",), (cat_col,), ("value",)]
            elif "SELECT *" in q:
                rows = [("abc123", "Leiden", 42)] * min(count, 15)
                mock.fetchall.return_value = rows
                mock.description = [("h3_id",), (cat_col,), ("value",)]
            else:
                mock.fetchall.return_value = []
                mock.fetchone.return_value = None
                mock.description = []
            return mock

        con = MagicMock()
        con.execute.side_effect = execute_side_effect
        return con

    def test_varchar_column_gets_top_values_stats(self):
        node = ExecuteQueryNode()
        con_mock = self._make_categorical_con_mock(count=150, non_null_count=150)
        state = {"intent_analysis": None}

        with patch(
            "app.services.nodes.execute_query.connect_delta",
            return_value=_mock_connect_delta(con_mock),
        ):
            _, _, summary, _ = node._execute_query("SELECT * FROM dataset", state)

        assert summary is not None
        assert "gemeente_Gemeentenaam" in summary
        cat_stats = summary["gemeente_Gemeentenaam"]
        assert "top_values" in cat_stats
        assert "non_null_count" in cat_stats
        assert "distinct_count" in cat_stats

    def test_null_only_categorical_column_excluded_from_summary(self):
        node = ExecuteQueryNode()
        con_mock = self._make_categorical_con_mock(count=150, non_null_count=0)
        state = {"intent_analysis": None}

        with patch(
            "app.services.nodes.execute_query.connect_delta",
            return_value=_mock_connect_delta(con_mock),
        ):
            _, _, summary, _ = node._execute_query("SELECT * FROM dataset", state)

        assert summary is not None
        assert "gemeente_Gemeentenaam" not in summary
        assert "value" in summary
