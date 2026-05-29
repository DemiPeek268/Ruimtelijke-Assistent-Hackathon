"""Unit tests for the app warm-up."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

pytestmark = pytest.mark.unit


class TestWarmUp:
    async def test_local_path_calls_generate_dictionary(self):
        from app.main import _warm_up
        from app.models.dictionary import DataDictionary

        fake_dict = MagicMock(spec=DataDictionary)
        fake_dict.total_columns = 1
        fake_dict.themes = []

        with (
            patch("app.main.generate_dictionary", AsyncMock(return_value=fake_dict)),
            patch("app.main.dictionary_service.set_local_dictionary") as set_local,
        ):
            app = FastAPI()
            await _warm_up(app)

        set_local.assert_called_once_with(fake_dict)
        assert app.state.ready is True

    async def test_warm_up_failure_does_not_set_ready(self):
        from app.main import _warm_up

        with patch(
            "app.main.generate_dictionary",
            AsyncMock(side_effect=RuntimeError("disk error")),
        ):
            app = FastAPI()
            app.state.ready = False
            await _warm_up(app)

        assert app.state.ready is False
