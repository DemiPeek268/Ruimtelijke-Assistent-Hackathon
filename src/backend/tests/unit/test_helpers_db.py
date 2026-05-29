"""Unit tests for helpers/db.py — ensures connect_delta context manager works."""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


class TestConnectDelta:
    def test_yields_connection_and_closes(self):
        from app.services.helpers.db import connect_delta

        mock_con = MagicMock()
        mock_con.execute.return_value = None  # LOAD delta; succeeds

        with patch("app.services.helpers.db.duckdb.connect", return_value=mock_con):
            with connect_delta() as con:
                assert con is mock_con

        mock_con.close.assert_called_once()

    def test_installs_delta_when_load_fails(self):
        from app.services.helpers.db import connect_delta

        mock_con = MagicMock()
        import duckdb

        call_count = {"n": 0}

        def execute_side_effect(query):
            if query == "LOAD delta;" and call_count["n"] == 0:
                call_count["n"] += 1
                raise duckdb.Error("Extension not found")
            return MagicMock()

        mock_con.execute.side_effect = execute_side_effect

        with patch("app.services.helpers.db.duckdb.connect", return_value=mock_con):
            with connect_delta() as con:
                assert con is mock_con

        calls = [str(c) for c in mock_con.execute.call_args_list]
        assert any("INSTALL delta" in c for c in calls)

    def test_connection_closed_on_exception(self):
        from app.services.helpers.db import connect_delta

        mock_con = MagicMock()

        with patch("app.services.helpers.db.duckdb.connect", return_value=mock_con):
            try:
                with connect_delta():
                    raise ValueError("test error")
            except ValueError:
                pass

        mock_con.close.assert_called_once()
