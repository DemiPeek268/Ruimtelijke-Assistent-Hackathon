"""Reusable filter-validation helpers.

These helpers implement validation semantics used by the validation node:
- OR within the same column
- AND across different columns
- hierarchical scoping for location filters
"""

from __future__ import annotations

import duckdb

from app.models.state import Filter
from app.models.validation import InvalidFilter
from app.services.helpers.filter_candidates import build_candidates_for_filter
from app.services.helpers.filter_queries import (
    check_combination_has_results,
    check_value_exists,
)
from app.services.helpers.location_hierarchy import (
    get_parent_columns,
    is_location_column,
    sort_filters_by_hierarchy,
)


def _is_not_null_filter(f: Filter) -> bool:
    return "IS NOT NULL" in f.operator.upper() or "IS NOT NULL" in f.value.upper()


def collect_invalid_filters(
    con: duckdb.DuckDBPyConnection,
    filters: list[Filter],
) -> list[InvalidFilter]:
    """Validate filters in hierarchy order with scoped and grouped semantics.

    Runs two phases:
    1. Individual value check — each filter is checked in isolation (scoped to
       already-validated parent filters). Filters that pass are added to
       ``validated`` so that child filters can be scoped against them.
       Parent filters must validate before children so scoping is accurate
       (e.g. a wijk is validated within its gemeente).
    2. Combination check — only when all individual values pass. It is possible
       for two individually-valid values to produce zero results together (e.g. a
       valid wijk that does not belong to the given gemeente). In that case,
       ``_find_conflicting_filter`` pinpoints which filter breaks the combination.

    Returns a list of InvalidFilter objects describing each invalid filter,
    including the attempted value and fuzzy-matched candidate replacements.
    An empty list means all filters are valid and mutually compatible.
    """
    validatable = [f for f in filters if not _is_not_null_filter(f)]
    sorted_filters = sort_filters_by_hierarchy(validatable)
    validated: dict[str, list[Filter]] = {}

    invalid = _validate_individual_phase(con, sorted_filters, validated)
    if invalid:
        return invalid

    return _validate_combination_phase(con, sorted_filters)


def _validate_individual_phase(
    con: duckdb.DuckDBPyConnection,
    sorted_filters: list[Filter],
    validated: dict[str, list[Filter]],
) -> list[InvalidFilter]:
    """Phase 1: check each filter value individually in hierarchy order.

    Validated filters are added to ``validated`` so child filters can be
    scoped against them during their own checks.
    """
    invalid: list[InvalidFilter] = []
    for filter_obj in sorted_filters:
        scope = _build_scope(filter_obj, validated)
        if check_value_exists(con, filter_obj, scope):
            validated.setdefault(filter_obj.column, []).append(filter_obj)
            continue

        candidates = build_candidates_for_filter(con, filter_obj, scope)
        invalid.append(
            InvalidFilter(
                column=filter_obj.column,
                operator=filter_obj.operator,
                attempted_value=filter_obj.value,
                candidates=candidates,
                scope_filters=scope,
            )
        )

    return invalid


def _validate_combination_phase(
    con: duckdb.DuckDBPyConnection,
    sorted_filters: list[Filter],
) -> list[InvalidFilter]:
    """Phase 2: verify that all individually-valid filters are mutually compatible.

    Two values can each be individually valid yet produce zero results together
    (e.g. a valid wijk that does not belong to the given gemeente).
    Returns the conflicting filter, or an empty list if all combinations pass.
    """
    if len(sorted_filters) <= 1:
        return []
    if check_combination_has_results(con, sorted_filters):
        return []
    return _find_conflicting_filter(con, sorted_filters)


def _build_scope(
    filter_obj: Filter,
    validated: dict[str, list[Filter]],
) -> list[Filter]:
    """Determine which already-validated filters should scope this check.

    Location columns are scoped to their direct parents only (e.g. a wijk
    is scoped to its gemeente). Non-location columns are scoped to all
    validated location filters.
    """
    if is_location_column(filter_obj.column):
        parent_cols = get_parent_columns(filter_obj.column)
        scoped_parents: list[Filter] = []
        for col in parent_cols:
            scoped_parents.extend(validated.get(col, []))
        return scoped_parents

    scoped_locations: list[Filter] = []
    for col, values in validated.items():
        if is_location_column(col):
            scoped_locations.extend(values)
    return scoped_locations


def _find_conflicting_filter(
    con: duckdb.DuckDBPyConnection,
    sorted_filters: list[Filter],
) -> list[InvalidFilter]:
    """Find the first filter that breaks grouped combination satisfiability.

    Accumulates filters one by one until the combination yields no results,
    then reports that filter as the conflicting one.
    """
    accumulated: list[Filter] = []
    for filter_obj in sorted_filters:
        accumulated.append(filter_obj)
        if not check_combination_has_results(con, accumulated):
            scope = accumulated[:-1]
            candidates = build_candidates_for_filter(con, filter_obj, scope)
            return [
                InvalidFilter(
                    column=filter_obj.column,
                    operator=filter_obj.operator,
                    attempted_value=filter_obj.value,
                    candidates=candidates,
                    scope_filters=scope,
                )
            ]
    return []
