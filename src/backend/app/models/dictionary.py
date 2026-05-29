from pydantic import BaseModel


class ColumnInfo(BaseModel):
    name: str
    type: str
    table: str
    group: str
    min: str | None = None
    max: str | None = None
    mean: str | None = None
    sample_values: list[str] = []
    description: str = ""
    unit: str | None = None
    categorical: bool = False


class TableInfo(BaseModel):
    name: str
    group: str
    columns: list[ColumnInfo]


class Theme(BaseModel):
    name: str
    label: str
    example_questions: list[str] = []
    tables: list[TableInfo]


class DataDictionary(BaseModel):
    total_rows: int
    total_columns: int
    themes: list[Theme]

    def all_tables(self) -> list[TableInfo]:
        return [t for theme in self.themes for t in theme.tables]

    def all_columns(self) -> list[ColumnInfo]:
        return [c for t in self.all_tables() for c in t.columns]
