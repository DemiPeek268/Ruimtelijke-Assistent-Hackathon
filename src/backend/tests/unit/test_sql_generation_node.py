"""Unit tests for SqlGenerationNode — LLM calls are mocked."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models.dictionary import DataDictionary
from app.models.state import Filter, Intent, IntentAnalysis, SqlGenerationOutput
from app.services.nodes.sql_generation import SqlGenerationNode

pytestmark = pytest.mark.unit


def _make_state(dictionary: DataDictionary):
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
    }


def _make_chain_mock(sql: str, thinking: str = "test summary") -> MagicMock:
    """Return a mock chain whose ainvoke resolves to a SqlGenerationOutput directly."""
    chain = MagicMock()
    chain.ainvoke = AsyncMock(
        return_value=SqlGenerationOutput(sql_query=sql, thinking_summary=thinking)
    )
    return chain


def _patch_node(chain: MagicMock):
    """Patch the DuckDB prompt and make_llm so the chain pipeline yields *chain*."""
    mock_prompt = MagicMock()
    mock_prompt.__or__ = MagicMock(return_value=chain)
    return (
        patch.object(SqlGenerationNode, "_PROMPT_DUCKDB", mock_prompt),
        patch("app.services.nodes.sql_generation.make_llm", return_value=MagicMock()),
    )


class TestSqlGenerationNodeRun:
    async def test_run_returns_sql_state(self, mock_dictionary):
        node = SqlGenerationNode()
        state = _make_state(mock_dictionary)
        dispatched = []

        async def capture(name, data, config=None):
            dispatched.append((name, data))

        chain = _make_chain_mock("SELECT h3_id FROM dataset")
        prompt_patch, llm_patch = _patch_node(chain)

        with (
            prompt_patch,
            llm_patch,
            patch(
                "app.services.nodes.base.adispatch_custom_event", side_effect=capture
            ),
        ):
            state_update = await node.run(state, {})

        assert state_update["sql_query"] == "SELECT h3_id FROM dataset"
        assert "map_config" not in state_update and "map_plan" not in state_update
        event_names = [d[0] for d in dispatched]
        assert "map_block" not in event_names

    async def test_run_dispatches_thinking_summary(self, mock_dictionary):
        node = SqlGenerationNode()
        state = _make_state(mock_dictionary)
        dispatched: list[str] = []

        async def capture(name, data, config=None):
            dispatched.append(name)

        chain = _make_chain_mock("SELECT 1", thinking="ik heb de query gegenereerd")
        prompt_patch, llm_patch = _patch_node(chain)

        with (
            prompt_patch,
            llm_patch,
            patch(
                "app.services.nodes.base.adispatch_custom_event", side_effect=capture
            ),
        ):
            await node.run(state, {})

        assert "step_thinking_summary" in dispatched

    def test_fallback_returns_none_sql(self):
        node = SqlGenerationNode()
        result = node.fallback()
        assert result["sql_query"] is None


class TestSqlGenerationNodeBuildContext:
    def test_build_context_shape(self, mock_dictionary):
        node = SqlGenerationNode()
        state = _make_state(mock_dictionary)
        ctx = node._build_context(state)

        assert "themes" in ctx
        assert "intent_section" in ctx
        assert "catalog_schema" not in ctx
