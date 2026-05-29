"""Unit tests for static/pure helper methods in intent.py, validate_filters.py, workflow.py."""

import pytest
from app.models.dictionary import ColumnInfo, DataDictionary, TableInfo, Theme
from app.models.state import Filter, Intent, IntentAnalysis, SpatialQuery
from app.services.nodes.intent import (
    _correct_column_names,
    _get_valid_column_names,
)
from app.services.nodes.validate_filters import ValidateFiltersNode
from app.services.workflow import (
    route_after_intent,
    route_after_validation,
)

pytestmark = pytest.mark.unit


def _make_dictionary() -> DataDictionary:
    col_a = ColumnInfo(
        name="verkeer_totaal_2020",
        type="INTEGER",
        categorical=False,
        table="verkeer_tabel",
        group="Verkeer",
    )
    col_b = ColumnInfo(
        name="gemeente_Gemeentenaam",
        type="VARCHAR",
        categorical=True,
        table="gemeente_tabel",
        group="Gemeente",
    )
    tables = [
        TableInfo(name="verkeer_tabel", group="Verkeer", columns=[col_a]),
        TableInfo(name="gemeente_tabel", group="Gemeente", columns=[col_b]),
    ]
    theme = Theme(name="test", label="Test", tables=tables)
    return DataDictionary(total_rows=100, total_columns=2, themes=[theme])


def _make_intent(filters=None, spatial_query=None) -> Intent:
    return Intent(
        description="test",
        relevant_columns=["h3_id"],
        filters=filters or [],
        spatial_query=spatial_query,
    )


class TestGetValidColumnNames:
    def test_returns_all_column_names(self):
        dictionary = _make_dictionary()
        result = _get_valid_column_names(dictionary)
        assert "verkeer_totaal_2020" in result
        assert "gemeente_Gemeentenaam" in result

    def test_returns_set(self):
        dictionary = _make_dictionary()
        result = _get_valid_column_names(dictionary)
        assert isinstance(result, set)

    def test_empty_dictionary(self):
        dictionary = DataDictionary(total_rows=0, total_columns=0, themes=[])
        result = _get_valid_column_names(dictionary)
        assert result == set()


class TestCorrectColumnNames:
    def test_valid_column_kept_as_is(self):
        valid = {"verkeer_totaal_2020", "gemeente_Gemeentenaam"}
        result = _correct_column_names(["verkeer_totaal_2020"], valid)
        assert result == ["verkeer_totaal_2020"]

    def test_close_match_corrected(self):
        valid = {"verkeer_totaal_2020", "gemeente_Gemeentenaam"}
        result = _correct_column_names(["verkeer_totaal_20200"], valid)
        assert "verkeer_totaal_2020" in result

    def test_no_match_dropped(self):
        valid = {"verkeer_totaal_2020", "gemeente_Gemeentenaam"}
        result = _correct_column_names(["xyz_nonexistent_col"], valid)
        assert "xyz_nonexistent_col" not in result

    def test_empty_input_returns_empty(self):
        valid = {"verkeer_totaal_2020"}
        result = _correct_column_names([], valid)
        assert result == []

    def test_multiple_columns_all_checked(self):
        valid = {"verkeer_totaal_2020", "gemeente_Gemeentenaam"}
        result = _correct_column_names(
            ["verkeer_totaal_2020", "gemeente_Gemeentenaam"], valid
        )
        assert "verkeer_totaal_2020" in result
        assert "gemeente_Gemeentenaam" in result


class TestValidateFiltersNodeStaticHelpers:
    def test_get_categorical_columns(self):
        dictionary = _make_dictionary()
        result = ValidateFiltersNode._get_categorical_columns(dictionary)
        assert ("gemeente_tabel", "gemeente_Gemeentenaam") in result
        assert ("verkeer_tabel", "verkeer_totaal_2020") not in result

    def test_get_origin_categorical_filters_no_spatial_query(self):
        intent = _make_intent()
        result = ValidateFiltersNode._get_origin_categorical_filters(
            intent, {"gemeente_Gemeentenaam"}
        )
        assert result == []

    def test_get_origin_categorical_filters_with_spatial_query(self):
        origin_filters = [
            Filter(column="gemeente_Gemeentenaam", operator="=", value="Delft"),
            Filter(column="verkeer_totaal_2020", operator=">", value="100"),
        ]
        intent = _make_intent(
            spatial_query=SpatialQuery(origin_filters=origin_filters, k_rings=5)
        )

        def is_categorical(f):
            return f.column == "gemeente_Gemeentenaam"

        result = ValidateFiltersNode._get_origin_categorical_filters(
            intent, is_categorical
        )
        assert len(result) == 1
        assert result[0].column == "gemeente_Gemeentenaam"


class TestWorkflowRouting:
    def test_route_after_intent_clear(self):
        state = {
            "needs_spatial_resolution": False,
            "intent_analysis": IntentAnalysis(
                is_clear=True,
                intent=_make_intent(),
            ),
        }
        result = route_after_intent(state)
        assert result == "validate_filters"

    def test_route_after_intent_spatial_resolution_needed(self):
        state = {
            "needs_spatial_resolution": True,
            "intent_analysis": IntentAnalysis(
                is_clear=True,
                intent=_make_intent(
                    spatial_query=SpatialQuery(
                        origin_filters=[
                            Filter(
                                column="h3_spatial_filter",
                                operator="=",
                                value="PLACE:Rotterdam Centraal",
                            )
                        ],
                        k_rings=6,
                    )
                ),
            ),
        }
        result = route_after_intent(state)
        assert result == "resolve_spatial"

    def test_route_after_intent_not_clear(self):
        state = {
            "needs_spatial_resolution": False,
            "intent_analysis": IntentAnalysis(
                is_clear=False,
                follow_up_question="Welke kolom?",
            ),
        }
        result = route_after_intent(state)
        from langgraph.graph import END

        assert result == END

    def test_route_after_intent_none_analysis(self):
        state = {"intent_analysis": None, "needs_spatial_resolution": False}
        result = route_after_intent(state)
        from langgraph.graph import END

        assert result == END

    def test_route_after_validation_clear(self):
        state = {
            "intent_analysis": IntentAnalysis(
                is_clear=True,
                intent=_make_intent(),
            )
        }
        result = route_after_validation(state)
        assert result == "generate_sql"

    def test_route_after_validation_not_clear(self):
        state = {
            "intent_analysis": IntentAnalysis(
                is_clear=False,
                follow_up_question="Welke waarde?",
            )
        }
        result = route_after_validation(state)
        from langgraph.graph import END

        assert result == END

    def test_route_after_intent_ignores_spatial_intent_without_flag(self):
        state = {
            "needs_spatial_resolution": False,
            "intent_analysis": IntentAnalysis(
                is_clear=True,
                intent=_make_intent(
                    spatial_query=SpatialQuery(
                        origin_filters=[
                            Filter(
                                column="h3_spatial_filter",
                                operator="=",
                                value="LATLON:51.905000,4.488000",
                            )
                        ],
                        k_rings=3,
                    )
                ),
            ),
        }
        assert route_after_intent(state) == "validate_filters"
