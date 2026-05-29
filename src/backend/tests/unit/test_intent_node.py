"""Unit tests for IntentNode structured intent handling."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models.dictionary import DataDictionary
from app.models.state import Filter, Intent, IntentAnalysis
from app.services.nodes.intent import IntentNode

pytestmark = pytest.mark.unit


def _make_state(dictionary: DataDictionary) -> dict:
    return {
        "messages": [{"role": "user", "content": "Toon woningen in Delft"}],
        "dictionary": dictionary,
        "model": "gpt-4o",
    }


def _make_chain_mock(result: IntentAnalysis) -> MagicMock:
    chain = MagicMock()
    chain.ainvoke = AsyncMock(return_value=result)
    return chain


def _patch_node(result: IntentAnalysis):
    chain = _make_chain_mock(result)
    mock_prompt = MagicMock()
    mock_prompt.__or__ = MagicMock(return_value=chain)
    return (
        patch.object(IntentNode, "_PROMPT", mock_prompt),
        patch("app.services.nodes.intent.make_llm", return_value=MagicMock()),
    )


class TestIntentNodeRun:
    async def test_run_clear_intent(self, mock_dictionary):
        node = IntentNode()
        state = _make_state(mock_dictionary)

        clear_intent = Intent(
            description="Toon verkeer in Delft",
            relevant_columns=["h3_id", "verkeer_totaal_2020"],
            filters=[
                Filter(column="gemeente_Gemeentenaam", operator="=", value="Delft"),
            ],
        )
        clear_analysis = IntentAnalysis(is_clear=True, intent=clear_intent)

        prompt_patch, llm_patch = _patch_node(clear_analysis)
        with (
            prompt_patch,
            llm_patch,
            patch(
                "app.services.nodes.base.adispatch_custom_event", new_callable=AsyncMock
            ),
        ):
            state_update = await node.run(state, {})

        assert state_update["intent_analysis"].is_clear is True
        assert state_update["needs_spatial_resolution"] is False

    async def test_run_sets_spatial_resolution_flag_for_place_origin(
        self, mock_dictionary
    ):
        node = IntentNode()
        state = _make_state(mock_dictionary)

        spatial_intent = Intent(
            description="Toon woningen nabij Rotterdam Centraal",
            relevant_columns=["h3_id", "woningen_count"],
            filters=[],
            spatial_query={
                "origin_filters": [
                    {
                        "column": "h3_spatial_filter",
                        "operator": "=",
                        "value": "PLACE:Rotterdam Centraal",
                    }
                ],
                "k_rings": 6,
            },
        )
        clear_analysis = IntentAnalysis(is_clear=True, intent=spatial_intent)

        prompt_patch, llm_patch = _patch_node(clear_analysis)
        with (
            prompt_patch,
            llm_patch,
            patch(
                "app.services.nodes.base.adispatch_custom_event", new_callable=AsyncMock
            ),
        ):
            state_update = await node.run(state, {})

        assert state_update["needs_spatial_resolution"] is True

    async def test_run_unclear_intent_dispatches_follow_up(self, mock_dictionary):
        node = IntentNode()
        state = _make_state(mock_dictionary)

        unclear = IntentAnalysis(is_clear=False, follow_up_question="Welke kolom?")
        dispatched = []

        async def capture(name, data, config=None):
            dispatched.append((name, data))

        prompt_patch, llm_patch = _patch_node(unclear)
        with (
            prompt_patch,
            llm_patch,
            patch(
                "app.services.nodes.base.adispatch_custom_event", side_effect=capture
            ),
        ):
            state_update = await node.run(state, {})

        assert state_update["intent_analysis"].is_clear is False
        assert state_update["needs_spatial_resolution"] is False
        follow_up_events = [d for d in dispatched if d[0] == "follow_up_text"]
        assert len(follow_up_events) == 1

    async def test_run_corrects_hallucinated_column_names(self, mock_dictionary):
        node = IntentNode()
        state = _make_state(mock_dictionary)

        intent_with_bad_col = Intent(
            description="test",
            relevant_columns=["h3_id", "verkeer_totaal_20200"],  # typo
            filters=[],
        )
        analysis = IntentAnalysis(is_clear=True, intent=intent_with_bad_col)

        prompt_patch, llm_patch = _patch_node(analysis)
        with (
            prompt_patch,
            llm_patch,
            patch(
                "app.services.nodes.base.adispatch_custom_event", new_callable=AsyncMock
            ),
        ):
            state_update = await node.run(state, {})

        corrected = state_update["intent_analysis"].intent.relevant_columns
        assert "verkeer_totaal_20200" not in corrected

    def test_fallback_returns_none_intent(self):
        node = IntentNode()
        result = node.fallback()
        assert result["intent_analysis"] is None
        assert result["needs_spatial_resolution"] is False
