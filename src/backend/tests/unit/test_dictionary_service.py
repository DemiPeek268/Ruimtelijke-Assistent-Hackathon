"""Unit tests for dictionary_service.py — Delta table reads mocked."""

import base64
import json
import time
from unittest.mock import AsyncMock, patch

import pytest
from app.models.dictionary import ColumnInfo, DataDictionary, Theme
from app.services.dictionary_service import generate_dictionary

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skip(
        reason="Tests target removed _load_metadata / normalized-column / "
        "Delta-table code path. Rewrite for the data/ multi-table loader."
    ),
]


def _make_jwt(payload: dict) -> str:
    """Build an unsigned JWT-shaped token (header.payload.signature)."""
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    )
    return f"{header}.{payload_b64}.signature"


def _trivial_dictionary(label: str = "L") -> DataDictionary:
    col = ColumnInfo(name="c", type="INTEGER")
    return DataDictionary(
        total_rows=0,
        total_columns=1,
        themes=[Theme(name="t", label=label, columns=[col])],
    )


def _make_metadata() -> dict:
    return {
        "groepen": [
            {
                "naam": "wonen",
                "label": "Wonen",
                "voorbeeldvragen": ["Hoeveel woningen?"],
            }
        ],
        "kolommen": {
            "verkeer_totaal_2020": {
                "groep": "wonen",
                "beschrijving": "Totaal verkeer 2020",
                "eenheid": "voertuigen",
                "genormaliseerd": True,
                "categorisch": False,
                "bron": "RWS",
            },
            "gemeente_Gemeentenaam": {
                "groep": "wonen",
                "beschrijving": "Naam van de gemeente",
                "eenheid": None,
                "genormaliseerd": False,
                "categorisch": True,
                "bron": "CBS",
            },
        },
    }


def _make_delta_stats():
    return (
        1000,  # total_rows
        {
            "verkeer_totaal_2020": {
                "type": "INTEGER",
                "min": "0",
                "max": "255",
                "mean": "127.5",
            },
            "gemeente_Gemeentenaam": {
                "type": "VARCHAR",
                "sample_values": ["Delft", "Leiden"],
            },
        },
    )


class TestGenerateDictionary:
    async def test_generates_dictionary_from_metadata_and_stats(self):
        metadata = _make_metadata()
        total_rows, delta_stats = _make_delta_stats()

        with (
            patch(
                "app.services.dictionary_service._load_metadata", return_value=metadata
            ),
            patch(
                "app.services.dictionary_service._read_delta_schema_and_stats",
                return_value=(total_rows, delta_stats),
            ),
        ):
            result = await generate_dictionary()

        assert result.total_rows == 1000
        assert len(result.themes) == 1
        assert result.themes[0].name == "wonen"
        assert result.themes[0].label == "Wonen"

    async def test_themes_contain_correct_columns(self):
        metadata = _make_metadata()
        total_rows, delta_stats = _make_delta_stats()

        with (
            patch(
                "app.services.dictionary_service._load_metadata", return_value=metadata
            ),
            patch(
                "app.services.dictionary_service._read_delta_schema_and_stats",
                return_value=(total_rows, delta_stats),
            ),
        ):
            result = await generate_dictionary()

        col_names = [c.name for c in result.themes[0].columns]
        assert "verkeer_totaal_2020" in col_names
        assert "gemeente_Gemeentenaam" in col_names

    async def test_column_attributes_from_metadata(self):
        metadata = _make_metadata()
        total_rows, delta_stats = _make_delta_stats()

        with (
            patch(
                "app.services.dictionary_service._load_metadata", return_value=metadata
            ),
            patch(
                "app.services.dictionary_service._read_delta_schema_and_stats",
                return_value=(total_rows, delta_stats),
            ),
        ):
            result = await generate_dictionary()

        wonen_theme = result.themes[0]
        woningen_col = next(
            c for c in wonen_theme.columns if c.name == "verkeer_totaal_2020"
        )
        assert woningen_col.normalized is True
        assert woningen_col.categorical is False
        assert woningen_col.description == "Totaal verkeer 2020"
        assert woningen_col.source == "RWS"

    async def test_unknown_group_gets_default_label(self):
        metadata = {
            "groepen": [],  # no groups defined
            "kolommen": {
                "some_col": {
                    "groep": "unknown_group",
                    "beschrijving": "Test column",
                    "eenheid": None,
                    "genormaliseerd": False,
                    "categorisch": False,
                    "bron": None,
                }
            },
        }

        with (
            patch(
                "app.services.dictionary_service._load_metadata", return_value=metadata
            ),
            patch(
                "app.services.dictionary_service._read_delta_schema_and_stats",
                return_value=(100, {"some_col": {"type": "INTEGER"}}),
            ),
        ):
            result = await generate_dictionary()

        # Group with no definition should use the name formatted as a title
        unknown_theme = next(t for t in result.themes if t.name == "unknown_group")
        assert unknown_theme.label == "Unknown Group"


@pytest.fixture(autouse=True)
def _reset_dictionary_module_state():
    """Each test gets a fresh local-dictionary singleton and an empty cache."""
    from app.services import dictionary_service as svc

    svc.set_local_dictionary(None)
    svc._user_cache.clear()
    yield
    svc.set_local_dictionary(None)
    svc._user_cache.clear()


class TestDecodeOid:
    def test_extracts_oid_from_valid_jwt(self):
        from app.services.dictionary_service import _decode_oid

        token = _make_jwt({"oid": "user-123", "upn": "x@y"})
        assert _decode_oid(token) == "user-123"

    def test_raises_when_oid_missing(self):
        from app.services.dictionary_service import _decode_oid

        token = _make_jwt({"upn": "x@y"})
        with pytest.raises(ValueError, match="oid"):
            _decode_oid(token)

    def test_raises_on_malformed_token(self):
        from app.services.dictionary_service import _decode_oid

        with pytest.raises(ValueError):
            _decode_oid("not-a-jwt")


class TestForUserLocalPath:
    async def test_returns_set_local_dictionary(self):
        from app.services import dictionary_service as svc

        local = _trivial_dictionary(label="local")
        svc.set_local_dictionary(local)

        result = await svc.for_user(user_token=None)

        assert result is local

    async def test_local_path_ignores_user_token(self):
        from app.services import dictionary_service as svc

        local = _trivial_dictionary(label="local")
        svc.set_local_dictionary(local)

        result = await svc.for_user(user_token=_make_jwt({"oid": "x"}))

        assert result is local

    async def test_local_path_lazily_builds_if_no_singleton(self):
        from app.services import dictionary_service as svc

        built = _trivial_dictionary(label="generated")
        with patch(
            "app.services.dictionary_service.generate_dictionary",
            AsyncMock(return_value=built),
        ):
            result = await svc.for_user(user_token=None)

        assert result is built


class TestUserCache:
    def test_ttl_expires_entry(self):
        from app.services.dictionary_service import TTLCache

        cache: TTLCache = TTLCache(maxsize=10, ttl=0.05)
        cache["k"] = "v"
        assert "k" in cache
        time.sleep(0.1)
        assert "k" not in cache

    def test_lru_evicts_when_maxsize_exceeded(self):
        from app.services.dictionary_service import TTLCache

        cache: TTLCache = TTLCache(maxsize=2, ttl=60)
        cache["a"] = 1
        cache["b"] = 2
        cache["c"] = 3
        assert "a" not in cache
        assert "b" in cache
        assert "c" in cache
