from __future__ import annotations

import json
from pathlib import Path

from app.models.dictionary import DataDictionary
from app.models.state import Intent


def load_prompt(filename: str) -> str:
    path = Path(__file__).parent.parent / "prompts" / filename
    return path.read_text(encoding="utf-8")


def build_columns_text(
    dictionary: DataDictionary,
    mode: str = "intent",
    only_columns: list[str] | None = None,
) -> str:
    """Build compact column listing grouped by theme, including metadata based on mode.

    If only_columns is provided, only include those columns (filtering by name).
    mode: "intent" (compact, for understanding user request) or "sql" (detailed, for query generation).
    """
    theme_sections = []
    for theme in dictionary.themes:
        cols = []
        for c in theme.columns:
            if only_columns is not None and c.name not in only_columns:
                continue

            # Common flags
            norm_flag = "[NORM]" if c.normalized else ""

            if mode == "intent":
                # Intent mode: Name, Description, [NORM], Available Years
                # Format: - {name} {norm_flag}: {description} {years}
                line = f"- {c.name}"
                if norm_flag:
                    line += f" {norm_flag}"

                desc = c.description or ""
                if desc:
                    line += f": {desc}"

                if c.available_years:
                    years_str = ", ".join(str(y) for y in c.available_years)
                    line += f" (jaren: {years_str})"

                cols.append(line)

            elif mode == "sql":
                # SQL mode: Name, Type, Description, [NORM], Range
                # Format: - {name} ({type}{norm_flag}): {description}. Range: {min}-{max}.
                type_info = c.type
                if norm_flag:
                    type_info += f", {norm_flag}"

                line = f"- {c.name} ({type_info})"

                if c.unit != "index":
                    line += f" {c.unit}"

                desc = c.description or ""
                if desc:
                    line += f": {desc}"

                if c.min is not None and c.max is not None:
                    line += f". Range: {c.min}-{c.max}"

                cols.append(line)

        if cols:
            theme_sections.append(f"### {theme.label}\n" + "\n".join(cols))

    return "\n\n".join(theme_sections)


def build_all_column_names(dictionary: DataDictionary) -> str:
    """Build a compact list of all column names grouped by theme (names only)."""
    sections = []
    for theme in dictionary.themes:
        names = ", ".join(c.name for c in theme.columns)
        sections.append(f"**{theme.label}**: {names}")
    return "\n".join(sections)


def format_results_section(
    sample: list[dict] | None,
    count: int | None,
    summary: dict | None,
    error: str | None,
) -> str:
    """Build the results section for the description prompt."""
    if error:
        return f"## Query Execution Error\n{error}"

    if count is None or count == 0:
        return "## Query Results\nThe query returned no results (0 rows)."

    parts = [f"## Query Results\nTotal rows: {count:,}"]

    if summary:
        parts.append("\n### Summary Statistics per Column")
        for col_name, stats in summary.items():
            if "top_values" in stats:
                top = ", ".join(
                    f'"{v}" ({c:,}×)' for v, c in stats["top_values"].items()
                )
                parts.append(
                    f"- **{col_name}**: {stats['non_null_count']:,} non-null values, "
                    f"{stats['distinct_count']:,} distinct values. "
                    f"Most common: {top}"
                )
            else:
                stat_parts = [f"  {k}: {v}" for k, v in stats.items()]
                parts.append(f"- **{col_name}**\n" + "\n".join(stat_parts))

    if sample:
        # Note: 100 matches ExecuteQueryNode.SAMPLE_THRESHOLD
        label = (
            "All rows" if count <= 100 else f"Sample ({len(sample)} of {count:,} rows)"
        )
        parts.append(f"\n### {label}")
        parts.append("```json")
        parts.append(json.dumps(sample, ensure_ascii=False, default=str))
        parts.append("```")

    return "\n".join(parts)


def format_intent_section(intent: Intent, for_sql: bool = False) -> str:
    """Format the intent section for prompts (SQL generation, correction, etc.)."""
    relevant_columns = ", ".join(intent.relevant_columns)

    def _fmt_value(v: str) -> str:
        return v.replace("'", "''") if for_sql else v

    filters_text = ", ".join(
        f'{f.column} {f.operator} "{_fmt_value(f.value)}"' for f in intent.filters
    )

    section = f"""
    - Description: {intent.description}
    - Relevant columns: {relevant_columns}
    - Filters: {filters_text}"""

    if intent.aggregation:
        # Print aggregation fields explicitly to avoid redundancy
        section += f"\n    - Aggregation: {intent.aggregation.function}({intent.aggregation.column})"
        if intent.aggregation.level:
            level_text = ", ".join(intent.aggregation.level)
            section += f"\n    - Aggregation level (GROUP BY): {level_text}"

    if intent.limit:
        section += f"\n    - Limit (top-N): {intent.limit}"

    if intent.spatial_query:
        origin_text = ", ".join(
            f'{f.column} {f.operator} "{_fmt_value(f.value)}"'
            for f in intent.spatial_query.origin_filters
        )
        section += (
            f"\n    - Spatial proximity query (spatial_query):"
            f"\n      - Origin area filters (origin_filters): {origin_text}"
            f"\n      - Number of H3 rings (k_rings): {intent.spatial_query.k_rings}"
        )

    if intent.year_comparison:
        yc = intent.year_comparison
        section += f"\n    - Year comparison: {yc.column} — from {yc.year_from} to {yc.year_to}"

    return section
