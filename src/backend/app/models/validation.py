from pydantic import BaseModel

from app.models.state import Filter


class InvalidFilter(BaseModel):
    """Een ongeldig filtercriterium inclusief kandidaten voor correctie."""

    column: str
    operator: str
    attempted_value: str
    candidates: list[str]
    scope_filters: list[Filter] = []
    sibling_match: str | None = None
    source: str = "filter"  # "filter" or "spatial_origin"
