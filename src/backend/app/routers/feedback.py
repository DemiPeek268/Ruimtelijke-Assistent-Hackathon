import asyncio
import hashlib
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth import CurrentUser, get_current_user, require_session_access
from app.database import get_session
from app.mlflow_monitoring.feedback import log_feedback_to_mlflow
from app.models.feedback import FeedbackRequest, FeedbackResponse, MessageFeedback
from app.models.session import Session

logger = logging.getLogger(__name__)

router = APIRouter()


def _advisory_key(message_id: str, user_id: str) -> int:
    """64-bit signed int key for `pg_advisory_lock` derived from (message_id, user_id).

    Hashing into a bigint loses pair-uniqueness — collisions are possible but
    harmless (a colliding pair just serializes one extra unrelated request).
    """
    digest = hashlib.blake2b(
        f"{message_id}\x00{user_id}".encode("utf-8"), digest_size=8
    ).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


async def _acquire_advisory_lock(db: AsyncSession, key: int) -> None:
    """Block until the per-(message, user) Postgres advisory lock is held.

    Session-level (not transactional) so it survives the intermediate commits
    inside the handler and continues to cover the downstream MLflow call.
    Must be paired with `_release_advisory_lock`.
    """
    await db.exec(text("SELECT pg_advisory_lock(:k)").bindparams(k=key))  # pyright: ignore[reportArgumentType]


async def _release_advisory_lock(db: AsyncSession, key: int) -> None:
    """Release the per-(message, user) Postgres advisory lock.

    If the release itself errors (e.g. connection went bad), Postgres frees
    the lock when the connection is closed, so we log and move on instead of
    bubbling a 500 for a request whose Postgres write already succeeded.
    """
    try:
        await db.exec(text("SELECT pg_advisory_unlock(:k)").bindparams(k=key))  # pyright: ignore[reportArgumentType]
    except Exception:
        logger.warning(
            "pg_advisory_unlock failed; lock will release on connection close",
            exc_info=True,
        )


@router.post(
    "/api/sessions/{session_id}/messages/{message_id}/feedback",
    response_model=FeedbackResponse,
)
async def post_feedback(
    session_id: uuid.UUID,
    message_id: str,
    body: FeedbackRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> FeedbackResponse:
    session = require_session_access(await db.get(Session, session_id), user)

    target = next((m for m in session.messages if m.get("id") == message_id), None)
    if target is None or target.get("role") != "assistant":
        raise HTTPException(status_code=404, detail="Message not found")

    # Serialize concurrent clicks on the same (message, user) so the Postgres
    # write and the MLflow side-effect run atomically. Without this, rapid
    # up→down clicks could both observe "no prior MLflow assessment" and each
    # call `log_assessment`, leaving the trace with two `user_thumbs` entries.
    lock_key = _advisory_key(message_id, user.oid)
    await _acquire_advisory_lock(db, lock_key)
    try:
        return await _apply_feedback(
            session_id=session_id,
            message_id=message_id,
            body=body,
            user=user,
            db=db,
        )
    finally:
        await _release_advisory_lock(db, lock_key)


async def _apply_feedback(
    *,
    session_id: uuid.UUID,
    message_id: str,
    body: FeedbackRequest,
    user: CurrentUser,
    db: AsyncSession,
) -> FeedbackResponse:
    existing = (
        await db.exec(
            select(MessageFeedback)
            .where(MessageFeedback.message_id == message_id)
            .where(MessageFeedback.user_id == user.oid)
        )
    ).first()

    if body.rating is None:
        if existing is not None:
            await db.delete(existing)
            await db.commit()
        await asyncio.to_thread(
            log_feedback_to_mlflow,
            message_id=message_id,
            rating=None,
            user_id=user.oid,
            comment=None,
        )
        return FeedbackResponse(rating=None, comment=None, updated_at=None)

    if existing is None:
        row = MessageFeedback(
            session_id=session_id,
            message_id=message_id,
            user_id=user.oid,
            rating=body.rating,
            comment=body.comment if body.comment_provided else None,
        )
        db.add(row)
    else:
        # SQLAlchemy tracks attached instances; no need to re-add(). The
        # model's `onupdate=_utcnow` advances updated_at on commit.
        existing.rating = body.rating
        if body.comment_provided:
            existing.comment = body.comment
        row = existing
    await db.commit()
    await db.refresh(row)

    await asyncio.to_thread(
        log_feedback_to_mlflow,
        message_id=message_id,
        rating=row.rating,
        user_id=user.oid,
        comment=row.comment,
    )

    return FeedbackResponse(
        rating=row.rating,  # type: ignore[arg-type]
        comment=row.comment,
        updated_at=row.updated_at,
    )
