import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlalchemy import DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel

Rating = Literal["up", "down"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MessageFeedback(SQLModel, table=True):
    __tablename__ = "message_feedback"  # pyright: ignore[reportAssignmentType]
    # The unique composite index on (message_id, user_id) is the only lookup
    # path used today (single-row in the router, IN-list in sessions.py), so
    # no separate per-column indexes are needed.
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_message_feedback_msg_user"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(foreign_key="sessions.id")
    message_id: str = Field(max_length=64)
    user_id: str = Field(max_length=255)
    # Stored as varchar; values constrained to {"up", "down"} by the API layer.
    rating: str = Field(max_length=8)
    comment: str | None = Field(default=None, max_length=2000)
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),  # pyright: ignore[reportArgumentType]
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),  # pyright: ignore[reportArgumentType]
        sa_column_kwargs={"onupdate": _utcnow},
    )


class FeedbackRequest(BaseModel):
    rating: Rating | None
    comment: str | None = PydanticField(default=None, max_length=2000)

    @property
    def comment_provided(self) -> bool:
        """True if `comment` was set explicitly (incl. ""); False if omitted.

        Distinguishes "leave existing untouched" (omitted) from
        "overwrite, including with empty string" (present).
        """
        return "comment" in self.model_fields_set


class FeedbackResponse(BaseModel):
    rating: Rating | None
    comment: str | None = None
    # None when no row exists (e.g., clear with nothing to clear); a real
    # timestamp otherwise. Avoids synthesizing a fake timestamp for a row
    # that was never written.
    updated_at: datetime | None = None
