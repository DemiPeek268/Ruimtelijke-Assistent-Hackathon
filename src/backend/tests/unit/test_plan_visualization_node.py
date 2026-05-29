"""Unit tests for PlanVisualizationNode — LLM calls are mocked."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models.dictionary import ColumnInfo, DataDictionary, TableInfo, Theme
from app.models.state import (
    ColorRole,
    Filter,
    Intent,
    IntentAnalysis,
    MapPlan,
    QueryResult,
)
from app.services.nodes.plan_visualization import PlanVisualizationNode

pytestmark = pytest.mark.unit


def _make_state(**overrides):
    col_h3 = ColumnInfo(
        name="h3_id", type="VARCHAR", table="verkeer_tabel", group="Verkeer"
    )
    col_val = ColumnInfo(
        name="verkeer_totaal_2020",
        type="INTEGER",
        table="verkeer_tabel",
        group="Verkeer",
    )
    table = TableInfo(name="verkeer_tabel", group="Verkeer", columns=[col_h3, col_val])
    theme = Theme(name="verkeer", label="Verkeer", tables=[table])
    dictionary = DataDictionary(total_rows=1000, total_columns=2, themes=[theme])
    intent = Intent(
        description="Toon verkeer in Delft",
        relevant_columns=["h3_id", "verkeer_totaal_2020"],
        filters=[Filter(column="gemeente_Gemeentenaam", operator="=", value="Delft")],
    )
    state = {
        "intent_analysis": IntentAnalysis(is_clear=True, intent=intent),
        "dictionary": dictionary,
        "model": "gpt-4o",
        "sql_query": "SELECT h3_id, verkeer_totaal_2020 FROM dataset",
        "query_result": QueryResult(
            sample=[
                {"h3_id": "8a1969481dbffff", "verkeer_totaal_2020": 42},
                {"h3_id": "8a1969481d3ffff", "verkeer_totaal_2020": 17},
            ],
            count=500,
        ),
    }
    state.update(overrides)
    return state


def _patch_node(plan: MapPlan):
    chain = MagicMock()
    chain.ainvoke = AsyncMock(return_value=plan)
    mock_prompt = MagicMock()
    mock_prompt.__or__ = MagicMock(return_value=chain)
    return (
        patch.object(PlanVisualizationNode, "_PROMPT", mock_prompt),
        patch(
            "app.services.nodes.plan_visualization.make_llm", return_value=MagicMock()
        ),
    )


class TestPlanVisualizationNodeSkip:
    async def test_skips_when_query_error(self):
        node = PlanVisualizationNode()
        state = _make_state(query_result=QueryResult(error="Syntax error"))
        state_update = await node.run(state, {})
        assert state_update == {"map_plan": None}

    async def test_skips_when_no_sql_query(self):
        node = PlanVisualizationNode()
        state = _make_state(sql_query=None)
        state_update = await node.run(state, {})
        assert state_update == {"map_plan": None}

    async def test_skips_when_no_sample(self):
        node = PlanVisualizationNode()
        state = _make_state(query_result=QueryResult(count=500))
        state_update = await node.run(state, {})
        assert state_update == {"map_plan": None}

    async def test_skips_when_count_is_zero(self):
        node = PlanVisualizationNode()
        state = _make_state(query_result=QueryResult(sample=[{"h3_id": "x"}], count=0))
        state_update = await node.run(state, {})
        assert state_update == {"map_plan": None}


class TestPlanVisualizationNodeRun:
    async def test_run_returns_map_plan_in_state(self):
        expected_plan = MapPlan(
            h3_column="h3_id",
            color=ColorRole(
                column="verkeer_totaal_2020", label="Verkeer", kind="numeric"
            ),
        )
        node = PlanVisualizationNode()
        state = _make_state()
        dispatched = []

        async def capture(name, data, config=None):
            dispatched.append((name, data))

        prompt_patch, llm_patch = _patch_node(expected_plan)
        with (
            prompt_patch,
            llm_patch,
            patch(
                "app.services.nodes.base.adispatch_custom_event", side_effect=capture
            ),
        ):
            state_update = await node.run(state, {})

        assert state_update["map_plan"] == expected_plan

    async def test_run_dispatches_map_block_event(self):
        plan = MapPlan(
            h3_column="h3_id",
            color=ColorRole(
                column="verkeer_totaal_2020", label="Verkeer", kind="numeric"
            ),
        )
        node = PlanVisualizationNode()
        state = _make_state()
        dispatched = []

        async def capture(name, data, config=None):
            dispatched.append((name, data))

        prompt_patch, llm_patch = _patch_node(plan)
        with (
            prompt_patch,
            llm_patch,
            patch(
                "app.services.nodes.base.adispatch_custom_event", side_effect=capture
            ),
        ):
            await node.run(state, {})

        event_names = [d[0] for d in dispatched]
        assert "map_block" in event_names
        map_block_data = next(d[1] for d in dispatched if d[0] == "map_block")
        assert map_block_data["h3_column"] == "h3_id"
        assert map_block_data["color"]["column"] == "verkeer_totaal_2020"

    async def test_run_state_contains_map_plan(self):
        plan = MapPlan(h3_column="h3_id")
        node = PlanVisualizationNode()
        state = _make_state()

        prompt_patch, llm_patch = _patch_node(plan)
        with (
            prompt_patch,
            llm_patch,
            patch("app.services.nodes.base.adispatch_custom_event", AsyncMock()),
        ):
            state_update = await node.run(state, {})

        assert state_update["map_plan"] == plan

    async def test_run_uses_only_first_10_sample_rows(self):
        """Prompt receives at most 10 sample rows regardless of sample size."""
        big_sample = [
            {"h3_id": f"hex_{i}", "verkeer_totaal_2020": i} for i in range(20)
        ]
        plan = MapPlan(h3_column="h3_id")
        node = PlanVisualizationNode()
        state = _make_state(query_result=QueryResult(sample=big_sample, count=20))

        captured_args: list = []

        original_format = None

        def capture_format(sample, count, summary, error):
            captured_args.append(sample)
            return original_format(sample, count, summary, error)

        import app.services.helpers.prompt_helpers as ph

        original_format = ph.format_results_section

        prompt_patch, llm_patch = _patch_node(plan)
        with (
            prompt_patch,
            llm_patch,
            patch("app.services.nodes.base.adispatch_custom_event", AsyncMock()),
            patch(
                "app.services.nodes.plan_visualization.format_results_section",
                side_effect=capture_format,
            ),
        ):
            await node.run(state, {})

        assert len(captured_args) == 1
        assert len(captured_args[0]) == 10


class TestPlanVisualizationNodeFallback:
    def test_fallback_returns_none_map_plan(self):
        node = PlanVisualizationNode()
        assert node.fallback() == {"map_plan": None}
