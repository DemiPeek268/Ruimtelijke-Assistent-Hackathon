import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth import CurrentUser, get_current_user, require_session_access
from app.database import get_session
from app.models.feedback import MessageFeedback
from app.models.session import (
    MessageFeedbackPublic,
    Session,
    SessionDetail,
    SessionMessage,
    SessionPublic,
)

router = APIRouter()


@router.get("/api/sessions", response_model=list[SessionPublic])
async def list_sessions(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> Sequence[Session]:
    statement = (
        select(Session)
        .where(Session.user_id == user.oid)
        .where(col(Session.deleted_at).is_(None))
        .order_by(col(Session.updated_at).desc())
    )
    result = await db.exec(statement)
    return result.all()


@router.get("/api/sessions/{session_id}", response_model=SessionDetail)
async def get_session_detail(
    session_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> SessionDetail:
    session = await db.get(Session, session_id)
    session = require_session_access(session, user)

    # Batch-load this user's feedback for every assistant message in one query.
    assistant_ids = [m["id"] for m in session.messages if m.get("role") == "assistant"]
    feedback_by_msg: dict[str, MessageFeedback] = {}
    if assistant_ids:
        statement = (
            select(MessageFeedback)
            .where(MessageFeedback.user_id == user.oid)
            .where(col(MessageFeedback.message_id).in_(assistant_ids))
        )
        rows = (await db.exec(statement)).all()
        feedback_by_msg = {r.message_id: r for r in rows}

    messages: list[SessionMessage] = []
    for m in session.messages:
        feedback: MessageFeedbackPublic | None = None
        if m.get("role") == "assistant":
            fb = feedback_by_msg.get(m["id"])
            if fb is not None:
                feedback = MessageFeedbackPublic(
                    rating=fb.rating,  # type: ignore[arg-type]
                    comment=fb.comment,
                    updated_at=fb.updated_at,
                )
        messages.append(SessionMessage.model_validate({**m, "feedback": feedback}))

    return SessionDetail(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=messages,
    )


@router.delete("/api/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    session = await db.get(Session, session_id)
    session = require_session_access(session, user)
    session.deleted_at = datetime.now(timezone.utc)
    db.add(session)
    await db.commit()
    return Response(status_code=204)
