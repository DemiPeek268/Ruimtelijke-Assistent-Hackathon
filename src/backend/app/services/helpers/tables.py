"""Discovery, registration, and metadata loading for `data/`.

The new data layout is `data/<theme>/<table>/*.parquet`. Each table is
exposed in DuckDB as a view of the same name. CBS tables use `h3_index`; the
view aliases it to `h3_id` so all tables share a single spatial key.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
CBS_ID_RAW = "h3_index"
CANONICAL_ID = "h3_id"


@dataclass(frozen=True)
class TableEntry:
    theme: str
    table_name: str
    group: str
    parquet_glob: str
    is_cbs: bool


def _derive_group(table_name: str) -> str:
    return table_name.split("_", 1)[0]


def _has_data_parquets(folder: Path) -> bool:
    return any(
        p.is_file() and p.name.endswith(".parquet") and not p.name.startswith("_")
        for p in folder.iterdir()
    )


def discover_tables(root: Path = DATA_DIR) -> list[TableEntry]:
    """Walk `root/<theme>/<table>/` and return one TableEntry per table folder."""
    entries: list[TableEntry] = []
    for theme_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for table_dir in sorted(p for p in theme_dir.iterdir() if p.is_dir()):
            if not _has_data_parquets(table_dir):
                continue
            entries.append(
                TableEntry(
                    theme=theme_dir.name,
                    table_name=table_dir.name,
                    group=_derive_group(table_dir.name),
                    parquet_glob=str(table_dir / "*.parquet"),
                    is_cbs=table_dir.name.startswith("cbs_"),
                )
            )
    return entries


def load_theme_metadata(root: Path = DATA_DIR) -> dict[str, dict]:
    """Read `root/_llm_metadata_<theme>.json` files into `{theme_name: parsed}`."""
    out: dict[str, dict] = {}
    for path in sorted(root.glob("_llm_metadata_*.json")):
        theme = path.stem.removeprefix("_llm_metadata_")
        try:
            out[theme] = json.loads(path.read_text())
        except Exception:
            logger.exception("Could not load %s", path)
    return out


def register_tables(
    con: duckdb.DuckDBPyConnection, entries: list[TableEntry] | None = None
) -> list[TableEntry]:
    """Register a view per table on `con`. CBS views alias `h3_index` to `h3_id`.

    Idempotent for a given connection: uses `CREATE OR REPLACE VIEW`.
    Returns the list of entries that were registered.
    """
    if entries is None:
        entries = discover_tables()
    for entry in entries:
        # h3_id is lowercased so CBS (already lowercase) and woondeals
        # (uppercase in the raw parquet) can join across tables.
        if entry.is_cbs:
            sql = (
                f"CREATE OR REPLACE VIEW {entry.table_name} AS "
                f"SELECT * EXCLUDE ({CBS_ID_RAW}), LOWER({CBS_ID_RAW}) AS {CANONICAL_ID} "
                f"FROM read_parquet('{entry.parquet_glob}')"
            )
        else:
            sql = (
                f"CREATE OR REPLACE VIEW {entry.table_name} AS "
                f"SELECT * EXCLUDE ({CANONICAL_ID}), LOWER({CANONICAL_ID}) AS {CANONICAL_ID} "
                f"FROM read_parquet('{entry.parquet_glob}')"
            )
        con.execute(sql)
    return entries
