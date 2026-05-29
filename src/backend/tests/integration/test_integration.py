"""
Integration tests — verify the LLM correctly interprets specific query classes and
produces structured output that satisfies contracts. Each test asserts a specific LLM capability or output contract.

Requires RUN_LIVE_MODEL_TESTS=1 and a valid OPENAI_KEY.
Run selectively: pytest -m integration
"""

import pytest
from app.config import settings
from app.models.state import Intent, IntentAnalysis

pytestmark = [
    pytest.mark.integration,
    pytest.mark.flaky(reruns=2),
]


# ── Shared NO2 fixture ─────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
async def no2_result(dictionary, run_graph):
    """Runs the full graph once for a clear NO2 query. Shared by four contract tests
    to avoid redundant API calls."""
    state = {
        "messages": [],
        "dictionary": dictionary,
        "model": settings.OPENAI_MODEL,
        "intent_analysis": None,
        "needs_spatial_resolution": False,
        "pdok_used": False,
        "sql_query": None,
        "query_result": None,
        "map_plan": None,
        "explanation": None,
    }
    state["messages"] = [
        {
            "role": "user",
            "content": "Toon de NO2 concentratie in de provincie Zuid-Holland in 2025.",
        }
    ]
    result = await run_graph(state)
    if result is None:
        pytest.fail("NO2 fixture: graph produced no final state.")
    intent_analysis = result.get("intent_analysis")
    if intent_analysis is None or not intent_analysis.is_clear:
        pytest.fail(
            "NO2 fixture: model returned ambiguous intent for a query that should be "
            "unambiguous. Pinned here so dependent contract tests don't silently skip; "
            "rerun retries are configured at the test level via flaky(reruns=2)."
        )
    return result


# ── Output contracts (NO2 query) ───────────────────────────────────────────────


class TestIntentContracts:
    """Verify that the LLM intent output conforms to expected schema and constraints."""

    async def test_intent_conforms_to_schema(self, no2_result):
        """A clear query produces an IntentAnalysis with a populated Intent and non-empty
        relevant_columns. Catches Pydantic schema drift caused by model updates."""
        intent_analysis = no2_result.get("intent_analysis")
        assert isinstance(intent_analysis, IntentAnalysis)
        assert intent_analysis.is_clear is True
        assert isinstance(intent_analysis.intent, Intent)
        assert isinstance(intent_analysis.intent.relevant_columns, list)
        assert len(intent_analysis.intent.relevant_columns) > 0

    async def test_no_hallucinated_columns(self, no2_result, dictionary):
        """Every column in intent.relevant_columns must exist in the data dictionary.
        This is the primary contract guard against silent LLM column hallucination,
        which would produce invalid SQL downstream."""
        intent_analysis = no2_result["intent_analysis"]
        valid_columns = {
            col.name for theme in dictionary.themes for col in theme.columns
        }
        for col in intent_analysis.intent.relevant_columns:
            assert col in valid_columns, (
                f"Hallucinated column '{col}' not in data dictionary — "
                "would produce invalid SQL."
            )

    async def test_sql_is_valid_select(self, no2_result):
        """A clear query produces a non-empty sql_query that starts with SELECT."""
        sql = no2_result.get("sql_query")
        assert isinstance(sql, str) and sql
        assert sql.strip().upper().startswith("SELECT"), (
            f"Expected SELECT statement, got: {sql[:60]!r}"
        )

    async def test_sql_columns_are_subset_of_relevant_columns(
        self, no2_result, dictionary
    ):
        """Every data-dictionary column referenced in the SQL must have been declared
        as relevant by the intent node. Catches SqlGenerationNode hallucinating column
        names that the intent never selected."""
        intent_analysis = no2_result["intent_analysis"]
        sql_query = no2_result.get("sql_query") or ""
        all_column_names = {
            col.name for theme in dictionary.themes for col in theme.columns
        }
        intent = intent_analysis.intent
        allowed = set(intent.relevant_columns) | {f.column for f in intent.filters}

        hallucinated = {
            col for col in all_column_names if col in sql_query and col not in allowed
        }
        assert not hallucinated, (
            f"SQL references columns not declared in intent.relevant_columns or intent.filters: {hallucinated}"
        )

    async def test_map_plan_references_result_column(self, no2_result):
        """map_plan.h3_column must refer to a column that actually exists in the
        query results. Catches hallucinated column names in the visualisation plan."""
        query_result = no2_result.get("query_result")
        if query_result is None or query_result.error or not query_result.sample:
            pytest.skip("No query results available — cannot validate map_plan column.")

        map_plan = no2_result.get("map_plan")
        if map_plan is None:
            pytest.skip("No map_plan produced.")

        result_columns = set(query_result.sample[0].keys())
        assert map_plan.h3_column in result_columns, (
            f"map_plan.h3_column '{map_plan.h3_column}' not in result columns: "
            f"{result_columns}"
        )


# ── Ambiguity detection ────────────────────────────────────────────────────────


class TestAmbiguityDetection:
    async def test_ambiguous_query_returns_follow_up(self, initial_state, run_graph):
        """An ambiguous multi-column query should cause the model to return is_clear=False
        with a non-empty follow-up question asking for clarification."""
        initial_state["messages"] = [
            {"role": "user", "content": "Hoe is het geluid in de regio?"}
        ]
        final_state = await run_graph(initial_state)

        intent_analysis = final_state.get("intent_analysis")
        assert intent_analysis is not None
        assert intent_analysis.is_clear is False
        assert (
            isinstance(intent_analysis.follow_up_question, str)
            and intent_analysis.follow_up_question
        )


# ── Feature behaviors ──────────────────────────────────────────────────────────


class TestYearComparison:
    async def test_year_comparison_sets_intent_fields_and_sql(
        self, initial_state, run_graph
    ):
        """A query comparing two explicit years should populate year_comparison on the
        intent and embed both years in the generated SQL."""
        initial_state["messages"] = [
            {
                "role": "user",
                "content": "Wat is het verschil in totale verkeersintensiteit tussen 2018 en 2023?",
            }
        ]
        final_state = await run_graph(initial_state)

        intent = final_state.get("intent_analysis").intent
        sql_query = final_state.get("sql_query", "") or ""

        assert intent.year_comparison is not None
        assert intent.year_comparison.year_from == 2018
        assert intent.year_comparison.year_to == 2023
        assert "2018" in sql_query
        assert "2023" in sql_query


class TestTopNAggregation:
    async def test_top_n_sets_limit_and_aggregation_level(
        self, initial_state, run_graph
    ):
        """A top-N query with an explicit count and area type should set intent.limit,
        a non-null aggregation level, and produce SQL with GROUP BY."""
        initial_state["messages"] = [
            {
                "role": "user",
                "content": "Welke 5 gemeenten hebben de hoogste NO2 concentratie in 2025?",
            }
        ]
        final_state = await run_graph(initial_state)

        intent = final_state.get("intent_analysis").intent
        sql_query = final_state.get("sql_query", "") or ""

        assert intent.limit == 5
        assert intent.aggregation is not None
        assert intent.aggregation.level is not None
        assert any("gemeente" in col.lower() for col in intent.aggregation.level)
        assert "GROUP BY" in sql_query.upper()


# ── Filter validation ──────────────────────────────────────────────────────────


class TestFilterValidation:
    async def test_valid_municipality_passes_validation(self, initial_state, run_graph):
        """A query with a valid, existing municipality value should pass filter
        validation and produce SQL."""
        initial_state["messages"] = [
            {"role": "user", "content": "Toon de NO2 concentratie in Leiden in 2025."}
        ]
        final_state = await run_graph(initial_state)

        assert final_state is not None
        intent_analysis = final_state.get("intent_analysis")
        assert intent_analysis is not None
        assert intent_analysis.is_clear is True
        assert final_state.get("sql_query") is not None

    async def test_municipality_synonym_is_corrected(self, initial_state, run_graph):
        """'Den Haag' is a known synonym for ''s-Gravenhage'. Filter validation
        should correct it automatically — the query stays clear and SQL is produced."""
        initial_state["messages"] = [
            {"role": "user", "content": "Toon de NO2 concentratie in Den Haag in 2025."}
        ]
        final_state = await run_graph(initial_state)

        assert final_state is not None
        intent_analysis = final_state.get("intent_analysis")
        assert intent_analysis is not None
        assert intent_analysis.is_clear is True
        assert final_state.get("sql_query") is not None
        filters = intent_analysis.intent.filters
        gemeente_filter = next(
            f for f in filters if f.column == "gemeente_Gemeentenaam"
        )
        assert gemeente_filter.value == "'s-Gravenhage"

    async def test_nonexistent_municipality_fails_validation(
        self, initial_state, run_graph
    ):
        """A municipality that doesn't exist anywhere in Zuid-Holland should result
        in is_clear=False with a follow-up question, regardless of which node catches it."""
        initial_state["messages"] = [
            {
                "role": "user",
                "content": "Toon de NO2 concentratie in IJsselstijn in 2025.",
            }
        ]
        final_state = await run_graph(initial_state)

        assert final_state is not None
        intent_analysis = final_state.get("intent_analysis")
        assert intent_analysis is not None
        assert intent_analysis.is_clear is False
        assert intent_analysis.follow_up_question
        assert final_state.get("sql_query") is None


# ── PDOK spatial resolution ────────────────────────────────────────────────────


# class TestPDOKSpatialResolution:
#     async def test_pdok_location_resolves_to_coordinates_in_sql(
#         self, initial_state, run_graph
#     ):
#         """A spatial query with a named place triggers PDOK lookup, sets pdok_used=True,
#         and embeds resolved decimal-degree coordinates in the SQL.
#         Does not assert exact coordinate values — PDOK precision can vary."""
#         initial_state["messages"] = [
#             {
#                 "role": "user",
#                 "content": "Binnen een cirkel van 15 km rond Coepelduynen: toon de geluidsniveaus.",
#             }
#         ]
#         final_state = await run_graph(initial_state)

#         assert final_state is not None
#         assert final_state.get("pdok_used") is True
#         sql_query = final_state.get("sql_query") or ""
#         match = re.search(r"([\d.]+),\s*([\d.]+)", sql_query)
#         assert match is not None, "No decimal-degree coordinates found in sql_query"
#         lat, lon = float(match.group(1)), float(match.group(2))
#         assert abs(lat - 52.225703) < 0.0001, (
#             f"Latitude {lat} too far from expected ~52.225703"
#         )
#         assert abs(lon - 4.414886) < 0.0001, (
#             f"Longitude {lon} too far from expected ~4.414886"
#         )
