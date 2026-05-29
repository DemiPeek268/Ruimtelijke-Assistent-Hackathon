"""Tests for the chat SSE router.

Focuses on contract guarantees of the streamed `meta` event and the persisted
assistant message. Database access is captured by a tiny in-memory fake
`AsyncSession` so we don't need Postgres running.
"""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import CurrentUser, get_current_user
from app.models.session import Session

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _stub_dictionary_service():
    """Stub dictionary_service.for_user for every test."""
    with patch(
        "app.routers.chat.dictionary_service.for_user",
        new=AsyncMock(return_value=MagicMock()),
    ):
        yield


TEST_USER = CurrentUser(oid="chat-user-oid", name="Chat Test User")


class FakeAsyncSession:
    """In-memory stand-in for sqlmodel.ext.asyncio.session.AsyncSession.

    Stores Session rows in a class-level dict so a single test can open multiple
    `async with FakeAsyncSession(...)` blocks (the chat router opens a fresh
    session for the initial save and another after streaming).
    """

    _store: dict[uuid.UUID, Session] = {}

    def __init__(self, *args, **kwargs):
        self._pending: list[Session] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, model, ident):
        return self._store.get(ident)

    def add(self, obj):
        self._pending.append(obj)

    async def commit(self):
        for obj in self._pending:
            if obj.id is None:
                obj.id = uuid.uuid4()
            self._store[obj.id] = obj
        self._pending.clear()

    async def refresh(self, obj):
        return obj

    @classmethod
    def reset(cls):
        cls._store.clear()


async def _fake_stream(*args, **kwargs):
    yield {
        "event": "on_chat_model_stream",
        "data": {"chunk": SimpleNamespace(content="Hallo wereld.")},
    }


def _build_app():
    from app.routers import chat as chat_router

    app = FastAPI()
    app.include_router(chat_router.router)
    app.state.dictionary = MagicMock()
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    return app


def _parse_sse(text: str) -> list[dict]:
    text = text.replace("\r\n", "\n")
    events: list[dict] = []
    for block in text.strip().split("\n\n"):
        current: dict = {}
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


def _stream_chat(client: TestClient, payload: dict) -> list[dict]:
    with client.stream("POST", "/api/chat", json=payload) as resp:
        assert resp.status_code == 200, resp.read()[:300]
        body = resp.read().decode()
    return _parse_sse(body)


class TestChatMessageId:
    def setup_method(self):
        FakeAsyncSession.reset()

    def test_meta_message_id_matches_persisted_assistant_message_id(self):
        """The `message_id` broadcast in the SSE meta event must be the same id
        used when persisting the assistant message to the session."""
        app = _build_app()

        with (
            patch("app.routers.chat.AsyncSession", FakeAsyncSession),
            patch("app.routers.chat.workflow") as mock_wf,
        ):
            mock_wf.astream_events = _fake_stream
            with TestClient(app) as client:
                events = _stream_chat(
                    client,
                    {"messages": [{"role": "user", "content": "Hoi"}]},
                )

        meta = next(e for e in events if e.get("event") == "meta")
        broadcast_id = meta["data"]["message_id"]
        assert broadcast_id, "meta event missing message_id"

        sessions = list(FakeAsyncSession._store.values())
        assert len(sessions) == 1
        assistant_messages = [
            m for m in sessions[0].messages if m["role"] == "assistant"
        ]
        assert len(assistant_messages) == 1
        assert assistant_messages[0]["id"] == broadcast_id

    def test_empty_stream_does_not_persist_assistant_message(self):
        """If the workflow yields no content (e.g., an exception fires before
        any chunk), no assistant message should be persisted — the meta event
        already broadcast a message_id, but feedback on a content-less message
        would 404 anyway, and storing an empty bubble pollutes the session."""
        app = _build_app()

        async def _failing_stream(*args, **kwargs):
            raise RuntimeError("workflow blew up immediately")
            yield  # pragma: no cover — marks the function as a generator

        with (
            patch("app.routers.chat.AsyncSession", FakeAsyncSession),
            patch("app.routers.chat.workflow") as mock_wf,
        ):
            mock_wf.astream_events = _failing_stream
            with TestClient(app) as client:
                _stream_chat(
                    client,
                    {"messages": [{"role": "user", "content": "Hoi"}]},
                )

        sessions = list(FakeAsyncSession._store.values())
        assert len(sessions) == 1
        assistant_messages = [
            m for m in sessions[0].messages if m["role"] == "assistant"
        ]
        assert assistant_messages == [], (
            f"empty stream should not persist an assistant message, "
            f"got: {assistant_messages}"
        )

    def test_meta_event_has_no_request_id_field(self):
        """`request_id` is replaced by `message_id`; the legacy key must be gone."""
        app = _build_app()

        with (
            patch("app.routers.chat.AsyncSession", FakeAsyncSession),
            patch("app.routers.chat.workflow") as mock_wf,
        ):
            mock_wf.astream_events = _fake_stream
            with TestClient(app) as client:
                events = _stream_chat(
                    client,
                    {"messages": [{"role": "user", "content": "Hoi"}]},
                )

        meta = next(e for e in events if e.get("event") == "meta")
        assert "request_id" not in meta["data"]


class TestChatMlflowTraceLabeling:
    """Slice 4: the assistant `message_id` must be set as the trace's
    `client_request_id` so the feedback endpoint can later resolve trace → message.
    """

    def setup_method(self):
        FakeAsyncSession.reset()

    def test_trace_labeled_with_assistant_message_id_when_mlflow_enabled(self):
        """When MLFLOW_ENABLED is True, the chat turn wraps streaming in an
        mlflow span and tags the trace with `client_request_id=<assistant_msg_id>`."""
        app = _build_app()

        with (
            patch("app.routers.chat.AsyncSession", FakeAsyncSession),
            patch("app.routers.chat.workflow") as mock_wf,
            patch("app.routers.chat.settings") as mock_settings,
            patch("app.routers.chat.mlflow") as mock_mlflow,
        ):
            mock_settings.MLFLOW_ENABLED = True
            mock_wf.astream_events = _fake_stream
            # `with mlflow.start_span(...)` returns a context manager.
            mock_mlflow.start_span.return_value.__enter__ = lambda *_: MagicMock()
            mock_mlflow.start_span.return_value.__exit__ = lambda *_: False

            with TestClient(app) as client:
                events = _stream_chat(
                    client,
                    {"messages": [{"role": "user", "content": "Hoi"}]},
                )

        meta = next(e for e in events if e.get("event") == "meta")
        assistant_msg_id = meta["data"]["message_id"]

        # The wrap span is named so it's discoverable in the MLflow UI.
        mock_mlflow.start_span.assert_called_once()
        span_name = mock_mlflow.start_span.call_args.args[0]
        assert span_name == "chat_turn"

        # client_request_id MUST be the same id broadcast in the SSE meta event.
        # session_id groups traces by conversation in the MLflow UI.
        mock_mlflow.update_current_trace.assert_called_once()
        kwargs = mock_mlflow.update_current_trace.call_args.kwargs
        assert kwargs["client_request_id"] == assistant_msg_id
        assert kwargs["session_id"]  # set, non-empty

    def test_chat_turn_span_carries_user_message_input_and_response_output(self):
        """The chat_turn span must capture the user message as input and the
        assembled assistant content as output, so the MLflow UI's request and
        response columns are populated (autolog spans are children and don't
        propagate I/O to the root)."""
        app = _build_app()
        fake_span = MagicMock()

        with (
            patch("app.routers.chat.AsyncSession", FakeAsyncSession),
            patch("app.routers.chat.workflow") as mock_wf,
            patch("app.routers.chat.settings") as mock_settings,
            patch("app.routers.chat.mlflow") as mock_mlflow,
        ):
            mock_settings.MLFLOW_ENABLED = True
            mock_wf.astream_events = _fake_stream
            mock_mlflow.start_span.return_value.__enter__ = lambda *_: fake_span
            mock_mlflow.start_span.return_value.__exit__ = lambda *_: False
            mock_mlflow.get_current_active_span.return_value = fake_span

            with TestClient(app) as client:
                _stream_chat(
                    client,
                    {"messages": [{"role": "user", "content": "Hoi"}]},
                )

        fake_span.set_inputs.assert_called_once_with({"user_message": "Hoi"})
        fake_span.set_outputs.assert_called_once()
        outputs = fake_span.set_outputs.call_args.args[0]
        assert outputs["content"] == "Hallo wereld."

    def test_no_mlflow_calls_when_disabled(self):
        """MLFLOW_ENABLED=False → no `start_span` or `update_current_trace`."""
        app = _build_app()

        with (
            patch("app.routers.chat.AsyncSession", FakeAsyncSession),
            patch("app.routers.chat.workflow") as mock_wf,
            patch("app.routers.chat.settings") as mock_settings,
            patch("app.routers.chat.mlflow") as mock_mlflow,
        ):
            mock_settings.MLFLOW_ENABLED = False
            mock_wf.astream_events = _fake_stream

            with TestClient(app) as client:
                _stream_chat(
                    client,
                    {"messages": [{"role": "user", "content": "Hoi"}]},
                )

        mock_mlflow.start_span.assert_not_called()
        mock_mlflow.update_current_trace.assert_not_called()

    def test_mlflow_failure_does_not_break_chat(self):
        """If `mlflow.start_span` blows up, the chat request must still stream
        normally — observability is best-effort, not load-bearing."""
        app = _build_app()

        with (
            patch("app.routers.chat.AsyncSession", FakeAsyncSession),
            patch("app.routers.chat.workflow") as mock_wf,
            patch("app.routers.chat.settings") as mock_settings,
            patch("app.routers.chat.mlflow") as mock_mlflow,
        ):
            mock_settings.MLFLOW_ENABLED = True
            mock_wf.astream_events = _fake_stream
            mock_mlflow.start_span.side_effect = RuntimeError("mlflow down")

            with TestClient(app) as client:
                events = _stream_chat(
                    client,
                    {"messages": [{"role": "user", "content": "Hoi"}]},
                )

        # The meta event still went out, and we still got the model chunk.
        assert any(e.get("event") == "meta" for e in events)
        assert any(e.get("event") == "text" for e in events)
