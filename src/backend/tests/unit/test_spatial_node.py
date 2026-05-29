import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models.dictionary import ColumnInfo, DataDictionary, TableInfo, Theme
from app.models.state import Filter, Intent, IntentAnalysis, SpatialQuery
from app.services.nodes.spatial import SpatialNode

pytestmark = pytest.mark.unit

_PDOK_SUCCESS = (
    "Resultaten voor 'Delft':\n"
    "- Delft (type: gemeente) → lat=52.011580, lon=4.357068\n"
    "\nGebruik de coördinaten van het beste resultaat als LATLON filter"
)
_PDOK_NO_RESULT = "Geen resultaten gevonden voor 'Luilekkerland'."


def _make_state(origin_value: str = "PLACE:Delft") -> dict:
    spatial_query = SpatialQuery(
        origin_filters=[
            Filter(column="h3_spatial_filter", operator="=", value=origin_value)
        ],
        k_rings=3,
    )
    intent = Intent(
        description="Toon data rond Delft",
        relevant_columns=["h3_id"],
        filters=[],
        spatial_query=spatial_query,
    )
    col = ColumnInfo(name="h3_id", type="VARCHAR", table="test_tabel", group="Test")
    table = TableInfo(name="test_tabel", group="Test", columns=[col])
    theme = Theme(name="test", label="Test", tables=[table])
    return {
        "intent_analysis": IntentAnalysis(is_clear=True, intent=intent),
        "needs_spatial_resolution": True,
        "dictionary": DataDictionary(total_rows=100, total_columns=1, themes=[theme]),
        "model": "gpt-4o",
    }


class TestSpatialNodeRun:
    async def test_run_sets_pdok_used_true_on_success(self):
        """SpatialNode resolves a PLACE: origin filter and writes pdok_used=True."""
        with (
            patch.object(
                SpatialNode, "pdok_locatie_search", return_value=_PDOK_SUCCESS
            ),
            patch(
                "app.services.nodes.base.adispatch_custom_event",
                new_callable=AsyncMock,
            ),
        ):
            node = SpatialNode()
            state_update = await node.run(_make_state(), config={})

        assert state_update["pdok_used"] is True

    async def test_run_resolves_place_filter_to_latlon(self):
        """SpatialNode replaces the PLACE: origin filter value with a LATLON: string."""
        with (
            patch.object(
                SpatialNode, "pdok_locatie_search", return_value=_PDOK_SUCCESS
            ),
            patch(
                "app.services.nodes.base.adispatch_custom_event",
                new_callable=AsyncMock,
            ),
        ):
            node = SpatialNode()
            state_update = await node.run(_make_state(), config={})

        updated_intent = state_update["intent_analysis"].intent
        origin_value = updated_intent.spatial_query.origin_filters[0].value
        assert origin_value.startswith("LATLON:"), (
            f"Expected LATLON: prefix, got: {origin_value!r}"
        )

    async def test_run_sets_needs_spatial_resolution_false_on_success(self):
        """After successful resolution, needs_spatial_resolution is cleared."""
        with (
            patch.object(
                SpatialNode, "pdok_locatie_search", return_value=_PDOK_SUCCESS
            ),
            patch(
                "app.services.nodes.base.adispatch_custom_event",
                new_callable=AsyncMock,
            ),
        ):
            node = SpatialNode()
            state_update = await node.run(_make_state(), config={})

        assert state_update["needs_spatial_resolution"] is False

    async def test_run_returns_follow_up_when_pdok_finds_no_coords(self):
        """When PDOK returns no coordinates, SpatialNode writes is_clear=False with
        a follow-up question asking for a more specific location."""
        with (
            patch.object(
                SpatialNode, "pdok_locatie_search", return_value=_PDOK_NO_RESULT
            ),
            patch(
                "app.services.nodes.base.adispatch_custom_event",
                new_callable=AsyncMock,
            ),
        ):
            node = SpatialNode()
            state_update = await node.run(_make_state(), config={})

        intent_analysis = state_update["intent_analysis"]
        assert intent_analysis.is_clear is False
        assert intent_analysis.follow_up_question

    async def test_run_skips_when_needs_spatial_resolution_false(self):
        """SpatialNode exits early when needs_spatial_resolution is False in state."""
        state = _make_state()
        state["needs_spatial_resolution"] = False

        with patch(
            "app.services.nodes.base.adispatch_custom_event", new_callable=AsyncMock
        ):
            node = SpatialNode()
            state_update = await node.run(state, config={})

        assert state_update["pdok_used"] is False
        assert state_update["needs_spatial_resolution"] is False


class TestSpatialNodeFallback:
    def test_fallback_clears_spatial_resolution_flag(self):
        """Fallback returns a safe state that clears the spatial resolution flag."""
        node = SpatialNode()
        result = node.fallback()

        assert result["needs_spatial_resolution"] is False
        assert result["pdok_used"] is False


class TestParseCentroide:
    def test_valid_wkt_returns_lat_lon(self):
        result = SpatialNode._parse_centroide("POINT(4.35889 52.01234)")
        assert result is not None
        lat, lon = result
        assert abs(lat - 52.01234) < 1e-5
        assert abs(lon - 4.35889) < 1e-5

    def test_note_order_is_lon_lat_in_wkt(self):
        # WKT is POINT(lon lat) but function returns (lat, lon)
        result = SpatialNode._parse_centroide("POINT(4.0 52.0)")
        lat, lon = result
        assert lat == 52.0
        assert lon == 4.0

    def test_invalid_wkt_returns_none(self):
        assert SpatialNode._parse_centroide("INVALID") is None
        assert SpatialNode._parse_centroide("") is None
        assert SpatialNode._parse_centroide(None) is None

    def test_missing_space_returns_none(self):
        assert SpatialNode._parse_centroide("POINT(4.3589)") is None

    def test_decimal_precision_preserved(self):
        result = SpatialNode._parse_centroide("POINT(4.358896 52.012345)")
        assert result is not None
        lat, lon = result
        assert abs(lat - 52.012345) < 1e-6
        assert abs(lon - 4.358896) < 1e-6


class TestPdokLocatieSearch:
    def _make_response(self, docs: list) -> bytes:
        data = {"response": {"docs": docs}}
        return json.dumps(data).encode()

    def test_returns_results_with_coordinates(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = self._make_response(
            [
                {
                    "weergavenaam": "Delft",
                    "type": "gemeente",
                    "centroide_ll": "POINT(4.35889 52.01124)",
                }
            ]
        )
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(
            "app.services.nodes.spatial.urllib.request.urlopen",
            return_value=mock_resp,
        ):
            result = SpatialNode.pdok_locatie_search("Delft")

        assert "Delft" in result
        assert "52." in result
        assert "4." in result

    def test_empty_docs_returns_no_results_message(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = self._make_response([])
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(
            "app.services.nodes.spatial.urllib.request.urlopen",
            return_value=mock_resp,
        ):
            result = SpatialNode.pdok_locatie_search("XYZ_NONEXISTENT")

        assert "Geen resultaten" in result

    def test_request_error_returns_error_message(self):
        with patch(
            "app.services.nodes.spatial.urllib.request.urlopen",
            side_effect=Exception("connection refused"),
        ):
            result = SpatialNode.pdok_locatie_search("Delft")

        assert "Fout" in result
        assert "Delft" in result

    def test_docs_without_valid_centroide_shows_no_coords_message(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = self._make_response(
            [{"weergavenaam": "Test", "type": "gemeente", "centroide_ll": "INVALID"}]
        )
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(
            "app.services.nodes.spatial.urllib.request.urlopen",
            return_value=mock_resp,
        ):
            result = SpatialNode.pdok_locatie_search("Test")

        assert "Geen coördinaten" in result

    def test_multiple_results_all_listed(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = self._make_response(
            [
                {
                    "weergavenaam": "Delft Station",
                    "type": "spoorwegstation",
                    "centroide_ll": "POINT(4.36 52.01)",
                },
                {
                    "weergavenaam": "Delft Centrum",
                    "type": "wijk",
                    "centroide_ll": "POINT(4.357 52.012)",
                },
            ]
        )
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(
            "app.services.nodes.spatial.urllib.request.urlopen",
            return_value=mock_resp,
        ):
            result = SpatialNode.pdok_locatie_search("Delft")

        assert "Delft Station" in result
        assert "Delft Centrum" in result
