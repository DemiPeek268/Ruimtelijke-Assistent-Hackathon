"""Unit tests for the MLflow side-effect inside the feedback router.

Postgres is faked so we can focus on the contract between the router and the
`log_feedback_to_mlflow` helper. Coverage of UPSERT semantics, ownership, etc.
lives in `tests/e2e/test_e2e_feedback.py` (against real Postgres).
"""

import uuid
from datetime import datetime, timezone
from typing import AsyncIterator
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.sql.elements import TextClause

from app.auth import CurrentUser, get_current_user
from app.database import get_session

pytestmark = [pytest.mark.unit, pytest.mark.asyncio(loop_scope="function")]

TEST_USER = CurrentUser(oid="fb-mlflow-user", name="MLflow Test")
SESSION_ID = uuid.uuid4()
ASSISTANT_MSG_ID = "asst-msg-123"
ASSISTANT_MSG_ID_2 = "asst-msg-456"


class _FakeDb:
    """Minimal AsyncSession stand-in scoped to one session row and its feedback.

    Records what the router writes so tests can assert on the persisted state
    without needing Postgres.
    """

    def __init__(self):
        # The seed assistant messages that the router's existence check looks for.
        # Two are seeded so concurrent-different-key tests can hit independent
        # advisory-lock keys.
        self.session_row = MagicMock(
            id=SESSION_ID,
            user_id=TEST_USER.oid,
            deleted_at=None,
            messages=[
                {"id": "user-msg", "role": "user"},
                {"id": ASSISTANT_MSG_ID, "role": "assistant"},
                {"id": ASSISTANT_MSG_ID_2, "role": "assistant"},
            ],
        )
        self.feedback_rows: list = []
        self.deleted: list = []
        # Records every `text()` statement the router issued — lets tests
        # assert on pg_advisory_lock acquisition/release without depending on
        # real Postgres.
        self.text_statements: list[str] = []

    async def get(self, model, ident):
        if ident == SESSION_ID:
            return self.session_row
        return None

    async def exec(self, statement):
        # `text()` statements are the advisory-lock calls (pg_advisory_lock /
        # pg_advisory_unlock). Record them and return a no-op result so they
        # don't get conflated with the feedback-row lookup.
        if isinstance(statement, TextClause):
            self.text_statements.append(str(statement))
            return MagicMock(first=MagicMock(return_value=None))
        # The router's lone select is the lookup for an existing feedback row.
        result = MagicMock()
        result.first = MagicMock(
            return_value=self.feedback_rows[0] if self.feedback_rows else None
        )
        return result

    def add(self, obj):
        if obj not in self.feedback_rows:
            self.feedback_rows.append(obj)
        # Stamp fields that the response model requires.
        if not getattr(obj, "updated_at", None):
            obj.updated_at = datetime.now(timezone.utc)

    async def delete(self, obj):
        self.deleted.append(obj)
        if obj in self.feedback_rows:
            self.feedback_rows.remove(obj)

    async def commit(self):
        # No-op: `add` already attached fields.
        pass

    async def rollback(self):
        # Drop anything that was added but not yet committed. The fake's add()
        # is eager so we just clear the deleted bookkeeping; the real session
        # would discard pending instances here.
        pass

    async def refresh(self, obj):
        return obj


@pytest_asyncio.fixture(loop_scope="function")
async def client():
    from app.routers import feedback as feedback_router

    db = _FakeDb()

    async def _db_dep() -> AsyncIterator:
        yield db

    app = FastAPI()
    app.include_router(feedback_router.router)
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    app.dependency_overrides[get_session] = _db_dep

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        # Stash the fake db on the client so tests can inspect it.
        c._fake_db = db  # type: ignore[attr-defined]
        yield c


def _feedback_url() -> str:
    return f"/api/sessions/{SESSION_ID}/messages/{ASSISTANT_MSG_ID}/feedback"


class TestFeedbackRouterCallsMlflowHelper:
    async def test_thumbs_down_with_comment_invokes_helper(self, client):
        """Successful POST → helper called once with message_id, rating, user_id, comment."""
        with patch("app.routers.feedback.log_feedback_to_mlflow") as mock_helper:
            resp = await client.post(
                _feedback_url(),
                json={"rating": "down", "comment": "te weinig context"},
            )

        assert resp.status_code == 200, resp.text
        mock_helper.assert_called_once_with(
            message_id=ASSISTANT_MSG_ID,
            rating="down",
            user_id=TEST_USER.oid,
            comment="te weinig context",
        )

    async def test_thumbs_up_invokes_helper_with_no_comment(self, client):
        """Thumbs-up never has a comment → helper called with comment=None."""
        with patch("app.routers.feedback.log_feedback_to_mlflow") as mock_helper:
            resp = await client.post(_feedback_url(), json={"rating": "up"})

        assert resp.status_code == 200, resp.text
        mock_helper.assert_called_once()
        kwargs = mock_helper.call_args.kwargs
        assert kwargs["rating"] == "up"
        assert kwargs["comment"] is None

    async def test_clear_rating_invokes_helper_with_rating_none(self, client):
        """rating=None must call the helper too, so MLflow drops the prior
        assessment instead of keeping a stale value the user just retracted."""
        client._fake_db.feedback_rows.append(  # type: ignore[attr-defined]
            MagicMock(
                rating="up",
                comment=None,
                updated_at=datetime.now(timezone.utc),
            )
        )

        with patch("app.routers.feedback.log_feedback_to_mlflow") as mock_helper:
            resp = await client.post(_feedback_url(), json={"rating": None})

        assert resp.status_code == 200
        mock_helper.assert_called_once_with(
            message_id=ASSISTANT_MSG_ID,
            rating=None,
            user_id=TEST_USER.oid,
            comment=None,
        )

    async def test_clear_without_existing_row_returns_updated_at_null(self, client):
        """Clearing a rating that never existed returns updated_at=None — we
        don't synthesize a fake timestamp for a row that was never written."""
        with patch("app.routers.feedback.log_feedback_to_mlflow"):
            resp = await client.post(_feedback_url(), json={"rating": None})

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["rating"] is None
        assert body["comment"] is None
        assert body["updated_at"] is None

    async def test_advisory_lock_is_acquired_and_released_per_request(self, client):
        """Every successful POST emits pg_advisory_lock(k) + pg_advisory_unlock(k)
        bound to the same key derived from (message_id, user_id). This is what
        prevents the concurrent-click race from producing duplicate MLflow
        user_thumbs assessments."""
        from app.routers.feedback import _advisory_key

        with patch("app.routers.feedback.log_feedback_to_mlflow"):
            resp = await client.post(_feedback_url(), json={"rating": "up"})

        assert resp.status_code == 200, resp.text
        text_stmts = client._fake_db.text_statements  # type: ignore[attr-defined]
        assert any("pg_advisory_lock" in s for s in text_stmts)
        assert any("pg_advisory_unlock" in s for s in text_stmts)
        # The key must come from (message_id, user_id) — assert it's deterministic
        # and stable across calls.
        expected_key = _advisory_key(ASSISTANT_MSG_ID, TEST_USER.oid)
        assert isinstance(expected_key, int)
        assert _advisory_key(ASSISTANT_MSG_ID, TEST_USER.oid) == expected_key
        # And different from a different message_id (so concurrent requests on
        # different messages don't serialize against each other).
        other_key = _advisory_key(ASSISTANT_MSG_ID_2, TEST_USER.oid)
        assert other_key != expected_key

    async def test_advisory_lock_released_even_when_handler_errors(self, client):
        """If the handler raises mid-flight, the lock must still be released —
        otherwise the connection returns to the pool holding a Postgres lock
        and the next request inheriting that connection deadlocks."""
        with patch(
            "app.routers.feedback._apply_feedback",
            side_effect=RuntimeError("boom"),
        ):
            try:
                await client.post(_feedback_url(), json={"rating": "up"})
            except Exception:
                pass  # We care about the lock-release side-effect, not the response.

        text_stmts = client._fake_db.text_statements  # type: ignore[attr-defined]
        assert any("pg_advisory_lock" in s for s in text_stmts)
        assert any("pg_advisory_unlock" in s for s in text_stmts)

    async def test_mlflow_side_effect_does_not_block_event_loop(self, client):
        """The MLflow helper makes sync HTTP calls; running it inline in the
        async handler would block the event loop and serialize concurrent
        requests. Verify two parallel POSTs complete in roughly one helper-
        duration, not two — i.e. they don't block each other."""
        import asyncio
        import time

        SLEEP = 0.25

        def slow_helper(**_kwargs):
            time.sleep(SLEEP)

        with patch("app.routers.feedback.log_feedback_to_mlflow", slow_helper):
            start = time.monotonic()
            resps = await asyncio.gather(
                client.post(_feedback_url(), json={"rating": "up"}),
                client.post(_feedback_url(), json={"rating": "down"}),
            )
            elapsed = time.monotonic() - start

        assert all(r.status_code == 200 for r in resps)
        # If the helper ran inline (blocking the event loop), elapsed would be
        # ~2 * SLEEP. Backgrounded into the threadpool, it's ~SLEEP. Pick a
        # threshold that's roughly halfway with margin for CI variability.
        assert elapsed < SLEEP * 1.6, (
            f"feedback POSTs serialized: elapsed={elapsed:.3f}s, "
            f"expected < {SLEEP * 1.6:.3f}s — MLflow helper is blocking the event loop"
        )
