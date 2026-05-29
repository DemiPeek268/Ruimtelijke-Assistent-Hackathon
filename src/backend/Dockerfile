# --- Stage 1: Builder ---
FROM --platform=linux/amd64 python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
ARG UV_INDEX_PZH_USERNAME=dummy
RUN --mount=type=secret,id=uv_index_pzh_password \
    UV_INDEX_PZH_USERNAME=${UV_INDEX_PZH_USERNAME} \
    UV_INDEX_PZH_PASSWORD=$(cat /run/secrets/uv_index_pzh_password) \
    uv sync --frozen --no-dev --no-cache && rm -rf /root/.cache

# --- Stage 2: Runtime ---
FROM --platform=linux/amd64 python:3.12-slim AS runner

ARG GIT_SHA=unknown
ENV GIT_SHA=$GIT_SHA \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8000

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY app/ ./app
COPY alembic/ ./alembic
COPY alembic.ini ./alembic.ini
COPY data/ ./data

# Pre-install DuckDB extensions so they're available in closed networks
RUN python -c "import duckdb; con = duckdb.connect(); con.execute('INSTALL delta'); con.execute('INSTALL h3 FROM community'); con.close()"

EXPOSE ${PORT}

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
