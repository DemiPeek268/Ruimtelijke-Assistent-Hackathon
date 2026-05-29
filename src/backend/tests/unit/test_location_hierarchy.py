"""Unit tests for location_hierarchy.py"""

import pytest
from app.models.state import Filter
from app.services.helpers.location_hierarchy import (
    get_parent_columns,
    is_location_column,
    sort_filters_by_hierarchy,
)

pytestmark = pytest.mark.unit


class TestIsLocationColumn:
    def test_gemeente_is_location(self):
        assert is_location_column("gemeente_Gemeentenaam") is True

    def test_gemeente_code_is_location(self):
        assert is_location_column("gemeente_Code") is True

    def test_code_columns_are_location(self):
        assert is_location_column("gemeente_Code") is True

    def test_non_location_column(self):
        assert is_location_column("verkeer_totaal_2020") is False

    def test_unknown_column(self):
        assert is_location_column("not_a_real_column") is False


class TestGetParentColumns:
    def test_gemeente_has_no_parents(self):
        assert get_parent_columns("gemeente_Gemeentenaam") == []

    def test_gemeente_code_has_no_parents(self):
        assert get_parent_columns("gemeente_Code") == []

    def test_non_location_column_returns_empty(self):
        assert get_parent_columns("verkeer_totaal_2020") == []

    def test_unknown_column_returns_empty(self):
        assert get_parent_columns("does_not_exist") == []


class TestSortFiltersByHierarchy:
    def _make_filter(self, column: str) -> Filter:
        return Filter(column=column, operator="=", value="test")

    def test_non_location_comes_last(self):
        filters = [
            self._make_filter("verkeer_totaal_2020"),
            self._make_filter("gemeente_Gemeentenaam"),
        ]
        sorted_filters = sort_filters_by_hierarchy(filters)
        assert sorted_filters[0].column == "gemeente_Gemeentenaam"
        assert sorted_filters[1].column == "verkeer_totaal_2020"

    def test_location_columns_before_non_location(self):
        filters = [
            self._make_filter("verkeer_totaal_2020"),
            self._make_filter("gemeente_Gemeentenaam"),
            self._make_filter("gemeente_Code"),
        ]
        sorted_filters = sort_filters_by_hierarchy(filters)
        columns = [f.column for f in sorted_filters]
        non_loc_idx = columns.index("verkeer_totaal_2020")
        assert columns.index("gemeente_Gemeentenaam") < non_loc_idx
        assert columns.index("gemeente_Code") < non_loc_idx

    def test_empty_list_returns_empty(self):
        assert sort_filters_by_hierarchy([]) == []
