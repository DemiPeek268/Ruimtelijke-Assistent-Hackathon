"""Unit tests for filter_validation.py — filter_queries calls are mocked."""

import pytest
from unittest.mock import MagicMock, patch
from app.models.state import Filter
from app.services.helpers.filter_validation import (
    _build_scope,
    _validate_combination_phase,
    _validate_individual_phase,
    collect_invalid_filters,
)

pytestmark = pytest.mark.unit


def _make_filter(column: str, value: str, operator: str = "=") -> Filter:
    return Filter(column=column, operator=operator, value=value)


class TestBuildScope:
    def test_location_column_has_no_parents_returns_empty_scope(self):
        validated = {
            "gemeente_Code": [_make_filter("gemeente_Code", "GM0503")],
            "verkeer_totaal_2020": [_make_filter("verkeer_totaal_2020", "100")],
        }
        # gemeente_Gemeentenaam has no parents → scope is always []
        scope = _build_scope(_make_filter("gemeente_Gemeentenaam", "Delft"), validated)
        assert scope == []

    def test_non_location_column_scoped_to_all_location_filters(self):
        validated = {
            "gemeente_Gemeentenaam": [_make_filter("gemeente_Gemeentenaam", "Delft")],
            "verkeer_totaal_2020": [_make_filter("verkeer_totaal_2020", "100")],
        }
        scope = _build_scope(_make_filter("some_other_col", "value"), validated)
        columns = [f.column for f in scope]
        assert "gemeente_Gemeentenaam" in columns
        assert "verkeer_totaal_2020" not in columns

    def test_gemeente_has_no_parent_scope(self):
        validated = {
            "gemeente_Code": [_make_filter("gemeente_Code", "GM0503")],
        }
        scope = _build_scope(_make_filter("gemeente_Gemeentenaam", "Delft"), validated)
        assert scope == []

    def test_empty_validated_returns_empty_scope(self):
        scope = _build_scope(_make_filter("gemeente_Gemeentenaam", "Delft"), {})
        assert scope == []


class TestValidateIndividualPhase:
    def test_all_valid_returns_empty(self):
        con = MagicMock()
        filters = [_make_filter("gemeente_Gemeentenaam", "Delft")]
        validated = {}

        with patch(
            "app.services.helpers.filter_validation.check_value_exists",
            return_value=True,
        ):
            result = _validate_individual_phase(con, filters, validated)

        assert result == []
        assert "gemeente_Gemeentenaam" in validated

    def test_invalid_filter_returned(self):
        con = MagicMock()
        filters = [_make_filter("gemeente_Gemeentenaam", "Delftt")]
        validated = {}

        with (
            patch(
                "app.services.helpers.filter_validation.check_value_exists",
                return_value=False,
            ),
            patch(
                "app.services.helpers.filter_validation.build_candidates_for_filter",
                return_value=["Delft"],
            ),
        ):
            result = _validate_individual_phase(con, filters, validated)

        assert len(result) == 1
        assert result[0].attempted_value == "Delftt"
        assert "Delft" in result[0].candidates


class TestValidateCombinationPhase:
    def test_single_filter_skips_combination(self):
        con = MagicMock()
        filters = [_make_filter("gemeente_Gemeentenaam", "Delft")]

        with patch(
            "app.services.helpers.filter_validation.check_combination_has_results"
        ) as mock_check:
            result = _validate_combination_phase(con, filters)

        assert result == []
        mock_check.assert_not_called()

    def test_valid_combination_returns_empty(self):
        con = MagicMock()
        filters = [
            _make_filter("gemeente_Gemeentenaam", "Delft"),
            _make_filter("gemeente_Code", "GM0503"),
        ]

        with patch(
            "app.services.helpers.filter_validation.check_combination_has_results",
            return_value=True,
        ):
            result = _validate_combination_phase(con, filters)

        assert result == []

    def test_invalid_combination_returns_conflicting_filter(self):
        con = MagicMock()
        filters = [
            _make_filter("gemeente_Gemeentenaam", "Delft"),
            _make_filter("gemeente_Code", "GM9999"),
        ]

        def check_combo(con, filters_arg):
            # Full combination fails; single filters pass
            return len(filters_arg) < 2

        with (
            patch(
                "app.services.helpers.filter_validation.check_combination_has_results",
                side_effect=check_combo,
            ),
            patch(
                "app.services.helpers.filter_validation.build_candidates_for_filter",
                return_value=["GM0503"],
            ),
        ):
            result = _validate_combination_phase(con, filters)

        assert len(result) == 1


class TestCollectInvalidFilters:
    def test_all_valid_returns_empty(self):
        con = MagicMock()
        filters = [_make_filter("gemeente_Gemeentenaam", "Delft")]

        with (
            patch(
                "app.services.helpers.filter_validation.check_value_exists",
                return_value=True,
            ),
            patch(
                "app.services.helpers.filter_validation.check_combination_has_results",
                return_value=True,
            ),
        ):
            result = collect_invalid_filters(con, filters)

        assert result == []

    def test_invalid_individual_stops_before_combination(self):
        con = MagicMock()
        filters = [_make_filter("gemeente_Gemeentenaam", "Delftt")]

        with (
            patch(
                "app.services.helpers.filter_validation.check_value_exists",
                return_value=False,
            ),
            patch(
                "app.services.helpers.filter_validation.build_candidates_for_filter",
                return_value=["Delft"],
            ),
            patch(
                "app.services.helpers.filter_validation.check_combination_has_results",
            ) as mock_combo,
        ):
            result = collect_invalid_filters(con, filters)

        assert len(result) == 1
        mock_combo.assert_not_called()

    def test_empty_filters_returns_empty(self):
        con = MagicMock()
        with patch(
            "app.services.helpers.filter_validation.check_combination_has_results",
            return_value=True,
        ):
            result = collect_invalid_filters(con, [])

        assert result == []
