"""Candidate suggestion helpers for filter value correction.

These helpers answer "what could the user have meant?" when a filter value
does not exist in the data: they build ranked candidate lists via fuzzy
matching and format a fallback follow-up question in Dutch.
"""

from __future__ import annotations

from difflib import get_close_matches

import duckdb

from app.config import settings
from app.models.state import Filter
from app.models.validation import InvalidFilter
from app.services.helpers.filter_queries import fetch_distinct_values


def build_candidate_list(
    attempted_value: str,
    all_values: list[str],
) -> list[str]:
    """Build a candidate list to show the user when a filter value is invalid.

    Selection strategy (in order of preference):
    1. If strict fuzzy matching yields 3 or more matches, those are returned —
       enough choices to be useful without overwhelming the user.
    2. If the column has fewer distinct values than the configured threshold,
       return all of them — the full list is short enough to display directly.
    3. Otherwise fall back to a wider fuzzy search (lower cutoff) to still
       surface something relevant even when the attempted value is very different.
    """
    fuzzy_matches = get_close_matches(
        attempted_value,
        all_values,
        n=settings.FILTER_MAX_FUZZY_CANDIDATES,
        cutoff=settings.FILTER_FUZZY_CUTOFF,
    )
    if len(fuzzy_matches) >= 3:
        return fuzzy_matches
    if len(all_values) < settings.FILTER_ALL_VALUES_THRESHOLD:
        return all_values
    return get_close_matches(attempted_value, all_values, n=50, cutoff=0.2)


def build_candidates_for_filter(
    con: duckdb.DuckDBPyConnection,
    filter_obj: Filter,
    scope_filters: list[Filter],
) -> list[str]:
    """Fetch distinct values for a filter's column and return fuzzy candidates.

    Combines ``fetch_distinct_values`` and ``build_candidate_list`` into a
    single call. Used in both individual-phase and combination-phase validation.
    """
    all_values = fetch_distinct_values(con, filter_obj, scope_filters)
    return build_candidate_list(filter_obj.value, all_values)


def build_fallback_question(invalid_filters: list[InvalidFilter]) -> str:
    """Build a Dutch follow-up question from a list of invalid filters."""
    parts = []
    for inv in invalid_filters:
        scope_text = ""
        if inv.scope_filters:
            scope_desc = ", ".join(
                f'{sf.column}="{sf.value}"' for sf in inv.scope_filters
            )
            scope_text = f" (binnen {scope_desc})"

        sample = ", ".join(f'"{v}"' for v in inv.candidates[:10])
        parts.append(
            f"De waarde '{inv.attempted_value}' bestaat niet in kolom "
            f"'{inv.column}'{scope_text}. "
            f"Beschikbare waarden zijn o.a.: {sample}."
        )
    return " ".join(parts)
