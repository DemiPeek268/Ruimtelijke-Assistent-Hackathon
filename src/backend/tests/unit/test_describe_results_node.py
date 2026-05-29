"""Unit tests for DescribeResultsNode — LLM calls are mocked."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models.dictionary import DataDictionary
from app.models.state import Filter, Intent, IntentAnalysis, QueryResult
from app.services.nodes.describe_results import DescribeResultsNode

pytestmark = pytest.mark.unit


def _make_state(
    dictionary: DataDictionary,
    sample=None,
    count=None,
    sql_query=None,
    query_error=None,
    map_plan=None,
    summary=None,
):
    intent = Intent(
        description="Toon verkeer in Delft",
        relevant_columns=["h3_id", "verkeer_totaal_2020"],
        filters=[Filter(column="gemeente_Gemeentenaam", operator="=", value="Delft")],
    )
    intent_analysis = IntentAnalysis(is_clear=True, intent=intent)
    return {
        "intent_analysis": intent_analysis,
        "dictionary": dictionary,
        "model": "gpt-4o",
        "query_result": QueryResult(
            sample=sample, count=count, summary=summary, error=query_error
        ),
        "sql_query": sql_query,
        "map_plan": map_plan,
    }


def _patch_node(text: str):
    response = MagicMock()
    response.content = text
    chain = MagicMock()
    chain.ainvoke = AsyncMock(return_value=response)
    mock_prompt = MagicMock()
    mock_prompt.__or__ = MagicMock(return_value=chain)
    return (
        patch.object(DescribeResultsNode, "_PROMPT", mock_prompt),
        patch("app.services.nodes.describe_results.make_llm", return_value=MagicMock()),
    )


class TestDescribeResultsNode:
    async def test_run_returns_explanation(self, mock_dictionary):
        node = DescribeResultsNode()
        state = _make_state(
            mock_dictionary,
            sample=[{"h3_id": "abc", "verkeer_totaal_2020": 42}],
            count=1,
            sql_query="SELECT h3_id FROM dataset",
        )

        prompt_patch, llm_patch = _patch_node("Er zijn 42 woningen.")
        with (
            prompt_patch,
            llm_patch,
            patch(
                "app.services.nodes.base.adispatch_custom_event", new_callable=AsyncMock
            ),
        ):
            state_update = await node.run(state, {})

        assert state_update["explanation"] == "Er zijn 42 woningen."

    async def test_run_with_empty_sample(self, mock_dictionary):
        node = DescribeResultsNode()
        state = _make_state(mock_dictionary, sample=None, count=0)

        prompt_patch, llm_patch = _patch_node("Geen resultaten gevonden.")
        with (
            prompt_patch,
            llm_patch,
            patch(
                "app.services.nodes.base.adispatch_custom_event", new_callable=AsyncMock
            ),
        ):
            state_update = await node.run(state, {})

        assert "Geen resultaten gevonden." in state_update["explanation"]

    def test_fallback_returns_none_explanation(self):
        node = DescribeResultsNode()
        result = node.fallback()
        assert result["explanation"] is None
