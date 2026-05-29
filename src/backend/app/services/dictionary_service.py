import asyncio
import logging
from collections import defaultdict

from app.models.dictionary import (
    ColumnInfo,
    DataDictionary,
    TableInfo,
    Theme,
)
from app.services.helpers.db import connect_delta
from app.services.helpers.tables import (
    discover_tables,
    load_theme_metadata,
    register_tables,
)

logger = logging.getLogger(__name__)

_local_dictionary: DataDictionary | None = None


def set_local_dictionary(dictionary: DataDictionary | None) -> None:
    global _local_dictionary
    _local_dictionary = dictionary


async def for_user() -> DataDictionary:
    """Return the data dictionary."""
    if _local_dictionary is not None:
        return _local_dictionary
    return await generate_dictionary()


# ---------------------------------------------------------------------------
# Local path
# ---------------------------------------------------------------------------


_NUMERIC_TYPES = (
    "INTEGER",
    "BIGINT",
    "DOUBLE",
    "FLOAT",
    "DECIMAL",
    "HUGEINT",
    "SMALLINT",
    "TINYINT",
)


def _read_table_stats(
    con, table_name: str
) -> tuple[list[tuple[str, str]], dict[str, dict]]:
    """Return (column schema, per-column stats) for a registered view.

    Stats: min/max/mean for numeric columns, sample_values for the rest.
    """
    columns_info = con.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = ? ORDER BY ordinal_position",
        [table_name],
    ).fetchall()

    stats: dict[str, dict] = {}
    for col_name, col_type in columns_info:
        col_stats: dict = {"type": col_type}
        try:
            if col_type in _NUMERIC_TYPES:
                row = con.execute(
                    f'SELECT MIN("{col_name}"), MAX("{col_name}"), AVG("{col_name}") '
                    f'FROM {table_name} WHERE "{col_name}" IS NOT NULL'
                ).fetchone()
                if row and row[0] is not None:
                    min_val, max_val, avg_val = row
                    col_stats["min"] = (
                        str(round(min_val, 2))
                        if isinstance(min_val, float)
                        else str(min_val)
                    )
                    col_stats["max"] = (
                        str(round(max_val, 2))
                        if isinstance(max_val, float)
                        else str(max_val)
                    )
                    if avg_val is not None:
                        col_stats["mean"] = str(round(avg_val, 2))
            else:
                samples = con.execute(
                    f'SELECT DISTINCT "{col_name}" FROM {table_name} '
                    f'WHERE "{col_name}" IS NOT NULL LIMIT 5'
                ).fetchall()
                col_stats["sample_values"] = [str(s[0]) for s in samples]
        except Exception:
            logger.exception(
                "Error reading stats for column %s.%s", table_name, col_name
            )
        stats[col_name] = col_stats
    return columns_info, stats


def _build_column(
    col_name: str,
    col_stats: dict,
    col_meta: dict,
    table_name: str,
    group: str,
) -> ColumnInfo:
    return ColumnInfo(
        name=col_name,
        type=col_stats.get("type", col_meta.get("type", "UNKNOWN")),
        table=table_name,
        group=col_meta.get("groep", group),
        min=col_stats.get("min"),
        max=col_stats.get("max"),
        mean=col_stats.get("mean"),
        sample_values=col_stats.get("sample_values", []),
        description=col_meta.get("beschrijving", ""),
        unit=col_meta.get("eenheid"),
        categorical=bool(col_meta.get("categorisch", False)),
    )


async def generate_dictionary() -> DataDictionary:
    """Walk data/, register one DuckDB view per table, build the dictionary."""
    return await asyncio.to_thread(_generate_dictionary_sync)


def _generate_dictionary_sync() -> DataDictionary:
    entries = discover_tables()
    theme_metadata = load_theme_metadata()

    # Pre-index column metadata by (table_name, column_name) for fast lookup.
    column_meta: dict[tuple[str, str], dict] = {}
    for theme_name, theme_meta in theme_metadata.items():
        for table_meta in theme_meta.get("data", []):
            t_name = table_meta.get("naam")
            for col_name, col_meta in table_meta.get("kolommen", {}).items():
                column_meta[(t_name, col_name)] = col_meta

    tables_by_theme: dict[str, list[TableInfo]] = defaultdict(list)
    total_columns = 0

    with connect_delta() as con:
        register_tables(con, entries)
        for entry in entries:
            _columns_info, stats = _read_table_stats(con, entry.table_name)
            col_infos: list[ColumnInfo] = []
            for col_name, col_stats in stats.items():
                col_meta = column_meta.get((entry.table_name, col_name), {})
                col_infos.append(
                    _build_column(
                        col_name=col_name,
                        col_stats=col_stats,
                        col_meta=col_meta,
                        table_name=entry.table_name,
                        group=entry.group,
                    )
                )
            tables_by_theme[entry.theme].append(
                TableInfo(name=entry.table_name, group=entry.group, columns=col_infos)
            )
            total_columns += len(col_infos)

    themes: list[Theme] = []
    for theme_name in sorted(tables_by_theme.keys()):
        meta = theme_metadata.get(theme_name, {})
        themes.append(
            Theme(
                name=theme_name,
                label=meta.get("label", theme_name.title()),
                example_questions=meta.get("voorbeeldvragen", []),
                tables=tables_by_theme[theme_name],
            )
        )

    logger.info(
        "Dictionary built: %d themes, %d tables, %d columns",
        len(themes),
        sum(len(t.tables) for t in themes),
        total_columns,
    )
    return DataDictionary(total_rows=0, total_columns=total_columns, themes=themes)
