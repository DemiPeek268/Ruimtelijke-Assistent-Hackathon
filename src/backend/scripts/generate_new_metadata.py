"""Generate per-theme metadata files for src/backend/
data/.

Walks `data/<theme>/<table>/*.parquet`, builds one metadata file per theme at
`data/_llm_metadata_<theme>.json`. For each column we first try to reuse an
existing description/eenheid/categorisch from the old `data/_llm_metadata*.json`
files; remaining columns get LLM-filled in batches. We also LLM-generate a
starter `voorbeeldvragen` list per theme.

Idempotent: re-running keeps columns already present in the output untouched.

Run with:  python -m backend.scripts.generate_new_metadata
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

import duckdb
from langchain_core.messages import HumanMessage, SystemMessage

# Make `app.*` importable when run as a script.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.config import settings  # noqa: E402
from app.services.llm import make_llm  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("generate_new_metadata")

data_DIR = _BACKEND_DIR / "data"
OLD_DATA_DIR = _BACKEND_DIR / "data"
CBS_ID_RENAME = ("h3_index", "h3_id")  # (from, to) — CBS tables only.


def _is_data_parquet(name: str) -> bool:
    return name.endswith(".parquet") and not name.startswith("_")


def _list_data_parquets(table_dir: Path) -> list[Path]:
    return sorted(p for p in table_dir.iterdir() if _is_data_parquet(p.name))


def discover_themes() -> list[tuple[str, list[Path]]]:
    """Return [(theme_name, [table_dir, ...])]."""
    themes: list[tuple[str, list[Path]]] = []
    for theme_dir in sorted(p for p in data_DIR.iterdir() if p.is_dir()):
        tables = [
            t
            for t in sorted(theme_dir.iterdir())
            if t.is_dir() and _list_data_parquets(t)
        ]
        if tables:
            themes.append((theme_dir.name, tables))
    return themes


def derive_group(table_name: str) -> str:
    return table_name.split("_", 1)[0]


def read_parquet_columns(
    con: duckdb.DuckDBPyConnection, parquet_glob: str
) -> list[tuple[str, str]]:
    rows = con.execute(
        f"DESCRIBE SELECT * FROM read_parquet('{parquet_glob}')"
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def sample_distinct_values(
    con: duckdb.DuckDBPyConnection, parquet_glob: str, column: str, k: int = 10
) -> list[str]:
    try:
        rows = con.execute(
            f"SELECT DISTINCT \"{column}\" FROM read_parquet('{parquet_glob}') "
            f'WHERE "{column}" IS NOT NULL LIMIT {k}'
        ).fetchall()
    except Exception:
        return []
    return [str(r[0]) for r in rows]


def load_old_metadata_index() -> dict[str, dict]:
    """Build `{column_name: {beschrijving, eenheid, categorisch}}` from old metadata files."""
    index: dict[str, dict] = {}
    for path in sorted(OLD_DATA_DIR.glob("_llm_metadata*.json")):
        try:
            data = json.loads(path.read_text())
        except Exception:
            logger.warning("Could not parse %s", path)
            continue
        for col_name, meta in data.get("kolommen", {}).items():
            if col_name in index:
                continue  # first match wins, files iterated in stable order
            entry: dict = {}
            if "beschrijving" in meta:
                entry["beschrijving"] = meta["beschrijving"]
            if "eenheid" in meta:
                entry["eenheid"] = meta["eenheid"]
            if "categorisch" in meta:
                entry["categorisch"] = bool(meta["categorisch"])
            if entry:
                index[col_name] = entry
    logger.info("Loaded %d reusable column entries from old metadata", len(index))
    return index


_JSON_BLOCK = re.compile(r"\{[\s\S]*\}|\[[\s\S]*\]")


def _strip_to_json(text: str) -> str:
    match = _JSON_BLOCK.search(text)
    return match.group(0) if match else text


def llm_fill_columns(
    table_name: str,
    columns: list[tuple[str, str, list[str]]],
) -> dict[str, dict]:
    """Ask the LLM to fill {beschrijving, eenheid, categorisch} for each column.

    `columns` items are `(name, parquet_type, sample_values)`.
    Returns `{column_name: {beschrijving, eenheid?, categorisch}}`.
    """
    if not columns:
        return {}
    llm = make_llm(settings.OPENAI_MODEL)
    col_payload = [{"naam": c, "type": t, "voorbeeldwaarden": s} for c, t, s in columns]
    system = (
        "Je bent een data-analist die Nederlandstalige metadata schrijft voor "
        "ruimtelijke datasets. Antwoord ALTIJD met een geldig JSON-object."
    )
    human = (
        f"Tabel: {table_name}\n"
        f"Kolommen (met type en voorbeeldwaarden):\n"
        f"{json.dumps(col_payload, ensure_ascii=False, indent=2)}\n\n"
        "Geef voor elke kolom een korte zakelijke 'beschrijving' (max 1 zin) in het "
        "Nederlands, een 'eenheid' (of null), en 'categorisch' (true/false). "
        "Categorisch = de kolom bevat een beperkte set discrete labels.\n\n"
        "Antwoordformaat: een JSON-object {kolomnaam: {beschrijving, eenheid, categorisch}}. "
        "Niets anders."
    )
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
    raw = resp.content if isinstance(resp.content, str) else str(resp.content)
    try:
        parsed = json.loads(_strip_to_json(raw))
    except Exception:
        logger.exception(
            "LLM returned non-JSON for table %s; raw=%r", table_name, raw[:500]
        )
        return {}
    out: dict[str, dict] = {}
    for col_name, payload in parsed.items():
        entry = {"beschrijving": str(payload.get("beschrijving", "")).strip()}
        eenheid = payload.get("eenheid")
        if eenheid not in (None, "", "null"):
            entry["eenheid"] = str(eenheid)
        entry["categorisch"] = bool(payload.get("categorisch", False))
        out[col_name] = entry
    return out


def llm_voorbeeldvragen(theme: str, tables_summary: list[dict]) -> list[str]:
    llm = make_llm(settings.OPENAI_MODEL)
    system = (
        "Je bedenkt voorbeeldvragen die een gebruiker aan een ruimtelijke "
        "data-assistent zou kunnen stellen. Antwoord met JSON-array van 5-8 strings."
    )
    human = (
        f"Thema: {theme}\n"
        f"Tabellen:\n{json.dumps(tables_summary, ensure_ascii=False, indent=2)}\n\n"
        "Geef 5-8 concrete Nederlandstalige voorbeeldvragen die met deze data "
        "beantwoord kunnen worden. Alleen een JSON-array van strings."
    )
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
    raw = resp.content if isinstance(resp.content, str) else str(resp.content)
    try:
        parsed = json.loads(_strip_to_json(raw))
    except Exception:
        logger.exception("LLM returned non-JSON voorbeeldvragen for %s", theme)
        return []
    return [str(q) for q in parsed if isinstance(q, (str, int))]


def build_table_metadata(
    con: duckdb.DuckDBPyConnection,
    table_dir: Path,
    old_index: dict[str, dict],
    existing_table: dict | None,
) -> dict:
    table_name = table_dir.name
    group = derive_group(table_name)
    parquet_glob = str(table_dir / "*.parquet")
    raw_cols = read_parquet_columns(con, parquet_glob)

    is_cbs = table_name.startswith("cbs_")
    existing_cols: dict[str, dict] = (
        (existing_table or {}).get("kolommen", {}) if existing_table else {}
    )

    kolommen: dict[str, dict] = {}
    needs_llm: list[tuple[str, str, list[str]]] = []

    for raw_name, raw_type in raw_cols:
        canonical_name = raw_name
        # CBS uses h3_index; canonical name is h3_id everywhere in metadata.
        if is_cbs and raw_name == CBS_ID_RENAME[0]:
            canonical_name = CBS_ID_RENAME[1]

        # Skip if already present in existing output (idempotency).
        if canonical_name in existing_cols:
            kolommen[canonical_name] = existing_cols[canonical_name]
            continue

        # Try reuse from old metadata. Also look up the un-renamed name for h3_index.
        reuse = old_index.get(canonical_name) or old_index.get(raw_name)
        entry: dict = {
            "type": raw_type,
            "groep": group,
            "categorisch": False,
        }
        if reuse:
            if "beschrijving" in reuse:
                entry["beschrijving"] = reuse["beschrijving"]
            if "eenheid" in reuse:
                entry["eenheid"] = reuse["eenheid"]
            if "categorisch" in reuse:
                entry["categorisch"] = bool(reuse["categorisch"])
            kolommen[canonical_name] = entry
        else:
            samples = sample_distinct_values(con, parquet_glob, raw_name)
            needs_llm.append((canonical_name, raw_type, samples))
            kolommen[canonical_name] = entry  # placeholder; filled below

    if needs_llm:
        logger.info("Table %s: %d columns need LLM fill", table_name, len(needs_llm))
        filled = llm_fill_columns(table_name, needs_llm)
        for col_name, payload in filled.items():
            if col_name not in kolommen:
                continue
            kolommen[col_name].update(
                {
                    "beschrijving": payload.get("beschrijving", ""),
                    "categorisch": bool(payload.get("categorisch", False)),
                }
            )
            if "eenheid" in payload:
                kolommen[col_name]["eenheid"] = payload["eenheid"]

    return {"naam": table_name, "groep": group, "kolommen": kolommen}


def build_theme_metadata(
    con: duckdb.DuckDBPyConnection,
    theme: str,
    table_dirs: list[Path],
    old_index: dict[str, dict],
    existing: dict | None,
) -> dict:
    existing_tables_by_name: dict[str, dict] = {}
    if existing:
        for t in existing.get("data", []):
            existing_tables_by_name[t.get("naam")] = t

    data: list[dict] = []
    for table_dir in table_dirs:
        existing_table = existing_tables_by_name.get(table_dir.name)
        data.append(build_table_metadata(con, table_dir, old_index, existing_table))

    voorbeeldvragen: list[str] = (existing or {}).get("voorbeeldvragen", [])
    if not voorbeeldvragen:
        tables_summary = [
            {
                "naam": t["naam"],
                "groep": t["groep"],
                "kolommen": list(t["kolommen"].keys())[:25],
            }
            for t in data
        ]
        voorbeeldvragen = llm_voorbeeldvragen(theme, tables_summary)

    return {
        "naam": theme,
        "label": (existing or {}).get("label", theme.title()),
        "voorbeeldvragen": voorbeeldvragen,
        "data": data,
    }


def main() -> None:
    old_index = load_old_metadata_index()
    con = duckdb.connect()
    for theme, table_dirs in discover_themes():
        out_path = data_DIR / f"_llm_metadata_{theme}.json"
        existing: dict | None = None
        if out_path.exists():
            try:
                existing = json.loads(out_path.read_text())
            except Exception:
                logger.warning("Existing %s is not valid JSON; regenerating", out_path)

        logger.info("Theme %s: %d tables", theme, len(table_dirs))
        theme_meta = build_theme_metadata(con, theme, table_dirs, old_index, existing)
        out_path.write_text(json.dumps(theme_meta, ensure_ascii=False, indent=2) + "\n")
        logger.info("Wrote %s", out_path)


if __name__ == "__main__":
    main()
