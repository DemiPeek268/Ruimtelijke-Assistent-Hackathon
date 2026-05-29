"""DuckDB connection helpers."""

from contextlib import contextmanager

import duckdb


@contextmanager
def connect_delta():
    """Context manager: yields a DuckDB connection with the Delta extension loaded."""
    con = duckdb.connect()
    try:
        try:
            con.execute("LOAD delta;")
        except duckdb.Error:
            con.execute("INSTALL delta; LOAD delta;")
        yield con
    finally:
        con.close()
