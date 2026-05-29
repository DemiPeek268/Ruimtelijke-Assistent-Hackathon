from fastapi import HTTPException
from pydantic import BaseModel

from app.models.session import Session


class CurrentUser(BaseModel):
    oid: str
    name: str


async def get_current_user() -> CurrentUser:
    return CurrentUser(oid="local-user", name="Local User")


def require_session_access(session: Session | None, user: CurrentUser) -> Session:
    """Return session if it exists, belongs to the user, and is not deleted; else 404."""
    if session is None or session.user_id != user.oid or session.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session
