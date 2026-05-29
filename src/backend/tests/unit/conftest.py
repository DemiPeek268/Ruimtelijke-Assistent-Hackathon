import pytest

from app.models.dictionary import ColumnInfo, DataDictionary, TableInfo, Theme


@pytest.fixture
def mock_dictionary() -> DataDictionary:
    col = ColumnInfo(
        name="verkeer_totaal_2020",
        type="INTEGER",
        table="verkeer_tabel",
        group="Verkeer",
    )
    table = TableInfo(name="verkeer_tabel", group="Verkeer", columns=[col])
    theme = Theme(name="verkeer", label="Verkeer", tables=[table])
    return DataDictionary(total_rows=1000, total_columns=1, themes=[theme])


@pytest.fixture
def graph_mock_dictionary() -> DataDictionary:
    col_h3 = ColumnInfo(
        name="h3_id", type="VARCHAR", table="verkeer_tabel", group="Verkeer"
    )
    col_verkeer = ColumnInfo(
        name="verkeer_totaal_2020",
        type="INTEGER",
        table="verkeer_tabel",
        group="Verkeer",
    )
    col_gemeente = ColumnInfo(
        name="gemeente_Gemeentenaam",
        type="VARCHAR",
        categorical=True,
        table="gemeente_tabel",
        group="Gemeente",
    )
    col_geluid = ColumnInfo(
        name="geluid_wegverkeer_Lden_2021_perc",
        type="DOUBLE",
        table="geluid_tabel",
        group="Geluid",
    )
    tables = [
        TableInfo(name="verkeer_tabel", group="Verkeer", columns=[col_h3, col_verkeer]),
        TableInfo(name="gemeente_tabel", group="Gemeente", columns=[col_gemeente]),
        TableInfo(name="geluid_tabel", group="Geluid", columns=[col_geluid]),
    ]
    theme = Theme(name="test", label="Test", tables=tables)
    return DataDictionary(total_rows=1000, total_columns=4, themes=[theme])


@pytest.fixture
def graph_base_state(graph_mock_dictionary) -> dict:
    return {
        "messages": [{"role": "user", "content": "Toon verkeer"}],
        "dictionary": graph_mock_dictionary,
        "model": "gpt-4o",
        "intent_analysis": None,
        "needs_spatial_resolution": False,
        "pdok_used": False,
        "sql_query": None,
        "query_result": None,
        "map_plan": None,
        "explanation": None,
    }
