import contextlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Literal

import mlflow
from fastapi import APIRouter, Depends, Request
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession
from sse_starlette import EventSourceResponse

from app.auth import (
    CurrentUser,
    get_current_user,
    require_session_access,
)
from app.config import settings
from app.database import engine
from app.models.chat import ChatRequest
from app.models.session import Session, SessionMessage, ThinkingStep
from app.models.state import MapPlan
from app.services import dictionary_service
from app.services.workflow import workflow

logger = logging.getLogger(__name__)

router = APIRouter()

CUSTOM_EVENT_TO_SSE = {
    "map_block": "map_config",
    "map_data": "map_data",
    "follow_up_text": "text",
    "status": "status",
    "error": "error",
    "step_thinking_summary": "step_thinking_summary",
}

MAX_TITLE_LENGTH = 100


async def _resolve_session(
    chat_request: ChatRequest,
    user: CurrentUser,
    db: AsyncSession,
) -> Session:
    """Load existing session or create a new one."""
    if chat_request.session_id is not None:
        return require_session_access(
            await db.get(Session, chat_request.session_id), user
        )

    # New session — auto-title from first user message
    first_msg = chat_request.messages[-1].content if chat_request.messages else ""
    title = first_msg[:MAX_TITLE_LENGTH] if first_msg else None

    session = Session(
        user_id=user.oid,
        title=title,
        messages=[],
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


def _make_message(
    role: Literal["user", "assistant"],
    content: str,
    message_id: str | None = None,
    sql: str | None = None,
    map_config: MapPlan | None = None,
    thinking_steps: list[ThinkingStep] | None = None,
) -> dict:
    """Build a validated SessionMessage and serialize it for JSON storage."""
    return SessionMessage(
        id=message_id or str(uuid.uuid4()),
        role=role,
        content=content,
        sql=sql,
        map_config=map_config,
        thinking_steps=thinking_steps or [],
        created_at=datetime.now(timezone.utc).isoformat(),
    ).model_dump(mode="json")


@router.post("/api/chat")
async def chat(
    chat_request: ChatRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    dictionary = await dictionary_service.for_user()

    # Resolve the session and save the user message in a short-lived DB session.
    # We capture the session_id and current messages so the SSE generator can
    # open its own DB session later (the DI session closes when this function returns).
    async with AsyncSession(engine, expire_on_commit=False) as db:
        session = await _resolve_session(chat_request, user, db)

        user_content = (
            chat_request.messages[-1].content if chat_request.messages else ""
        )
        session.messages = session.messages + [_make_message("user", user_content)]
        session.updated_at = datetime.now(timezone.utc)
        db.add(session)
        await db.commit()

    session_id = session.id
    current_messages = list(session.messages)
    request_id = f"req_{int(time.time() * 1000)}"
    workflow_config: RunnableConfig = {
        "metadata": {"session_id": str(session_id), "request_id": request_id},
        "tags": [f"session:{session_id}"],
        "run_name": "chat_workflow",
    }

    initial_state = {
        "messages": [
            {"role": m.role, "content": m.content} for m in chat_request.messages
        ],
        "dictionary": dictionary,
        "model": chat_request.model,
        "intent_analysis": None,
        "needs_spatial_resolution": False,
        "pdok_used": False,
        "sql_query": None,
        "query_result": None,
        "map_plan": None,
        "explanation": None,
    }

    async def event_generator():
        assistant_msg_id = str(uuid.uuid4())
        assistant_content = ""
        assistant_sql: str | None = None
        assistant_map_config: MapPlan | None = None
        thinking_steps: dict[str, ThinkingStep] = {}

        yield {
            "event": "meta",
            "data": json.dumps(
                {
                    "message_id": assistant_msg_id,
                    "session_id": str(session_id),
                    "model": chat_request.model,
                    "timestamp": time.time(),
                }
            ),
        }

        # Wrap the workflow stream in an MLflow span so we can tag the trace
        # with `client_request_id = assistant_msg_id`. This lets the feedback
        # endpoint later resolve `message_id → trace_id` via `search_traces`.
        # Best-effort: any failure here is swallowed and we fall back to a
        # no-op context manager so chat keeps working.
        if settings.MLFLOW_ENABLED:
            try:
                trace_ctx = mlflow.start_span("chat_turn")
            except Exception:
                logger.warning(
                    "mlflow.start_span failed — chat will run untraced",
                    exc_info=True,
                )
                trace_ctx = contextlib.nullcontext()
        else:
            trace_ctx = contextlib.nullcontext()

        try:
            with trace_ctx:
                if settings.MLFLOW_ENABLED:
                    try:
                        # session_id groups all turns of a conversation in the
                        # MLflow UI; client_request_id is the per-turn bridge to
                        # the feedback endpoint.
                        mlflow.update_current_trace(
                            client_request_id=assistant_msg_id,
                            session_id=str(session_id),
                        )
                        # Setting inputs on the chat_turn span populates the
                        # trace's request column in the UI (otherwise blank,
                        # since autolog spans are children and their I/O does
                        # not propagate to the root).
                        span = mlflow.get_current_active_span()
                        if span is not None:
                            span.set_inputs({"user_message": user_content})
                    except Exception:
                        logger.warning(
                            "mlflow trace metadata update failed for %s",
                            assistant_msg_id,
                            exc_info=True,
                        )

                async for event in workflow.astream_events(
                    initial_state,
                    config=workflow_config,
                    version="v2",
                ):
                    if event["event"] == "on_chat_model_stream":
                        chunk = event["data"].get("chunk")
                        content = chunk.content if chunk is not None else ""
                        if content:
                            assistant_content += content
                            yield {
                                "event": "text",
                                "data": json.dumps({"content": content}),
                            }

                    elif event["event"] == "on_custom_event":
                        name = event["name"]
                        data = event["data"]
                        sse_event = CUSTOM_EVENT_TO_SSE.get(name)

                        if sse_event:
                            yield {"event": sse_event, "data": json.dumps(data)}

                        if name == "sql_block":
                            assistant_sql = data.get("query")
                        elif name == "map_block":
                            # Validate at write-time so persisted shape is canonical;
                            # if the workflow ever emits a non-MapPlan payload, we
                            # log and drop the field instead of poisoning sessions.
                            try:
                                assistant_map_config = MapPlan.model_validate(data)
                            except ValidationError:
                                logger.exception(
                                    "map_block payload failed MapPlan validation"
                                )
                                assistant_map_config = None
                        elif name == "follow_up_text":
                            assistant_content += data.get("content", "")
                        elif name == "step_thinking_summary":
                            step_id = data.get("step_id")
                            if step_id:
                                thinking_steps[step_id] = ThinkingStep(
                                    step_id=step_id,
                                    summary=data.get("summary", ""),
                                )

                    if await request.is_disconnected():
                        break

                if settings.MLFLOW_ENABLED:
                    try:
                        span = mlflow.get_current_active_span()
                        if span is not None:
                            span.set_outputs(
                                {"content": assistant_content, "sql": assistant_sql}
                            )
                    except Exception:
                        logger.warning(
                            "mlflow chat_turn outputs update failed",
                            exc_info=True,
                        )

        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"message": f"Er ging iets mis: {str(e)}"}),
            }

        # Save assistant message in a fresh DB session — the DI session is long gone.
        # Wrapped in try/except so a DB failure here doesn't prevent the client
        # from receiving `done`; a half-streamed response is better than the
        # client thinking the connection died.
        #
        # Skip persistence when the turn produced nothing of value — feedback
        # buttons would resolve to a content-less message_id (POST → 404) and
        # the empty bubble would clutter the session in the sidebar.
        has_content = bool(assistant_content or assistant_sql or assistant_map_config)
        if has_content:
            try:
                async with AsyncSession(engine) as db:
                    updated_messages = current_messages + [
                        _make_message(
                            "assistant",
                            assistant_content,
                            message_id=assistant_msg_id,
                            sql=assistant_sql,
                            map_config=assistant_map_config,
                            thinking_steps=list(thinking_steps.values()),
                        )
                    ]
                    session_obj = await db.get(Session, session_id)
                    if session_obj is not None:
                        session_obj.messages = updated_messages
                        session_obj.updated_at = datetime.now(timezone.utc)
                        db.add(session_obj)
                        await db.commit()
            except Exception:
                logger.exception(
                    "Failed to persist assistant message for %s", session_id
                )

        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_generator())
