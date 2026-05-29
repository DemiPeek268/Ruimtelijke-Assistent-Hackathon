"""Unit tests for ValidateFiltersNode.run — DB and LLM calls mocked."""

from unittest.mock import AsyncMock, patch

import pytest
from app.models.dictionary import ColumnInfo, DataDictionary, TableInfo, Theme
from app.models.state import Filter, Intent, IntentAnalysis
from app.models.validation import InvalidFilter
from app.services.nodes.validate_filters import ValidateFiltersNode

pytestmark = pytest.mark.unit


def _make_dictionary(categorical_cols=None) -> DataDictionary:
    cat_names = categorical_cols or ["gemeente_Gemeentenaam", "gemeente_Code"]
    cat_cols = [
        ColumnInfo(
            name=name,
            type="VARCHAR",
            categorical=True,
            table="gemeente_tabel",
            group="Gemeente",
        )
        for name in cat_names
    ]
    non_cat = ColumnInfo(
        name="verkeer_totaal_2020",
        type="INTEGER",
        categorical=False,
        table="verkeer_tabel",
        group="Verkeer",
    )
    tables = [
        TableInfo(name="gemeente_tabel", group="Gemeente", columns=cat_cols),
        TableInfo(name="verkeer_tabel", group="Verkeer", columns=[non_cat]),
    ]
    theme = Theme(name="test", label="Test", tables=tables)
    return DataDictionary(
        total_rows=100, total_columns=len(cat_cols) + 1, themes=[theme]
    )


def _make_state(filters=None, spatial_query=None, dictionary=None) -> dict:
    intent = Intent(
        description="test",
        relevant_columns=["h3_id"],
        filters=filters or [],
        spatial_query=spatial_query,
    )
    intent_analysis = IntentAnalysis(is_clear=True, intent=intent)
    return {
        "intent_analysis": intent_analysis,
        "dictionary": dictionary or _make_dictionary(),
        "model": "gpt-4o",
    }


class TestValidateFiltersNodeRun:
    async def test_no_categorical_filters_skipped(self):
        """When no categorical filters are present, validation is skipped."""
        node = ValidateFiltersNode()
        state = _make_state(
            filters=[Filter(column="verkeer_totaal_2020", operator=">", value="100")],
            dictionary=_make_dictionary(categorical_cols=["gemeente_Gemeentenaam"]),
        )

        with patch(
            "app.services.nodes.base.adispatch_custom_event", new_callable=AsyncMock
        ):
            state_update = await node.run(state, {})

        assert state_update == {}

    async def test_valid_filters_return_empty_state(self):
        """When all categorical filters are valid, state update is empty."""
        node = ValidateFiltersNode()
        state = _make_state(
            filters=[
                Filter(column="gemeente_Gemeentenaam", operator="=", value="Delft")
            ]
        )

        with (
            patch.object(node, "_validate_all", return_value=[]),
            patch(
                "app.services.nodes.base.adispatch_custom_event", new_callable=AsyncMock
            ),
        ):
            state_update = await node.run(state, {})

        assert state_update == {}

    async def test_invalid_filter_correctable_returns_corrected_intent(self):
        """When filters are invalid but correctable, returns corrected intent."""
        node = ValidateFiltersNode()
        state = _make_state(
            filters=[
                Filter(column="gemeente_Gemeentenaam", operator="=", value="Delftt")
            ]
        )

        invalid = [
            InvalidFilter(
                column="gemeente_Gemeentenaam",
                operator="=",
                attempted_value="Delftt",
                candidates=["Delft"],
            )
        ]
        corrected_intent = Intent(
            description="test",
            relevant_columns=["h3_id"],
            filters=[
                Filter(column="gemeente_Gemeentenaam", operator="=", value="Delft")
            ],
        )
        corrected_analysis = IntentAnalysis(is_clear=True, intent=corrected_intent)

        with (
            patch.object(node, "_validate_all", side_effect=[invalid, []]),
            patch.object(node, "_correct_filters", return_value=corrected_analysis),
            patch(
                "app.services.nodes.base.adispatch_custom_event", new_callable=AsyncMock
            ),
        ):
            state_update = await node.run(state, {})

        assert state_update["intent_analysis"] == corrected_analysis

    async def test_invalid_filter_not_correctable_dispatches_follow_up(self):
        """When filters cannot be corrected, a follow-up question is dispatched."""
        node = ValidateFiltersNode()
        state = _make_state(
            filters=[
                Filter(
                    column="gemeente_Gemeentenaam", operator="=", value="XYZ_NOTEXIST"
                )
            ]
        )

        invalid = [
            InvalidFilter(
                column="gemeente_Gemeentenaam",
                operator="=",
                attempted_value="XYZ_NOTEXIST",
                candidates=[],
            )
        ]
        follow_up_analysis = IntentAnalysis(
            is_clear=False,
            follow_up_question="Welke gemeente bedoelt u?",
        )

        dispatched = []

        async def capture(name, data, config=None):
            dispatched.append((name, data))

        with (
            patch.object(node, "_validate_all", return_value=invalid),
            patch.object(node, "_correct_filters", return_value=follow_up_analysis),
            patch(
                "app.services.nodes.base.adispatch_custom_event", side_effect=capture
            ),
        ):
            state_update = await node.run(state, {})

        assert state_update["intent_analysis"].is_clear is False
        follow_up_events = [d for d in dispatched if d[0] == "follow_up_text"]
        assert len(follow_up_events) == 1

    async def test_correction_still_invalid_dispatches_follow_up(self):
        """When corrected filters are still invalid, sends final follow-up."""
        node = ValidateFiltersNode()
        state = _make_state(
            filters=[Filter(column="gemeente_Gemeentenaam", operator="=", value="XYZ")]
        )

        invalid = [
            InvalidFilter(
                column="gemeente_Gemeentenaam",
                operator="=",
                attempted_value="XYZ",
                candidates=[],
            )
        ]
        corrected_intent = Intent(
            description="test",
            relevant_columns=["h3_id"],
            filters=[Filter(column="gemeente_Gemeentenaam", operator="=", value="ABC")],
        )
        corrected_analysis = IntentAnalysis(is_clear=True, intent=corrected_intent)
        final_analysis = IntentAnalysis(
            is_clear=False,
            follow_up_question="Geen overeenkomst gevonden.",
        )

        dispatched = []

        async def capture(name, data, config=None):
            dispatched.append((name, data))

        with (
            patch.object(node, "_validate_all", side_effect=[invalid, invalid]),
            patch.object(
                node,
                "_correct_filters",
                side_effect=[corrected_analysis, final_analysis],
            ),
            patch(
                "app.services.nodes.base.adispatch_custom_event", side_effect=capture
            ),
        ):
            state_update = await node.run(state, {})

        assert state_update["intent_analysis"].is_clear is False
        follow_up_events = [d for d in dispatched if d[0] == "follow_up_text"]
        assert len(follow_up_events) == 1

    def test_fallback_returns_empty_dict(self):
        node = ValidateFiltersNode()
        assert node.fallback() == {}
