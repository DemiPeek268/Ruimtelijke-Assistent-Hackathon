"""Unit tests for FastAPI routers — health, dictionary."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.unit


def _make_app_with_health():
    from app.routers import health

    app = FastAPI()
    app.include_router(health.router)
    return app


def _make_app_with_dictionary(dictionary=None):
    from app.routers import dictionary as dict_router

    app = FastAPI()
    app.include_router(dict_router.router)
    if dictionary is not None:
        from app.services import dictionary_service as svc

        svc.set_local_dictionary(dictionary)
    return app


def _make_dictionary_mock():
    from app.models.dictionary import ColumnInfo, DataDictionary, TableInfo, Theme

    col = ColumnInfo(
        name="verkeer_totaal_2020",
        type="INTEGER",
        table="verkeer_tabel",
        group="Verkeer",
    )
    table = TableInfo(name="verkeer_tabel", group="Verkeer", columns=[col])
    theme = Theme(name="wonen", label="Wonen", tables=[table])
    return DataDictionary(total_rows=1000, total_columns=1, themes=[theme])


class TestHealthRouter:
    def test_healthcheck_returns_ok(self):
        app = _make_app_with_health()
        client = TestClient(app)
        response = client.get("/healthcheck")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestDictionaryRouter:
    def test_get_dictionary_returns_dictionary_data(self):
        from app.services import dictionary_service as svc

        dictionary = _make_dictionary_mock()
        app = _make_app_with_dictionary(dictionary)
        client = TestClient(app)
        try:
            response = client.get("/api/dictionary")
        finally:
            svc.set_local_dictionary(None)
        assert response.status_code == 200
        data = response.json()
        assert data["total_rows"] == 1000
        assert len(data["themes"]) == 1

    def test_get_dictionary_calls_for_user(self):
        from app.routers import dictionary as dict_router
        from app.services import dictionary_service as svc

        dictionary = _make_dictionary_mock()
        app = FastAPI()
        app.include_router(dict_router.router)
        client = TestClient(app)

        with patch.object(
            svc, "for_user", AsyncMock(return_value=dictionary)
        ) as mocked:
            response = client.get("/api/dictionary")

        assert response.status_code == 200
        mocked.assert_awaited_once_with()
