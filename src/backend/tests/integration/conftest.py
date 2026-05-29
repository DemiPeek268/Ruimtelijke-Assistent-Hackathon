import os

import pytest
from app.config import settings
from app.services.dictionary_service import generate_dictionary


@pytest.fixture(autouse=True)
def require_live_env():
    if os.getenv("RUN_LIVE_MODEL_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_MODEL_TESTS=1 to run integration tests.")

    if not settings.OPENAI_KEY:
        pytest.skip("OPENAI_KEY required.")


@pytest.fixture(scope="session")
async def dictionary():
    return await generate_dictionary()


@pytest.fixture(scope="session")
def initial_state(dictionary):
    return {
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
