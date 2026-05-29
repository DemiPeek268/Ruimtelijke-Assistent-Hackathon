import pytest

from app.services.workflow import workflow


@pytest.fixture(scope="session")
def run_graph():
    async def _run(state: dict) -> dict | None:
        final_state = None
        async for event in workflow.astream_events(state, version="v2"):
            if event["event"] == "on_chain_end" and event.get("name") == "LangGraph":
                final_state = event.get("data", {}).get("output")
        return final_state

    return _run
