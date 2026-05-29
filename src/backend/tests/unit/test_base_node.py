"""Unit tests for BaseNode — covers dispatch, __call__."""

from unittest.mock import AsyncMock, patch

import pytest
from app.services.nodes.base import BaseNode

pytestmark = pytest.mark.unit


class _ConcreteNode(BaseNode):
    """Minimal concrete subclass for testing."""

    def __init__(self, *, auto_activate: bool = True):
        super().__init__("test_step", auto_activate=auto_activate)
        self.run_result: dict = {}
        self.should_raise = False

    async def run(self, state, config):
        if self.should_raise:
            raise ValueError("run() failed")
        return self.run_result

    def fallback(self):
        return {"fallback": True}


class TestBaseNodeCall:
    async def test_success_path_returns_state_update(self):
        node = _ConcreteNode()
        node.run_result = {"key": "value"}

        with patch(
            "app.services.nodes.base.adispatch_custom_event", new_callable=AsyncMock
        ):
            result = await node(state={}, config={})

        assert result == {"key": "value"}

    async def test_error_path_returns_fallback(self):
        node = _ConcreteNode()
        node.should_raise = True

        with patch(
            "app.services.nodes.base.adispatch_custom_event", new_callable=AsyncMock
        ):
            result = await node(state={}, config={})

        assert result == {"fallback": True}

    async def test_auto_activate_dispatches_active_status(self):
        node = _ConcreteNode(auto_activate=True)
        dispatched_events = []

        async def capture_event(name, data, config=None):
            dispatched_events.append((name, data))

        with patch(
            "app.services.nodes.base.adispatch_custom_event", side_effect=capture_event
        ):
            await node(state={}, config={})

        status_events = [e for e in dispatched_events if e[0] == "status"]
        active_events = [e for e in status_events if e[1].get("status") == "active"]
        assert len(active_events) == 1

    async def test_no_auto_activate_skips_active_status(self):
        node = _ConcreteNode(auto_activate=False)
        dispatched_events = []

        async def capture_event(name, data, config=None):
            dispatched_events.append((name, data))

        with patch(
            "app.services.nodes.base.adispatch_custom_event", side_effect=capture_event
        ):
            await node(state={}, config={})

        active_events = [e for e in dispatched_events if e[1].get("status") == "active"]
        assert len(active_events) == 0

    async def test_error_event_dispatched_on_failure(self):
        node = _ConcreteNode()
        node.should_raise = True
        dispatched_events = []

        async def capture_event(name, data, config=None):
            dispatched_events.append((name, data))

        with patch(
            "app.services.nodes.base.adispatch_custom_event", side_effect=capture_event
        ):
            await node(state={}, config={})

        error_events = [e for e in dispatched_events if e[0] == "error"]
        assert len(error_events) == 1
        assert "test_step" in error_events[0][1]["message"]
