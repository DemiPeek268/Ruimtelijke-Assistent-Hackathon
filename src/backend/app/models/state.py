from typing import Any, Literal, TypedDict

from pydantic import BaseModel


class Filter(BaseModel):
    """Een enkel filtercriterium voor de SQL query."""

    table: str | None = None
    column: str
    operator: str
    value: str


class Aggregation(BaseModel):
    """Een enkele aggregatiefunctie voor de SQL query."""

    column: str
    function: str
    level: list[str] | None = None


class SpatialQuery(BaseModel):
    """Parameters voor een ruimtelijke proximity query (H3 buffer)."""

    origin_filters: list[Filter]
    k_rings: int


class YearComparison(BaseModel):
    """Vergelijking van één kolom tussen twee jaren."""

    column: str
    year_from: int
    year_to: int


class Intent(BaseModel):
    """Gestructureerde beschrijving van een gebruikersintentie."""

    description: str
    relevant_columns: list[str]
    filters: list[Filter] = []
    aggregation: Aggregation | None = None
    limit: int | None = None
    spatial_query: SpatialQuery | None = None
    year_comparison: YearComparison | None = None


class IntentAnalysis(BaseModel):
    """Output van de intent-analyse stap."""

    is_clear: bool
    intent: Intent | None = None
    follow_up_question: str | None = None
    thinking_summary: str = ""


class SqlGenerationOutput(BaseModel):
    """Gestructureerde output van de SQL-generatie node."""

    sql_query: str
    thinking_summary: str = ""


class ColorRole(BaseModel):
    """De visuele rol 'kleur' in een MapPlan."""

    column: str
    label: str
    kind: Literal["numeric", "categorical"]


class HeightRole(BaseModel):
    """De visuele rol 'hoogte' in een MapPlan. Alleen numeriek."""

    column: str
    label: str


class IconRole(BaseModel):
    """Een aanwezigheidskolom die als gekleurde cirkel wordt getoond."""

    column: str
    label: str


class MapPlan(BaseModel):
    """Rollen-gebaseerde kaartconfiguratie voor de frontend."""

    h3_column: str
    color: ColorRole | None = None
    height: HeightRole | None = None
    icons: list[IconRole] = []
    thinking_summary: str = ""


class QueryResult(BaseModel):
    """Output van de execute_query node."""

    sample: list[dict] | None = None
    count: int | None = None
    summary: dict | None = None
    # `rows` is intentionally not stored here — all rows are streamed directly
    # to the frontend via the `map_data` SSE event and do not belong in graph state.
    error: str | None = None


class ConversationState(TypedDict):
    """State die door de LangGraph workflow stroomt."""

    messages: list[dict]
    dictionary: Any
    model: str

    # Output van intent node
    intent_analysis: IntentAnalysis | None
    needs_spatial_resolution: bool
    pdok_used: bool

    # Output van SQL generation node
    sql_query: str | None

    # Output van execute_query node
    query_result: QueryResult | None

    # Output van plan_visualization node
    map_plan: MapPlan | None

    # Output van describe_results node
    explanation: str | None
