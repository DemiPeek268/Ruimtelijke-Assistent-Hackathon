"""Tests for auth stub."""

import pytest

pytestmark = pytest.mark.unit


class TestGetCurrentUser:
    async def test_returns_local_user(self):
        from app.auth import get_current_user

        user = await get_current_user()

        assert user.oid == "local-user"
        assert user.name == "Local User"


class TestRequireSessionAccess:
    def test_returns_session_when_owned(self):
        from app.auth import CurrentUser, require_session_access
        from app.models.session import Session

        session = Session(user_id="local-user", title="test")
        user = CurrentUser(oid="local-user", name="Local User")
        result = require_session_access(session, user)
        assert result is session

    def test_raises_404_when_session_none(self):
        from fastapi import HTTPException

        from app.auth import CurrentUser, require_session_access

        user = CurrentUser(oid="local-user", name="Local User")
        with pytest.raises(HTTPException) as exc:
            require_session_access(None, user)
        assert exc.value.status_code == 404

    def test_raises_404_when_wrong_owner(self):
        from fastapi import HTTPException

        from app.auth import CurrentUser, require_session_access
        from app.models.session import Session

        session = Session(user_id="other-user", title="test")
        user = CurrentUser(oid="local-user", name="Local User")
        with pytest.raises(HTTPException) as exc:
            require_session_access(session, user)
        assert exc.value.status_code == 404
