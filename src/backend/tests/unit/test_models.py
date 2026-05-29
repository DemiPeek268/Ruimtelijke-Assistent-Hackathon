"""Unit tests for models — ensures model instantiation and validation works."""

import pytest
from app.models.chat import ChatMessage, ChatRequest
from app.models.dictionary import ColumnInfo
from app.models.state import (
    Aggregation,
    Filter,
    Intent,
    IntentAnalysis,
    SpatialQuery,
    YearComparison,
)
from app.models.validation import InvalidFilter

pytestmark = pytest.mark.unit


class TestModels:
    def test_filter_creation(self):
        f = Filter(column="gemeentenaam", operator="=", value="Delft")
        assert f.column == "gemeentenaam"

    def test_intent_analysis_not_clear(self):
        ia = IntentAnalysis(is_clear=False, follow_up_question="Welke kolom?")
        assert ia.is_clear is False
        assert ia.follow_up_question == "Welke kolom?"

    def test_intent_analysis_clear(self):
        intent = Intent(
            description="Toon woningen",
            relevant_columns=["h3_id"],
            filters=[],
        )
        ia = IntentAnalysis(is_clear=True, intent=intent)
        assert ia.is_clear is True
        assert ia.intent is not None

    def test_invalid_filter_default_source(self):
        inv = InvalidFilter(
            column="gemeentenaam",
            operator="=",
            attempted_value="Delftt",
            candidates=["Delft"],
        )
        assert inv.source == "filter"
        assert inv.scope_filters == []
        assert inv.sibling_match is None

    def test_invalid_filter_custom_source(self):
        inv = InvalidFilter(
            column="gemeentenaam",
            operator="=",
            attempted_value="X",
            candidates=[],
            source="spatial_origin",
        )
        assert inv.source == "spatial_origin"

    def test_spatial_query_creation(self):
        sq = SpatialQuery(
            origin_filters=[Filter(column="gemeentenaam", operator="=", value="Delft")],
            k_rings=10,
        )
        assert sq.k_rings == 10
        assert len(sq.origin_filters) == 1

    def test_chat_request_default_model(self):
        req = ChatRequest(messages=[ChatMessage(role="user", content="test")])
        expected_default = ChatRequest.model_fields["model"].default
        assert req.model == expected_default

    def test_aggregation_creation(self):
        agg = Aggregation(column="gemeentenaam", function="AVG")
        assert agg.column == "gemeentenaam"
        assert agg.function == "AVG"


class TestYearComparisonModel:
    def test_year_comparison_creation(self):
        yc = YearComparison(column="bouwjaar", year_from=2018, year_to=2023)
        assert yc.column == "bouwjaar"
        assert yc.year_from == 2018
        assert yc.year_to == 2023


class TestIntentModel:
    def test_intent_default_filters_is_empty_list(self):
        intent = Intent(description="test", relevant_columns=["h3_id"])
        assert intent.filters == []

    def test_intent_defaults_year_comparison_to_none(self):
        intent = Intent(description="test", relevant_columns=["h3_id"])
        assert intent.year_comparison is None

    def test_intent_accepts_year_comparison(self):
        yc = YearComparison(column="bouwjaar", year_from=2018, year_to=2023)
        intent = Intent(
            description="test", relevant_columns=["h3_id"], year_comparison=yc
        )
        assert intent.year_comparison is not None
        assert intent.year_comparison.column == "bouwjaar"

    def test_intent_defaults_limit_to_none(self):
        intent = Intent(description="test", relevant_columns=["h3_id"])
        assert intent.limit is None

    def test_intent_accepts_limit(self):
        intent = Intent(description="test", relevant_columns=["h3_id"], limit=5)
        assert intent.limit == 5


class TestColumnInfoTable:
    def test_table_and_group_are_required(self):
        with pytest.raises(Exception):
            ColumnInfo(name="aantal_inwoners_sum", type="BIGINT")

    def test_table_can_be_set_to_uc_table_name(self):
        col = ColumnInfo(
            name="aantal_inwoners_sum",
            type="BIGINT",
            table="cbs_bevolking_h3",
            group="CBS",
        )
        assert col.table == "cbs_bevolking_h3"
