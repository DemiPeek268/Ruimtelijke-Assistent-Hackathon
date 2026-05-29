"""
Moch graph tests — Full-graph tests with all LLMs and external services mocked.

All LLMs are mocked via patch.object on node classes, following the same pattern
as the unit tests. Tests verify graph routing logic and state contracts.
Fast — no real API calls required.
"""

from unittest.mock import AsyncMock, patch

import pytest
from app.models.state import ColorRole, Intent, IntentAnalysis, MapPlan, QueryResult
from app.services.nodes.describe_results import DescribeResultsNode
from app.services.nodes.execute_query import ExecuteQueryNode
from app.services.nodes.intent import IntentNode
from app.services.nodes.plan_visualization import PlanVisualizationNode
from app.services.nodes.spatial import SpatialNode
from app.services.nodes.sql_generation import SqlGenerationNode
from app.services.nodes.validate_filters import ValidateFiltersNode

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clear_intent() -> IntentAnalysis:
    intent = Intent(
        description="Toon verkeersdata",
        relevant_columns=["h3_id", "verkeer_totaal_2020"],
        filters=[],
    )
    return IntentAnalysis(is_clear=True, intent=intent)


def _ambiguous_intent() -> IntentAnalysis:
    return IntentAnalysis(
        is_clear=False,
        follow_up_question="Welk type verkeersdata wil je zien?",
    )


def _intent_run(intent_analysis: IntentAnalysis, *, needs_spatial: bool = False):
    """AsyncMock for IntentNode.run that writes the given intent analysis to state."""
    return AsyncMock(
        return_value={
            "intent_analysis": intent_analysis,
            "needs_spatial_resolution": needs_spatial,
            "pdok_used": False,
        }
    )


def _noop_run():
    """AsyncMock for a node's run that returns an empty state update."""
    return AsyncMock(return_value={})


def _sql_run(sql: str = "SELECT h3_id, verkeer_totaal_2020 FROM dataset"):
    """AsyncMock for SqlGenerationNode.run."""
    return AsyncMock(return_value={"sql_query": sql})


def _execute_run(count: int = 3):
    """AsyncMock for ExecuteQueryNode.run returning {count} result rows."""
    sample = [{"h3_id": "8a1969481dbffff", "verkeer_totaal_2020": 42}] * min(count, 3)
    return AsyncMock(
        return_value={
            "query_result": QueryResult(
                sample=sample or None,
                count=count or None,
                summary=(
                    {"verkeer_totaal_2020": {"min": 0, "max": 100, "avg": 50}}
                    if count
                    else None
                ),
            )
        }
    )


def _execute_error_run():
    """AsyncMock for ExecuteQueryNode.run that writes a query_error to state."""
    return AsyncMock(
        return_value={"query_result": QueryResult(error="DB connection failed")}
    )


def _map_run():
    """AsyncMock for PlanVisualizationNode.run returning a minimal MapPlan."""
    plan = MapPlan(
        h3_column="h3_id",
        color=ColorRole(column="verkeer_totaal_2020", label="Verkeer", kind="numeric"),
    )
    return AsyncMock(return_value={"map_plan": plan})


def _describe_run(text: str = "Testbeschrijving."):
    """AsyncMock for DescribeResultsNode.run returning a canned explanation."""
    return AsyncMock(return_value={"explanation": text})


# ---------------------------------------------------------------------------
# Routing tests
# ---------------------------------------------------------------------------


class TestRoutingMocked:
    """Pins graph routing logic with all node.run() methods mocked."""

    async def test_unclear_intent_routes_to_end_without_sql(
        self, graph_base_state, run_graph
    ):
        """When IntentNode returns is_clear=False for any reason, the graph exits
        immediately and neither sql_query nor map_plan are written to state.
        Catches the regression where a node change makes ambiguous queries appear
        clear, causing the graph to generate SQL it should not."""
        with (
            patch.object(IntentNode, "run", _intent_run(_ambiguous_intent())),
            patch(
                "app.services.nodes.base.adispatch_custom_event",
                new_callable=AsyncMock,
            ),
        ):
            final_state = await run_graph(graph_base_state)

        assert final_state is not None
        assert final_state["sql_query"] is None
        assert final_state["map_plan"] is None

    async def test_clear_intent_no_spatial_skips_resolve_spatial(
        self, graph_base_state, run_graph
    ):
        """When intent is clear and needs_spatial_resolution=False, the SpatialNode
        is not entered and pdok_used stays False in the final state.
        Catches inadvertent routing into the spatial branch."""
        with (
            patch.object(
                IntentNode, "run", _intent_run(_clear_intent(), needs_spatial=False)
            ),
            patch.object(ValidateFiltersNode, "run", _noop_run()),
            patch.object(SqlGenerationNode, "run", _sql_run()),
            patch.object(ExecuteQueryNode, "run", _execute_run()),
            patch.object(PlanVisualizationNode, "run", _map_run()),
            patch.object(DescribeResultsNode, "run", _describe_run()),
            patch(
                "app.services.nodes.base.adispatch_custom_event",
                new_callable=AsyncMock,
            ),
        ):
            final_state = await run_graph(graph_base_state)

        assert final_state is not None
        assert final_state["pdok_used"] is False
        assert final_state["sql_query"] is not None

    async def test_clear_intent_with_spatial_routes_through_resolve_spatial(
        self, graph_base_state, run_graph
    ):
        """When needs_spatial_resolution=True, SpatialNode runs and sets pdok_used=True.
        Catches the spatial routing branch being accidentally bypassed."""
        spatial_update = {
            "intent_analysis": _clear_intent(),
            "needs_spatial_resolution": False,
            "pdok_used": True,
        }
        with (
            patch.object(
                IntentNode, "run", _intent_run(_clear_intent(), needs_spatial=True)
            ),
            patch.object(SpatialNode, "run", AsyncMock(return_value=spatial_update)),
            patch.object(ValidateFiltersNode, "run", _noop_run()),
            patch.object(SqlGenerationNode, "run", _sql_run()),
            patch.object(ExecuteQueryNode, "run", _execute_run()),
            patch.object(PlanVisualizationNode, "run", _map_run()),
            patch.object(DescribeResultsNode, "run", _describe_run()),
            patch(
                "app.services.nodes.base.adispatch_custom_event",
                new_callable=AsyncMock,
            ),
        ):
            final_state = await run_graph(graph_base_state)

        assert final_state is not None
        assert final_state["pdok_used"] is True

    async def test_filter_validation_failure_routes_to_end_without_sql(
        self, graph_base_state, run_graph
    ):
        """When ValidateFiltersNode returns is_clear=False after failed correction,
        the graph exits before SQL generation and sql_query stays None.
        Catches route_after_validation being bypassed."""
        with (
            patch.object(IntentNode, "run", _intent_run(_clear_intent())),
            patch.object(
                ValidateFiltersNode,
                "run",
                AsyncMock(return_value={"intent_analysis": _ambiguous_intent()}),
            ),
            patch(
                "app.services.nodes.base.adispatch_custom_event",
                new_callable=AsyncMock,
            ),
        ):
            final_state = await run_graph(graph_base_state)

        assert final_state is not None
        assert final_state["sql_query"] is None


# ---------------------------------------------------------------------------
# State transformation tests
# ---------------------------------------------------------------------------


class TestStateMocked:
    """Pins state contracts across the full graph with all LLMs mocked."""

    async def test_happy_path_populates_all_expected_state_keys(
        self, graph_base_state, run_graph
    ):
        """A full graph run with all mocked nodes produces sql_query, map_plan,
        and explanation — all non-null — with no query_error.
        Catches any node silently dropping its state write."""
        with (
            patch.object(IntentNode, "run", _intent_run(_clear_intent())),
            patch.object(ValidateFiltersNode, "run", _noop_run()),
            patch.object(SqlGenerationNode, "run", _sql_run()),
            patch.object(ExecuteQueryNode, "run", _execute_run(count=3)),
            patch.object(PlanVisualizationNode, "run", _map_run()),
            patch.object(DescribeResultsNode, "run", _describe_run()),
            patch(
                "app.services.nodes.base.adispatch_custom_event",
                new_callable=AsyncMock,
            ),
        ):
            final_state = await run_graph(graph_base_state)

        assert final_state is not None
        assert isinstance(final_state["sql_query"], str) and final_state["sql_query"]
        assert final_state["map_plan"] is not None
        assert final_state["explanation"] is not None
        assert final_state["query_result"].error is None

    async def test_query_error_skips_map_plan_but_explanation_still_written(
        self, graph_base_state, run_graph
    ):
        """When ExecuteQueryNode writes query_error, PlanVisualizationNode skips
        (returns map_plan=None without calling the LLM) but DescribeResultsNode
        still runs and writes explanation.
        Pins PlanVisualizationNode's skip guard and DescribeResultsNode's
        'always runs' contract simultaneously."""
        with (
            patch.object(IntentNode, "run", _intent_run(_clear_intent())),
            patch.object(ValidateFiltersNode, "run", _noop_run()),
            patch.object(SqlGenerationNode, "run", _sql_run()),
            patch.object(ExecuteQueryNode, "run", _execute_error_run()),
            # PlanVisualizationNode is NOT patched — it must skip naturally via its guard
            patch.object(DescribeResultsNode, "run", _describe_run()),
            patch(
                "app.services.nodes.base.adispatch_custom_event",
                new_callable=AsyncMock,
            ),
        ):
            final_state = await run_graph(graph_base_state)

        assert final_state is not None
        assert (
            isinstance(final_state["query_result"].error, str)
            and final_state["query_result"].error
        )
        assert final_state["map_plan"] is None
        assert final_state["explanation"] is not None

    async def test_zero_result_count_skips_map_plan(self, graph_base_state, run_graph):
        """When ExecuteQueryNode returns count=0, PlanVisualizationNode's guard
        (not count) fires and map_plan stays None — but explanation is still written.
        Pins the early-return guard in PlanVisualizationNode."""
        with (
            patch.object(IntentNode, "run", _intent_run(_clear_intent())),
            patch.object(ValidateFiltersNode, "run", _noop_run()),
            patch.object(SqlGenerationNode, "run", _sql_run()),
            patch.object(ExecuteQueryNode, "run", _execute_run(count=0)),
            # PlanVisualizationNode is NOT patched — it must skip naturally via its guard
            patch.object(DescribeResultsNode, "run", _describe_run()),
            patch(
                "app.services.nodes.base.adispatch_custom_event",
                new_callable=AsyncMock,
            ),
        ):
            final_state = await run_graph(graph_base_state)

        assert final_state is not None
        assert final_state["map_plan"] is None
        assert final_state["explanation"] is not None

    async def test_sql_query_written_verbatim_to_state(
        self, graph_base_state, run_graph
    ):
        """The sql_query written to state by SqlGenerationNode matches exactly what
        the mock returns — no accidental stripping or mangling of content.
        Catches any transformation of the SQL string between node output and state."""
        expected_sql = (
            "SELECT h3_id, verkeer_totaal_2020 FROM dataset WHERE gemeente = 'Delft'"
        )
        with (
            patch.object(IntentNode, "run", _intent_run(_clear_intent())),
            patch.object(ValidateFiltersNode, "run", _noop_run()),
            patch.object(SqlGenerationNode, "run", _sql_run(expected_sql)),
            patch.object(ExecuteQueryNode, "run", _execute_run()),
            patch.object(PlanVisualizationNode, "run", _map_run()),
            patch.object(DescribeResultsNode, "run", _describe_run()),
            patch(
                "app.services.nodes.base.adispatch_custom_event",
                new_callable=AsyncMock,
            ),
        ):
            final_state = await run_graph(graph_base_state)

        assert final_state is not None
        assert final_state["sql_query"] == expected_sql

    async def test_intent_node_corrects_hallucinated_column_names(
        self, graph_base_state, graph_mock_dictionary, run_graph
    ):
        """IntentNode's post-processing replaces a hallucinated column name with
        the closest fuzzy match from the dictionary.
        Pins _correct_column_names — which has no dedicated unit test — and catches
        a regression where correction silently stops working after a refactor."""
        from unittest.mock import MagicMock

        # LLM returns an intent with a hallucinated column suffix
        hallucinated_intent = IntentAnalysis(
            is_clear=True,
            intent=Intent(
                description="Toon verkeer",
                relevant_columns=["h3_id", "verkeer_totaal_202x"],
                filters=[],
            ),
        )
        valid_names = {col.name for col in graph_mock_dictionary.all_columns()}

        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=hallucinated_intent)
        mock_prompt = MagicMock()
        mock_prompt.__or__ = MagicMock(return_value=mock_chain)

        with (
            patch.object(IntentNode, "_PROMPT", mock_prompt),
            patch("app.services.nodes.intent.make_llm", return_value=MagicMock()),
            patch.object(ValidateFiltersNode, "run", _noop_run()),
            patch.object(SqlGenerationNode, "run", _sql_run()),
            patch.object(ExecuteQueryNode, "run", _execute_run()),
            patch.object(PlanVisualizationNode, "run", _map_run()),
            patch.object(DescribeResultsNode, "run", _describe_run()),
            patch(
                "app.services.nodes.base.adispatch_custom_event",
                new_callable=AsyncMock,
            ),
        ):
            final_state = await run_graph(graph_base_state)

        assert final_state is not None
        intent = final_state["intent_analysis"].intent
        for col in intent.relevant_columns:
            assert col in valid_names, (
                f"Column '{col}' was not corrected to a valid dictionary column. "
                f"Valid: {valid_names}"
            )
