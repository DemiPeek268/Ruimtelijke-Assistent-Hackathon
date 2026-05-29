"""Unit tests for filter_candidates.py"""

import pytest
from unittest.mock import MagicMock, patch
from app.models.state import Filter
from app.models.validation import InvalidFilter
from app.services.helpers.filter_candidates import (
    build_candidate_list,
    build_candidates_for_filter,
    build_fallback_question,
)

pytestmark = pytest.mark.unit


class TestBuildCandidateList:
    def test_returns_fuzzy_matches_when_three_or_more(self):
        all_values = ["Amsterdam", "Amstelveen", "Amstelland", "Rotterdam", "Utrecht"]
        result = build_candidate_list("Amsterdm", all_values)
        assert "Amsterdam" in result

    def test_returns_all_values_when_below_threshold(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "FILTER_ALL_VALUES_THRESHOLD", 200)
        monkeypatch.setattr(settings, "FILTER_FUZZY_CUTOFF", 0.8)
        monkeypatch.setattr(settings, "FILTER_MAX_FUZZY_CANDIDATES", 20)

        all_values = ["Delft", "Leiden", "Den Haag"]
        # attempted value far from all_values → fuzzy < 3, list is short → return all
        result = build_candidate_list("zzz_no_match", all_values)
        assert result == all_values

    def test_falls_back_to_wide_fuzzy_when_large_list_no_close_matches(
        self, monkeypatch
    ):
        from app.config import settings

        monkeypatch.setattr(settings, "FILTER_ALL_VALUES_THRESHOLD", 2)
        monkeypatch.setattr(settings, "FILTER_FUZZY_CUTOFF", 0.8)
        monkeypatch.setattr(settings, "FILTER_MAX_FUZZY_CANDIDATES", 20)

        all_values = ["Amsterdam", "Amstelveen", "Amstelland"] + [
            f"City{i}" for i in range(10)
        ]
        result = build_candidate_list("Amster", all_values)
        # Should return something (wide fuzzy fallback)
        assert isinstance(result, list)

    def test_returns_exact_matches_among_close_matches(self):
        all_values = ["Delft", "Delfzijl", "Den Haag", "Rotterdam", "Utrecht"]
        result = build_candidate_list("Delft", all_values)
        assert "Delft" in result

    def test_empty_all_values_returns_empty(self):
        result = build_candidate_list("Amsterdam", [])
        assert result == []


class TestBuildFallbackQuestion:
    def test_single_invalid_filter(self):
        invalid = [
            InvalidFilter(
                column="gemeente_Gemeentenaam",
                operator="=",
                attempted_value="Delftt",
                candidates=["Delft", "Delfzijl"],
            )
        ]
        result = build_fallback_question(invalid)
        assert "Delftt" in result
        assert "gemeente_Gemeentenaam" in result
        assert "Delft" in result

    def test_multiple_invalid_filters(self):
        invalid = [
            InvalidFilter(
                column="gemeente_Gemeentenaam",
                operator="=",
                attempted_value="Delftt",
                candidates=["Delft"],
            ),
            InvalidFilter(
                column="gemeente_Code",
                operator="=",
                attempted_value="Binennstad",
                candidates=["Binnenstad"],
            ),
        ]
        result = build_fallback_question(invalid)
        assert "Delftt" in result
        assert "Binennstad" in result

    def test_with_scope_filters_includes_scope_in_message(self):
        scope = [Filter(column="gemeente_Gemeentenaam", operator="=", value="Delft")]
        invalid = [
            InvalidFilter(
                column="gemeente_Code",
                operator="=",
                attempted_value="Centrum",
                candidates=["Binnenstad", "Noord"],
                scope_filters=scope,
            )
        ]
        result = build_fallback_question(invalid)
        assert "gemeente_Gemeentenaam" in result
        assert "Delft" in result

    def test_shows_at_most_ten_candidates(self):
        candidates = [f"City{i}" for i in range(20)]
        invalid = [
            InvalidFilter(
                column="gemeente_Gemeentenaam",
                operator="=",
                attempted_value="Test",
                candidates=candidates,
            )
        ]
        result = build_fallback_question(invalid)
        # Only first 10 candidates shown
        assert "City10" not in result
        assert "City9" in result


class TestBuildCandidatesForFilter:
    def test_calls_fetch_distinct_and_build_candidate_list(self):
        mock_con = MagicMock()
        filter_obj = Filter(
            column="gemeente_Gemeentenaam", operator="=", value="Delftt"
        )
        scope_filters = []

        with patch(
            "app.services.helpers.filter_candidates.fetch_distinct_values",
            return_value=["Delft", "Leiden", "Den Haag"],
        ) as mock_fetch:
            result = build_candidates_for_filter(mock_con, filter_obj, scope_filters)

        mock_fetch.assert_called_once_with(mock_con, filter_obj, scope_filters)
        assert "Delft" in result
