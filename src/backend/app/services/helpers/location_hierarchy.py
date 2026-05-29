"""Location hierarchy definitions and ordering for filter validation.

Defines the parent-child relationships between location columns
(gemeente → wijk → buurt) and provides sorting/scoping utilities.

Dataset switching guide:
  data_wonen_demo_delta  → uses gemeente_Gemeentenaam / gemeente_Code (active below)
  volledige_tijdreeks_delta → uses gemeentenaam / wijknaam / buurtnaam (commented out)
"""

from __future__ import annotations

from app.models.state import Filter

# Each location column maps to its parent columns (in order).
LOCATION_HIERARCHY: dict[str, list[str]] = {
    "gemeente_Gemeentenaam": [],
    "gemeente_Code": [],
}

# Validation priority: lower number = validate first.
_HIERARCHY_ORDER: dict[str, int] = {
    "gemeente_Gemeentenaam": 0,
    "gemeente_Code": 0,
}

_NON_LOCATION_ORDER = 3  # Non-location categoricals validate last.


def is_location_column(column: str) -> bool:
    """Return True if *column* is part of the location hierarchy."""
    return column in LOCATION_HIERARCHY


def get_parent_columns(column: str) -> list[str]:
    """Return the parent columns for a location column, or [] if not in hierarchy."""
    return LOCATION_HIERARCHY.get(column, [])


def sort_filters_by_hierarchy(filters: list[Filter]) -> list[Filter]:
    """Sort filters so parents validate before children.

    Order: gemeente(code) → wijk → buurt → non-location categoricals.
    """
    return sorted(
        filters,
        key=lambda f: _HIERARCHY_ORDER.get(f.column, _NON_LOCATION_ORDER),
    )
