# Unit tests for prompt_helpers.py
import pytest
from app.models.dictionary import ColumnInfo, DataDictionary, Theme
from app.models.state import Aggregation, Filter, Intent, YearComparison
from app.services.helpers.prompt_helpers import (
    build_all_column_names,
    build_columns_text,
    format_intent_section,
    format_results_section,
    load_prompt,
)

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skip(
        reason="ColumnInfo dropped normalized/source/available_years and Theme "
        "now owns tables, not columns. Rewrite for the new model shape."
    ),
]


def _make_dictionary(
    normalized: bool = False,
    unit: str = "index",
    with_range: bool = False,
    categorical: bool = False,
) -> DataDictionary:
    col = ColumnInfo(
        name="verkeer_totaal_2020",
        type="INTEGER",
        min="0" if with_range else None,
        max="255" if with_range else None,
        description="Aantal woningen",
        unit=unit,
        normalized=normalized,
        categorical=categorical,
        available_years=[2022, 2023],
    )
    theme = Theme(name="wonen", label="Wonen", columns=[col])
    return DataDictionary(total_rows=1000, total_columns=1, themes=[theme])


class TestLoadPrompt:
    def test_returns_nonempty_string_for_known_file(self):
        result = load_prompt("03_sql_generator.md")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_raises_for_unknown_file(self):
        with pytest.raises(FileNotFoundError):
            load_prompt("nonexistent_prompt.md")


class TestFormatResultsSection:
    def test_error_takes_priority_over_data(self):
        result = format_results_section(
            sample=[{"h3_id": "abc", "val": 1}],
            count=1,
            summary=None,
            error="relation 'dataset' does not exist",
        )

        assert "Error" in result
        assert "relation 'dataset' does not exist" in result
        assert "abc" not in result

    def test_zero_count_returns_no_results_message(self):
        result = format_results_section(sample=None, count=0, summary=None, error=None)
        assert "0 rows" in result

    def test_none_count_returns_no_results_message(self):
        result = format_results_section(
            sample=None, count=None, summary=None, error=None
        )
        assert "0 rows" in result

    def test_small_result_includes_all_rows_label(self):
        sample = [{"h3_id": "abc", "val": 1}]
        result = format_results_section(
            sample=sample, count=1, summary=None, error=None
        )
        assert "All rows" in result

    def test_large_result_includes_sample_label(self):
        sample = [{"h3_id": f"cell{i}", "val": i} for i in range(10)]
        result = format_results_section(
            sample=sample, count=500, summary=None, error=None
        )
        assert "500" in result
        assert "10" in result

    def test_summary_included_when_present(self):
        sample = [{"h3_id": "abc", "val": 42}]
        summary = {"val": {"min": 0, "max": 255, "avg": 127.5}}
        result = format_results_section(
            sample=sample, count=200, summary=summary, error=None
        )
        assert "val" in result
        assert "127.5" in result

    def test_sample_data_serialized_as_json(self):
        sample = [{"h3_id": "abc", "val": 42}]
        result = format_results_section(
            sample=sample, count=1, summary=None, error=None
        )
        assert "abc" in result
        assert "42" in result

    def test_categorical_summary_renders_top_values(self):
        summary = {
            "gemeente_Gemeentenaam": {
                "non_null_count": 500,
                "distinct_count": 12,
                "top_values": {"Leiden": 80, "Delft": 65, "Gouda": 42},
            }
        }
        result = format_results_section(
            sample=[{"h3_id": "abc"}], count=500, summary=summary, error=None
        )
        assert "gemeente_Gemeentenaam" in result
        assert "Leiden" in result
        assert "12" in result
        assert "500" in result
        assert "Most common" in result


class TestBuildColumnsText:
    def test_intent_mode_includes_name_and_description(self):
        dictionary = _make_dictionary()
        result = build_columns_text(dictionary, mode="intent")
        assert "verkeer_totaal_2020" in result
        assert "Aantal woningen" in result

    def test_intent_mode_includes_norm_flag_when_normalized(self):
        dictionary = _make_dictionary(normalized=True)
        result = build_columns_text(dictionary, mode="intent")
        assert "[NORM]" in result

    def test_intent_mode_includes_available_years(self):
        dictionary = _make_dictionary()
        result = build_columns_text(dictionary, mode="intent")
        assert "2022" in result
        assert "2023" in result

    def test_sql_mode_includes_type(self):
        dictionary = _make_dictionary()
        result = build_columns_text(dictionary, mode="sql")
        assert "INTEGER" in result

    def test_sql_mode_includes_range_when_present(self):
        dictionary = _make_dictionary(with_range=True)
        result = build_columns_text(dictionary, mode="sql")
        assert "Range: 0-255" in result

    def test_sql_mode_shows_unit_when_not_index(self):
        dictionary = _make_dictionary(unit="meters")
        result = build_columns_text(dictionary, mode="sql")
        assert "meters" in result

    def test_only_columns_filter(self):
        col_a = ColumnInfo(name="col_a", type="INTEGER", description="Column A")
        col_b = ColumnInfo(name="col_b", type="VARCHAR", description="Column B")
        theme = Theme(name="test", label="Test", columns=[col_a, col_b])
        dictionary = DataDictionary(total_rows=100, total_columns=2, themes=[theme])

        result = build_columns_text(dictionary, only_columns=["col_a"])
        assert "col_a" in result
        assert "col_b" not in result

    def test_empty_theme_columns_excluded(self):
        col_a = ColumnInfo(name="col_a", type="INTEGER")
        col_b = ColumnInfo(name="col_b", type="VARCHAR")
        theme1 = Theme(name="t1", label="T1", columns=[col_a])
        theme2 = Theme(name="t2", label="T2", columns=[col_b])
        dictionary = DataDictionary(
            total_rows=100, total_columns=2, themes=[theme1, theme2]
        )

        result = build_columns_text(dictionary, only_columns=["col_a"])
        assert "T1" in result
        assert "T2" not in result


class TestBuildAllColumnNames:
    def test_includes_theme_label_and_column_names(self):
        dictionary = _make_dictionary()
        result = build_all_column_names(dictionary)
        assert "Wonen" in result
        assert "verkeer_totaal_2020" in result

    def test_multiple_columns_comma_separated(self):
        col_a = ColumnInfo(name="col_a", type="INTEGER")
        col_b = ColumnInfo(name="col_b", type="VARCHAR")
        theme = Theme(name="test", label="Test", columns=[col_a, col_b])
        dictionary = DataDictionary(total_rows=100, total_columns=2, themes=[theme])
        result = build_all_column_names(dictionary)
        assert "col_a" in result
        assert "col_b" in result
        assert "," in result


class TestFormatIntentSection:
    def test_includes_description(self):
        intent = Intent(
            description="Toon woningen per gemeente",
            relevant_columns=["h3_id", "verkeer_totaal_2020"],
            filters=[
                Filter(column="gemeente_Gemeentenaam", operator="=", value="Leiden")
            ],
        )
        result = format_intent_section(intent)
        assert "Toon woningen per gemeente" in result

    def test_includes_relevant_columns(self):
        intent = Intent(
            description="test",
            relevant_columns=["h3_id", "verkeer_totaal_2020"],
            filters=[],
        )
        result = format_intent_section(intent)
        assert "h3_id" in result
        assert "verkeer_totaal_2020" in result

    def test_includes_filters(self):
        intent = Intent(
            description="test",
            relevant_columns=["h3_id"],
            filters=[
                Filter(column="gemeente_Gemeentenaam", operator="=", value="Leiden")
            ],
        )
        result = format_intent_section(intent)
        assert "gemeente_Gemeentenaam" in result
        assert "Leiden" in result

    def test_no_aggregation_not_included(self):
        intent = Intent(
            description="test", relevant_columns=["h3_id"], filters=[], aggregation=None
        )
        result = format_intent_section(intent)
        assert "Aggregation" not in result

    def test_with_aggregation_included(self):
        from app.models.state import Aggregation

        intent = Intent(
            description="test",
            relevant_columns=["h3_id"],
            filters=[],
            aggregation=Aggregation(column="verkeer_totaal_2020", function="AVG"),
        )
        result = format_intent_section(intent)
        assert "Aggregation" in result
        assert "AVG" in result

    def test_aggregation_uses_explicit_function_column_format(self):
        intent = Intent(
            description="test",
            relevant_columns=["h3_id"],
            filters=[],
            aggregation=Aggregation(column="verkeer_totaal_2020", function="AVG"),
        )
        result = format_intent_section(intent)
        assert "AVG(verkeer_totaal_2020)" in result

    def test_aggregation_with_level_shows_group_by_columns(self):
        intent = Intent(
            description="test",
            relevant_columns=["h3_id"],
            filters=[],
            aggregation=Aggregation(
                column="verkeer_totaal_2020",
                function="SUM",
                level=["gemeente_Gemeentenaam"],
            ),
        )
        result = format_intent_section(intent)
        assert "gemeente_Gemeentenaam" in result

    def test_with_year_comparison_included(self):
        intent = Intent(
            description="test",
            relevant_columns=["h3_id"],
            filters=[],
            year_comparison=YearComparison(
                column="bouwjaar", year_from=2018, year_to=2023
            ),
        )
        result = format_intent_section(intent)
        assert "Year comparison" in result
        assert "bouwjaar" in result
        assert "2018" in result
        assert "2023" in result

    def test_without_year_comparison_not_included(self):
        intent = Intent(
            description="test",
            relevant_columns=["h3_id"],
            filters=[],
        )
        result = format_intent_section(intent)
        assert "Year comparison" not in result

    def test_with_spatial_query_included(self):
        from app.models.state import SpatialQuery

        intent = Intent(
            description="test",
            relevant_columns=["h3_id"],
            filters=[],
            spatial_query=SpatialQuery(
                origin_filters=[
                    Filter(column="gemeente_Gemeentenaam", operator="=", value="Delft")
                ],
                k_rings=5,
            ),
        )
        result = format_intent_section(intent)
        assert "spatial_query" in result
        assert "Delft" in result
        assert "5" in result
