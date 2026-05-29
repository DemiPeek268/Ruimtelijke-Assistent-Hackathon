import asyncio
import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.services.helpers.db import connect_delta
from app.services.helpers.tables import register_tables

router = APIRouter()
logger = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    sql: str


@router.post("/api/query")
async def run_query(body: QueryRequest):
    def _run():
        with connect_delta() as con:
            try:
                con.execute("LOAD h3;")
            except Exception:
                con.execute("INSTALL h3 FROM community; LOAD h3;")
            register_tables(con)
            result = con.execute(body.sql).fetchall()
            columns = [desc[0] for desc in con.description]
            return [dict(zip(columns, row)) for row in result]

    try:
        rows = await asyncio.to_thread(_run)
    except Exception as exc:
        logger.exception("Query execution failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {"rows": rows}
