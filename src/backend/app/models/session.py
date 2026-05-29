import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.models.state import MapPlan


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ThinkingStep(BaseModel):
    step_id: str
    summary: str = ""


class MessageFeedbackPublic(BaseModel):
    """Per-message feedback embedded in `GET /api/sessions/{id}`."""

    rating: Literal["up", "down"]
    comment: str | None = None
    updated_at: datetime


class SessionMessage(BaseModel):
    """Canonical shape of a single chat turn persisted in `sessions.messages`."""

    id: str
    role: Literal["user", "assistant"]
    content: str
    sql: str | None = None
    map_config: MapPlan | None = None
    thinking_steps: list[ThinkingStep] = []
    created_at: str  # ISO-8601 UTC
    feedback: MessageFeedbackPublic | None = None


class SessionBase(SQLModel):
    user_id: str = Field(index=True, max_length=255)
    title: str | None = Field(default=None, max_length=500)


class Session(SessionBase, table=True):
    __tablename__ = "sessions"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # JSONB so PostgreSQL stores it in a binary, indexable form. We don't query
    # into messages today, but JSONB is the better default (validation + size).
    messages: list[dict] = Field(default_factory=list, sa_type=JSONB)
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),  # pyright: ignore[reportArgumentType]
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),  # pyright: ignore[reportArgumentType]
    )
    deleted_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # pyright: ignore[reportArgumentType]
    )


class SessionCreate(SessionBase):
    pass


class SessionPublic(SQLModel):
    """List view — no messages."""

    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class SessionDetail(SessionPublic):
    """Detail view — includes messages."""

    messages: list[SessionMessage]
