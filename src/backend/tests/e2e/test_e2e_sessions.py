"""
End-to-end test for session persistence.

Exercises the full HTTP flow with auth bypassed at the dependency level.
Uses a real uvicorn server so SSE streaming + async DB work correctly.
"""

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth import CurrentUser, get_current_user
from app.config import settings
from app.database import get_session
from app.models.session import Session
from app.routers import chat, sessions
from app.services import dictionary_service

# ---------- config ----------

TEST_PORT = 18765
USER_A = CurrentUser(oid="e2e-user-a", name="User A")
USER_B = CurrentUser(oid="e2e-user-b", name="User B")

engine = create_async_engine(settings.DATABASE_URL, echo=False)

_active_user = USER_A


def _current_user():
    return _active_user


async def _real_db():
    async with AsyncSession(engine) as session:
        yield session


# ---------- fake workflow ----------


async def _fake_stream_events(*args, **kwargs):
    for token in ["Hallo", ", er zijn", " 100 woningen."]:
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": SimpleNamespace(content=token)},
        }
    yield {
        "event": "on_custom_event",
        "name": "sql_block",
        "data": {"query": "SELECT count(*) FROM woningen"},
    }
    yield {
        "event": "on_custom_event",
        "name": "map_block",
        "data": {"h3_column": "h3", "value_column": "count", "label": "Woningen"},
    }


async def _followup_stream(*args, **kwargs):
    yield {
        "event": "on_chat_model_stream",
        "data": {"chunk": SimpleNamespace(content="Dat is correct.")},
    }


# ---------- build test app ----------


def _build_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        dictionary_service.set_local_dictionary(MagicMock())
        yield
        dictionary_service.set_local_dictionary(None)

    test_app = FastAPI(lifespan=lifespan)
    test_app.include_router(chat.router)
    test_app.include_router(sessions.router)

    test_app.dependency_overrides[get_current_user] = _current_user
    test_app.dependency_overrides[get_session] = _real_db

    return test_app


# ---------- helpers ----------


def _parse_sse(text: str) -> list[dict]:
    events = []
    # SSE blocks are separated by double newlines (may use \r\n)
    text = text.replace("\r\n", "\n")
    for block in text.strip().split("\n\n"):
        current = {}
        for line in block.strip().split("\n"):
            line = line.strip()
            if line.startswith("event:"):
                current["event"] = line[6:].strip()
            elif line.startswith("data:"):
                raw = line[5:].strip()
                try:
                    current["data"] = json.loads(raw)
                except json.JSONDecodeError:
                    current["data"] = raw
        if current:
            events.append(current)
    return events


async def _cleanup():
    async with AsyncSession(engine) as db:
        from sqlmodel import select

        result = await db.exec(
            select(Session).where(Session.user_id.in_([USER_A.oid, USER_B.oid]))
        )
        for s in result.all():
            await db.delete(s)
        await db.commit()


# ---------- test ----------


@pytest.mark.e2e
async def test_full_flow(monkeypatch):
    global _active_user

    test_app = _build_app()
    await _cleanup()

    config = uvicorn.Config(
        test_app, host="127.0.0.1", port=TEST_PORT, log_level="error"
    )
    server = uvicorn.Server(config)
    serve_task = asyncio.create_task(server.serve())

    # Wait for server readiness
    for _ in range(50):
        try:
            async with httpx.AsyncClient() as c:
                await c.get(f"http://127.0.0.1:{TEST_PORT}/docs")
            break
        except httpx.ConnectError:
            await asyncio.sleep(0.1)

    base = f"http://127.0.0.1:{TEST_PORT}"

    try:
        async with httpx.AsyncClient(base_url=base, timeout=15) as client:
            # ---- 1. List sessions (empty) ----
            _active_user = USER_A
            resp = await client.get("/api/sessions")
            assert resp.status_code == 200 and resp.json() == []
            print("PASS  1. List sessions (empty)")

            # ---- 2. Send first chat → creates session ----
            with patch("app.routers.chat.workflow") as mock_wf:
                mock_wf.astream_events = _fake_stream_events
                resp = await client.post(
                    "/api/chat",
                    json={
                        "messages": [
                            {
                                "role": "user",
                                "content": "Hoeveel woningen in Den Haag?",
                            }
                        ],
                        "model": "gpt-5-chat",
                    },
                )
                assert resp.status_code == 200, (
                    f"Chat: {resp.status_code} {resp.text[:300]}"
                )
                events = _parse_sse(resp.text)

            meta = next((e for e in events if e.get("event") == "meta"), None)
            assert meta is not None, f"No meta event in {len(events)} events"
            session_id = meta["data"]["session_id"]
            assert session_id
            print(f"PASS  2a. Chat created session: {session_id}")

            full_text = "".join(
                e["data"]["content"] for e in events if e.get("event") == "text"
            )
            assert "100 woningen" in full_text
            print(f"PASS  2b. Streamed text: '{full_text}'")

            assert any(e.get("event") == "sql" for e in events)
            print("PASS  2c. SQL event received")

            assert any(e.get("event") == "map_config" for e in events)
            print("PASS  2d. Map config event received")

            assert any(e.get("event") == "done" for e in events)
            print("PASS  2e. Done event received")

            # ---- 3. List sessions (1) ----
            resp = await client.get("/api/sessions")
            sessions_list = resp.json()
            assert len(sessions_list) == 1
            assert sessions_list[0]["id"] == session_id
            assert sessions_list[0]["title"] == "Hoeveel woningen in Den Haag?"
            print(f"PASS  3. Session in list: '{sessions_list[0]['title']}'")

            # ---- 4. Get session detail ----
            resp = await client.get(f"/api/sessions/{session_id}")
            assert resp.status_code == 200
            detail = resp.json()
            assert len(detail["messages"]) == 2
            assert detail["messages"][0]["role"] == "user"
            assert detail["messages"][0]["content"] == "Hoeveel woningen in Den Haag?"
            assert detail["messages"][1]["role"] == "assistant"
            assert "100 woningen" in detail["messages"][1]["content"]
            assert detail["messages"][1]["sql"] == "SELECT count(*) FROM woningen"
            assert detail["messages"][1]["map_config"]["h3_column"] == "h3"
            for m in detail["messages"]:
                uuid.UUID(m["id"])
            print("PASS  4. Session detail: 2 messages, SQL, map_config, UUIDs")

            # ---- 5. Follow-up → appends to same session ----
            with patch("app.routers.chat.workflow") as mock_wf:
                mock_wf.astream_events = _followup_stream
                resp = await client.post(
                    "/api/chat",
                    json={
                        "messages": [
                            {
                                "role": "user",
                                "content": "Hoeveel woningen in Den Haag?",
                            },
                            {
                                "role": "assistant",
                                "content": "Hallo, er zijn 100 woningen.",
                            },
                            {
                                "role": "user",
                                "content": "Is dat inclusief nieuwbouw?",
                            },
                        ],
                        "model": "gpt-5-chat",
                        "session_id": session_id,
                    },
                )
                assert resp.status_code == 200
                events = _parse_sse(resp.text)

            meta = next(e for e in events if e.get("event") == "meta")
            assert meta["data"]["session_id"] == session_id
            print("PASS  5a. Follow-up uses same session_id")

            resp = await client.get(f"/api/sessions/{session_id}")
            detail = resp.json()
            assert len(detail["messages"]) == 4
            assert detail["messages"][2]["content"] == "Is dat inclusief nieuwbouw?"
            assert detail["messages"][3]["content"] == "Dat is correct."
            print("PASS  5b. Session has 4 messages after follow-up")

            # ---- 6. Ownership isolation ----
            _active_user = USER_B

            resp = await client.get("/api/sessions")
            assert resp.json() == []
            print("PASS  6a. User B sees empty list")

            resp = await client.get(f"/api/sessions/{session_id}")
            assert resp.status_code == 404
            print("PASS  6b. User B gets 404 for User A's session")

            resp = await client.delete(f"/api/sessions/{session_id}")
            assert resp.status_code == 404
            print("PASS  6c. User B can't delete User A's session")

            # ---- 7. Soft delete ----
            _active_user = USER_A

            resp = await client.delete(f"/api/sessions/{session_id}")
            assert resp.status_code == 204
            print("PASS  7a. Soft delete returns 204")

            resp = await client.get("/api/sessions")
            assert resp.json() == []
            print("PASS  7b. Deleted session not in list")

            resp = await client.get(f"/api/sessions/{session_id}")
            assert resp.status_code == 404
            print("PASS  7c. Deleted session returns 404")

            resp = await client.delete(f"/api/sessions/{session_id}")
            assert resp.status_code == 404
            print("PASS  7d. Can't re-delete")

            # ---- 8. Non-existent session_id → 404 ----
            with patch("app.routers.chat.workflow") as mock_wf:
                mock_wf.astream_events = _fake_stream_events
                resp = await client.post(
                    "/api/chat",
                    json={
                        "messages": [{"role": "user", "content": "test"}],
                        "session_id": str(uuid.uuid4()),
                    },
                )
                assert resp.status_code == 404
                print("PASS  8. Chat with bad session_id returns 404")

        print()
        print("=" * 50)
        print("ALL E2E TESTS PASSED")
        print("=" * 50)

    finally:
        await _cleanup()
        server.should_exit = True
        await serve_task
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_full_flow())
