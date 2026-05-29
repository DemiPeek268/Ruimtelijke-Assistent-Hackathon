"""Unit tests for app.services.llm.make_llm."""

from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit


class TestMakeLlm:
    def test_non_reasoning_model_includes_temperature(self):
        with patch("app.services.llm.ChatOpenAI") as mock_cls:
            from app.services.llm import make_llm

            make_llm("gpt-4o")
            kwargs = mock_cls.call_args[1]
            assert kwargs["model"] == "gpt-4o"
            assert "temperature" in kwargs

    def test_reasoning_model_omits_temperature(self):
        with patch("app.services.llm.ChatOpenAI") as mock_cls:
            from app.services.llm import make_llm

            make_llm("o3-mini")
            kwargs = mock_cls.call_args[1]
            assert "temperature" not in kwargs

    def test_o4_model_omits_temperature(self):
        with patch("app.services.llm.ChatOpenAI") as mock_cls:
            from app.services.llm import make_llm

            make_llm("o4-mini")
            kwargs = mock_cls.call_args[1]
            assert "temperature" not in kwargs

    def test_streaming_flag_forwarded(self):
        with patch("app.services.llm.ChatOpenAI") as mock_cls:
            from app.services.llm import make_llm

            make_llm("gpt-4o", streaming=True)
            kwargs = mock_cls.call_args[1]
            assert kwargs["streaming"] is True

    def test_streaming_defaults_to_false(self):
        with patch("app.services.llm.ChatOpenAI") as mock_cls:
            from app.services.llm import make_llm

            make_llm("gpt-4o")
            kwargs = mock_cls.call_args[1]
            assert kwargs["streaming"] is False
