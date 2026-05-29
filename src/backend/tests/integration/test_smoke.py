"""
Smoke tests — verify the full LangGraph workflow runs end-to-end without crashing.

Each test covers one top-level execution path: the happy path (clear query reaches END
with an explanation) and the early-exit path (ambiguous query exits cleanly with no SQL).

Assertions are limited to type and None checks only — never specific field values or
LLM output content. That belongs in test_integration.py.

Requires RUN_LIVE_MODEL_TESTS=1 and a valid OPENAI_KEY.
Run selectively: pytest -m smoke
"""

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.smoke,
]


class TestSmoke:
    async def test_happy_path_produces_explanation(self, initial_state, run_graph):
        """A clear, unambiguous query runs the full graph to END and produces a non-empty
        explanation string. Catches graph-level crashes and wiring failures."""
        initial_state["messages"] = [
            {
                "role": "user",
                "content": "Toon de NO2 concentratie in 2025.",
            }
        ]
        final_state = await run_graph(initial_state)

        assert final_state is not None, "Graph produced no final state."
        assert (
            isinstance(final_state.get("explanation"), str)
            and final_state["explanation"]
        ), "explanation should be a non-empty string"

    async def test_ambiguous_query_exits_without_crash(self, initial_state, run_graph):
        """An ambiguous query causes early graph exit. The workflow must terminate
        cleanly with no SQL generated. Does not assert specific LLM output values."""
        initial_state["messages"] = [{"role": "user", "content": "Laat geluid zien."}]
        final_state = await run_graph(initial_state)

        assert final_state is not None, "Graph produced no final state."
        assert final_state.get("sql_query") is None
        assert final_state.get("intent_analysis") is not None
