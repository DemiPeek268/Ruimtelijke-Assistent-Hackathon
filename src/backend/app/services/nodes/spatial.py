import copy
import json
import logging
import re
import urllib.parse
import urllib.request

from app.models.state import ConversationState, IntentAnalysis
from app.services.nodes.base import BaseNode
from langchain_core.runnables import RunnableConfig

_COORD_RE = re.compile(r"lat=([0-9.]+), lon=([0-9.]+)")
logger = logging.getLogger(__name__)

PDOK_FREE_URL = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free"

# WKT POINT(lon lat) — note: WKT uses (lon lat) order
_WKT_POINT_RE = re.compile(r"POINT\(([0-9.]+)\s+([0-9.]+)\)")


class SpatialNode(BaseNode):
    """Resolve named spatial origins into LATLON filters when needed."""

    def __init__(self):
        super().__init__("spatial", auto_activate=False)

    async def run(self, state: ConversationState, config: RunnableConfig) -> dict:
        intent_analysis = state["intent_analysis"]
        intent = intent_analysis.intent

        if not state.get("needs_spatial_resolution"):
            return {
                "needs_spatial_resolution": False,
                "pdok_used": False,
            }

        resolved_intent = copy.deepcopy(intent)
        resolved_locations: list[dict] = []
        pdok_used = False

        for origin_filter in resolved_intent.spatial_query.origin_filters:
            query = origin_filter.value.removeprefix("PLACE:").strip()
            pdok_used = True
            result_str = self.pdok_locatie_search(query)

            coords = self._parse_best_match(result_str)
            if coords is None:
                unresolved = IntentAnalysis(
                    is_clear=False,
                    follow_up_question=(
                        f"Ik kon de locatie '{query}' niet eenduidig vinden. "
                        "Kun je de locatie specifieker beschrijven?"
                    ),
                )
                await self.dispatch(
                    "follow_up_text", {"content": unresolved.follow_up_question}, config
                )
                return {
                    "intent_analysis": unresolved,
                    "needs_spatial_resolution": False,
                    "pdok_used": pdok_used,
                }

            lat, lon = coords
            origin_filter.value = f"LATLON:{lat:.6f},{lon:.6f}"
            resolved_locations.append({"query": query, "lat": lat, "lon": lon})

        updated_analysis = IntentAnalysis(is_clear=True, intent=resolved_intent)
        return {
            "intent_analysis": updated_analysis,
            "needs_spatial_resolution": False,
            "pdok_used": pdok_used,
        }

    @staticmethod
    def _parse_centroide(wkt: str) -> tuple[float, float] | None:
        """Parse WKT POINT(lon lat) → (lat, lon)."""
        m = _WKT_POINT_RE.match(wkt or "")
        if not m:
            return None
        lon, lat = float(m.group(1)), float(m.group(2))
        return lat, lon

    @staticmethod
    def _parse_best_match(result_text: str) -> tuple[float, float] | None:
        match = _COORD_RE.search(result_text or "")
        if not match:
            return None
        return float(match.group(1)), float(match.group(2))

    @staticmethod
    def pdok_locatie_search(query: str) -> str:
        """Search PDOK and return a formatted best-match result string for spatial resolution."""
        params = urllib.parse.urlencode(
            {"q": query, "rows": 3, "fl": "id,weergavenaam,type,centroide_ll"}
        )
        url = f"{PDOK_FREE_URL}?{params}"

        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            logger.warning("PDOK Locatieserver request failed: %s", exc)
            return f"Fout bij opzoeken van locatie '{query}': {exc}"

        docs = data.get("response", {}).get("docs", [])
        if not docs:
            return f"Geen resultaten gevonden voor '{query}'."

        lines = []
        for doc in docs:
            coords = SpatialNode._parse_centroide(doc.get("centroide_ll", ""))
            if coords is None:
                continue
            lat, lon = coords
            lines.append(
                f"- {doc.get('weergavenaam')} (type: {doc.get('type')}) "
                f"→ lat={lat:.6f}, lon={lon:.6f}"
            )

        if not lines:
            return f"Geen coördinaten gevonden voor '{query}'."

        return (
            f"Resultaten voor '{query}':\n"
            + "\n".join(lines)
            + "\n\nGebruik de coördinaten van het beste resultaat als LATLON filter in spatial_query.origin_filters: "
        )

    def fallback(self) -> dict:
        return {
            "needs_spatial_resolution": False,
            "pdok_used": False,
        }
