"""Tests for session CRUD endpoints."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.auth import CurrentUser, get_current_user
from app.database import get_session
from app.models.session import Session

pytestmark = pytest.mark.unit

TEST_USER = CurrentUser(oid="user-oid-123", name="Test User")
OTHER_USER = CurrentUser(oid="other-oid-456", name="Other User")


def _make_session(user_id: str = TEST_USER.oid, **kwargs) -> Session:
    defaults = dict(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Test session",
        messages=[
            {
                "id": str(uuid.uuid4()),
                "role": "user",
                "content": "Hallo",
                "sql": None,
                "map_config": None,
                "thinking_steps": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        deleted_at=None,
    )
    defaults.update(kwargs)
    return Session(**defaults)


def _make_app(mock_db):
    from app.routers.sessions import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    app.dependency_overrides[get_session] = lambda: mock_db
    return app


class TestListSessions:
    @pytest.mark.anyio
    async def test_returns_user_sessions_ordered_by_updated_at(self):
        s1 = _make_session(title="First")
        s2 = _make_session(title="Second")

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [s2, s1]
        mock_db.exec = AsyncMock(return_value=mock_result)

        app = _make_app(mock_db)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/sessions")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    @pytest.mark.anyio
    async def test_excludes_deleted_sessions(self):
        """The list query must filter on deleted_at IS NULL and user_id."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.exec = AsyncMock(return_value=mock_result)

        app = _make_app(mock_db)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/sessions")

        assert resp.status_code == 200

        # Verify the actual SELECT statement that was issued.
        mock_db.exec.assert_awaited_once()
        statement = mock_db.exec.await_args.args[0]
        compiled = str(
            statement.compile(compile_kwargs={"literal_binds": True})
        ).lower()
        assert "deleted_at is null" in compiled
        assert f"user_id = '{TEST_USER.oid}'" in compiled
        assert "order by" in compiled and "updated_at desc" in compiled


class TestGetSession:
    @pytest.mark.anyio
    async def test_returns_session_with_messages(self):
        session = _make_session()

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=session)

        app = _make_app(mock_db)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/sessions/{session.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["messages"]) == 1

    @pytest.mark.anyio
    async def test_returns_404_for_other_users_session(self):
        session = _make_session(user_id=OTHER_USER.oid)

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=session)

        app = _make_app(mock_db)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/sessions/{session.id}")

        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_returns_404_for_deleted_session(self):
        session = _make_session(deleted_at=datetime.now(timezone.utc))

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=session)

        app = _make_app(mock_db)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/sessions/{session.id}")

        assert resp.status_code == 404


class TestDeleteSession:
    @pytest.mark.anyio
    async def test_soft_deletes_session(self):
        session = _make_session()

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=session)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        app = _make_app(mock_db)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.delete(f"/api/sessions/{session.id}")

        assert resp.status_code == 204
        assert session.deleted_at is not None

    @pytest.mark.anyio
    async def test_returns_404_for_other_users_session(self):
        session = _make_session(user_id=OTHER_USER.oid)

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=session)

        app = _make_app(mock_db)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.delete(f"/api/sessions/{session.id}")

        assert resp.status_code == 404
