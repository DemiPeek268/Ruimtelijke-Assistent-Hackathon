"""Integration tests for the message-feedback endpoint.

Run against the real Postgres dev database (the same one `test_e2e_sessions.py`
uses) so UPSERT semantics, the UNIQUE(message_id, user_id) constraint, and
joins-on-message-id are exercised against the actual driver.

Marked `e2e` because they require docker-compose's `db` service running.
"""

import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth import CurrentUser, get_current_user
from app.config import settings
from app.database import get_session
from app.models.feedback import MessageFeedback
from app.models.session import Session
from app.routers import feedback as feedback_router
from app.routers import sessions as sessions_router

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="function")]

USER_A = CurrentUser(oid="fb-user-a", name="User A")
USER_B = CurrentUser(oid="fb-user-b", name="User B")

_active_user: CurrentUser = USER_A


def _current_user() -> CurrentUser:
    return _active_user


@pytest_asyncio.fixture(loop_scope="function", scope="function")
async def engine():
    """Per-test engine so asyncpg's bound event loop matches the test loop."""
    eng = create_async_engine(settings.DATABASE_URL, echo=False)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.fixture
def db_dependency(engine):
    async def _real_db() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session

    return _real_db


@pytest.fixture
def app(db_dependency):
    application = FastAPI()
    application.include_router(feedback_router.router)
    application.include_router(sessions_router.router)
    application.dependency_overrides[get_current_user] = _current_user
    application.dependency_overrides[get_session] = db_dependency
    return application


@pytest_asyncio.fixture(loop_scope="function")
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


def _make_message(role: str, content: str = "hi", id: str | None = None) -> dict:
    return {
        "id": id or str(uuid.uuid4()),
        "role": role,
        "content": content,
        "sql": None,
        "map_config": None,
        "thinking_steps": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


async def _seed_session(
    engine,
    user_id: str = USER_A.oid,
    messages: list[dict] | None = None,
) -> Session:
    sess = Session(
        user_id=user_id,
        title="Feedback test",
        messages=messages or [_make_message("user"), _make_message("assistant")],
    )
    async with AsyncSession(engine) as db:
        db.add(sess)
        await db.commit()
        await db.refresh(sess)
    return sess


async def _cleanup(engine) -> None:
    async with AsyncSession(engine) as db:
        await db.exec(
            delete(MessageFeedback).where(
                MessageFeedback.user_id.in_([USER_A.oid, USER_B.oid])  # pyright: ignore[reportAttributeAccessIssue]
            )
        )
        result = await db.exec(
            select(Session).where(Session.user_id.in_([USER_A.oid, USER_B.oid]))  # pyright: ignore[reportAttributeAccessIssue]
        )
        for s in result.all():
            await db.delete(s)
        await db.commit()


async def _count_feedback(engine, message_id: str, user_id: str) -> int:
    async with AsyncSession(engine) as db:
        result = await db.exec(
            select(MessageFeedback)
            .where(MessageFeedback.message_id == message_id)
            .where(MessageFeedback.user_id == user_id)
        )
        return len(result.all())


async def _get_feedback(
    engine, message_id: str, user_id: str
) -> MessageFeedback | None:
    async with AsyncSession(engine) as db:
        result = await db.exec(
            select(MessageFeedback)
            .where(MessageFeedback.message_id == message_id)
            .where(MessageFeedback.user_id == user_id)
        )
        return result.first()


@pytest_asyncio.fixture(autouse=True, loop_scope="function")
async def _isolate(engine):
    global _active_user
    _active_user = USER_A
    await _cleanup(engine)
    yield
    await _cleanup(engine)


class TestPostFeedback:
    async def test_creates_row_with_rating_up(self, engine, client):
        """POST {rating: up} on an assistant message persists a single row."""
        session = await _seed_session(engine)
        assistant_msg = next(m for m in session.messages if m["role"] == "assistant")
        msg_id = assistant_msg["id"]

        resp = await client.post(
            f"/api/sessions/{session.id}/messages/{msg_id}/feedback",
            json={"rating": "up"},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["rating"] == "up"
        assert body["updated_at"]

        assert await _count_feedback(engine, msg_id, USER_A.oid) == 1

    async def test_second_post_overwrites_rating(self, engine, client):
        """Second POST upserts: same row, new rating, advanced updated_at."""
        session = await _seed_session(engine)
        msg_id = next(m["id"] for m in session.messages if m["role"] == "assistant")
        url = f"/api/sessions/{session.id}/messages/{msg_id}/feedback"

        first = await client.post(url, json={"rating": "up"})
        assert first.status_code == 200
        first_updated = first.json()["updated_at"]

        second = await client.post(url, json={"rating": "down"})
        assert second.status_code == 200
        assert second.json()["rating"] == "down"
        assert second.json()["updated_at"] >= first_updated

        assert await _count_feedback(engine, msg_id, USER_A.oid) == 1
        row = await _get_feedback(engine, msg_id, USER_A.oid)
        assert row is not None and row.rating == "down"

    async def test_post_null_clears_row(self, engine, client):
        """POST {rating: null} deletes the existing feedback row."""
        session = await _seed_session(engine)
        msg_id = next(m["id"] for m in session.messages if m["role"] == "assistant")
        url = f"/api/sessions/{session.id}/messages/{msg_id}/feedback"

        await client.post(url, json={"rating": "up"})
        assert await _count_feedback(engine, msg_id, USER_A.oid) == 1

        clear = await client.post(url, json={"rating": None})
        assert clear.status_code == 200
        body = clear.json()
        assert body["rating"] is None
        # Cleared rating reports no `updated_at` — nothing to update once the
        # row is gone (avoids synthesizing a fake timestamp).
        assert body["updated_at"] is None
        assert await _count_feedback(engine, msg_id, USER_A.oid) == 0

    async def test_other_user_gets_404(self, engine, client):
        """User B posting to User A's session leaks nothing and returns 404."""
        global _active_user
        session = await _seed_session(engine, user_id=USER_A.oid)
        msg_id = next(m["id"] for m in session.messages if m["role"] == "assistant")

        _active_user = USER_B
        resp = await client.post(
            f"/api/sessions/{session.id}/messages/{msg_id}/feedback",
            json={"rating": "up"},
        )

        assert resp.status_code == 404
        assert await _count_feedback(engine, msg_id, USER_B.oid) == 0
        assert await _count_feedback(engine, msg_id, USER_A.oid) == 0

    async def test_non_assistant_message_returns_404(self, engine, client):
        """Posting to a user message must 404 (only assistant turns are rateable)."""
        session = await _seed_session(engine)
        user_msg_id = next(m["id"] for m in session.messages if m["role"] == "user")

        resp = await client.post(
            f"/api/sessions/{session.id}/messages/{user_msg_id}/feedback",
            json={"rating": "up"},
        )

        assert resp.status_code == 404
        assert await _count_feedback(engine, user_msg_id, USER_A.oid) == 0

    async def test_non_existent_session_returns_404(self, client):
        """Bogus session_id → 404."""
        resp = await client.post(
            f"/api/sessions/{uuid.uuid4()}/messages/{uuid.uuid4()}/feedback",
            json={"rating": "up"},
        )
        assert resp.status_code == 404


class TestGetSessionEmbedsFeedback:
    async def test_get_session_embeds_feedback_per_assistant_message(
        self, engine, client
    ):
        """GET /api/sessions/{id} returns feedback per assistant message:
        - rated assistant → {"feedback": {"rating", "updated_at"}}
        - unrated assistant → {"feedback": null}
        - user message → no feedback field (or null; we settle on null)
        """
        user_msg = _make_message("user")
        rated_msg = _make_message("assistant")
        unrated_msg = _make_message("assistant")
        session = await _seed_session(
            engine, messages=[user_msg, rated_msg, unrated_msg]
        )

        # Pre-seed a feedback row for `rated_msg`.
        rate = await client.post(
            f"/api/sessions/{session.id}/messages/{rated_msg['id']}/feedback",
            json={"rating": "down"},
        )
        assert rate.status_code == 200

        resp = await client.get(f"/api/sessions/{session.id}")
        assert resp.status_code == 200
        messages = resp.json()["messages"]
        assert len(messages) == 3

        by_id = {m["id"]: m for m in messages}
        # User message: feedback is null (consistent shape, never present).
        assert by_id[user_msg["id"]].get("feedback") is None
        # Unrated assistant message: feedback is null.
        assert by_id[unrated_msg["id"]]["feedback"] is None
        # Rated assistant message: feedback object present.
        rated_fb = by_id[rated_msg["id"]]["feedback"]
        assert rated_fb["rating"] == "down"
        assert rated_fb["updated_at"]

    async def test_get_session_does_not_leak_other_users_feedback(self, engine, client):
        """Feedback lookup is scoped to the current user. User A rates their
        own message; the GET as user A returns it. (User B can't even see the
        session — covered by existing session ownership tests — so the only
        cross-user leak path would be a bug in the join. This pins it down.)
        """
        global _active_user
        user_msg = _make_message("user")
        asst_msg = _make_message("assistant")
        session = await _seed_session(
            engine, user_id=USER_A.oid, messages=[user_msg, asst_msg]
        )

        # User A rates the message.
        _active_user = USER_A
        await client.post(
            f"/api/sessions/{session.id}/messages/{asst_msg['id']}/feedback",
            json={"rating": "up"},
        )

        # Directly insert a contradicting row attributed to USER_B for the
        # same message_id (simulating the bug surface this test guards).
        async with AsyncSession(engine) as db:
            db.add(
                MessageFeedback(
                    session_id=session.id,
                    message_id=asst_msg["id"],
                    user_id=USER_B.oid,
                    rating="down",
                )
            )
            await db.commit()

        # User A's GET must still see their own "up", not user B's "down".
        _active_user = USER_A
        resp = await client.get(f"/api/sessions/{session.id}")
        assert resp.status_code == 200
        msgs = resp.json()["messages"]
        asst = next(m for m in msgs if m["id"] == asst_msg["id"])
        assert asst["feedback"]["rating"] == "up"


class TestFeedbackComment:
    """Slice 3 — optional comment on thumbs-down."""

    async def test_message_feedback_table_has_comment_column(self, engine):
        """Migration must add the nullable `comment` column to message_feedback."""
        from sqlalchemy import text

        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT column_name, is_nullable "
                    "FROM information_schema.columns "
                    "WHERE table_name = 'message_feedback' "
                    "AND column_name = 'comment'"
                )
            )
            row = result.first()
        assert row is not None, "comment column missing from message_feedback"
        assert row[1] == "YES", "comment column must be nullable"

    async def test_post_with_comment_persists_both(self, engine, client):
        """POST {rating, comment} stores both; GET returns both."""
        session = await _seed_session(engine)
        msg_id = next(m["id"] for m in session.messages if m["role"] == "assistant")
        url = f"/api/sessions/{session.id}/messages/{msg_id}/feedback"

        resp = await client.post(
            url, json={"rating": "down", "comment": "te weinig context"}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["rating"] == "down"
        assert body["comment"] == "te weinig context"

        row = await _get_feedback(engine, msg_id, USER_A.oid)
        assert row is not None and row.comment == "te weinig context"

    async def test_post_without_comment_field_preserves_existing(self, engine, client):
        """Re-POSTing the same rating with no `comment` key must not erase it."""
        session = await _seed_session(engine)
        msg_id = next(m["id"] for m in session.messages if m["role"] == "assistant")
        url = f"/api/sessions/{session.id}/messages/{msg_id}/feedback"

        first = await client.post(
            url, json={"rating": "down", "comment": "blijft staan"}
        )
        assert first.status_code == 200

        second = await client.post(url, json={"rating": "down"})
        assert second.status_code == 200
        assert second.json()["comment"] == "blijft staan"

        row = await _get_feedback(engine, msg_id, USER_A.oid)
        assert row is not None and row.comment == "blijft staan"

    async def test_post_with_empty_comment_overwrites(self, engine, client):
        """Explicit `comment: ""` is the clear-path: overwrites prior comment."""
        session = await _seed_session(engine)
        msg_id = next(m["id"] for m in session.messages if m["role"] == "assistant")
        url = f"/api/sessions/{session.id}/messages/{msg_id}/feedback"

        await client.post(url, json={"rating": "down", "comment": "original"})
        clear = await client.post(url, json={"rating": "down", "comment": ""})
        assert clear.status_code == 200
        assert clear.json()["comment"] == ""

        row = await _get_feedback(engine, msg_id, USER_A.oid)
        assert row is not None and row.comment == ""

    async def test_post_comment_too_long_returns_422(self, engine, client):
        """Comments longer than 2000 chars are rejected by Pydantic validation."""
        session = await _seed_session(engine)
        msg_id = next(m["id"] for m in session.messages if m["role"] == "assistant")
        url = f"/api/sessions/{session.id}/messages/{msg_id}/feedback"

        resp = await client.post(url, json={"rating": "down", "comment": "x" * 2001})
        assert resp.status_code == 422
        assert await _count_feedback(engine, msg_id, USER_A.oid) == 0

    async def test_post_null_rating_ignores_comment(self, engine, client):
        """Clearing the rating deletes the row; any comment in the body is ignored."""
        session = await _seed_session(engine)
        msg_id = next(m["id"] for m in session.messages if m["role"] == "assistant")
        url = f"/api/sessions/{session.id}/messages/{msg_id}/feedback"

        await client.post(url, json={"rating": "down", "comment": "weg ermee"})
        clear = await client.post(url, json={"rating": None, "comment": "negeer mij"})
        assert clear.status_code == 200
        assert clear.json()["comment"] is None
        assert await _count_feedback(engine, msg_id, USER_A.oid) == 0

    async def test_get_session_embeds_comment_in_feedback(self, engine, client):
        """GET /api/sessions/{id} surfaces `comment` inside the embedded feedback."""
        user_msg = _make_message("user")
        rated_msg = _make_message("assistant")
        session = await _seed_session(engine, messages=[user_msg, rated_msg])

        rate = await client.post(
            f"/api/sessions/{session.id}/messages/{rated_msg['id']}/feedback",
            json={"rating": "down", "comment": "onvoldoende uitleg"},
        )
        assert rate.status_code == 200

        resp = await client.get(f"/api/sessions/{session.id}")
        assert resp.status_code == 200
        by_id = {m["id"]: m for m in resp.json()["messages"]}
        fb = by_id[rated_msg["id"]]["feedback"]
        assert fb["rating"] == "down"
        assert fb["comment"] == "onvoldoende uitleg"
        assert fb["updated_at"]
