import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.mlflow_monitoring.mlflow_setup import init_mlflow
from app.routers import (
    chat,
    dictionary,
    feedback,
    health,
    query,
    sessions,
)
from app.services import dictionary_service
from app.services.dictionary_service import generate_dictionary

logger = logging.getLogger(__name__)


async def _warm_up(app: FastAPI) -> None:
    """Run heavy startup tasks in the background so the health probe can respond immediately."""
    try:
        logger.info("Generating data dictionary from metadata + Delta table ...")
        local_dictionary = await generate_dictionary()
        dictionary_service.set_local_dictionary(local_dictionary)
        logger.info(
            "Dictionary ready: %d columns in %d themes",
            local_dictionary.total_columns,
            len(local_dictionary.themes),
        )
        app.state.ready = True
    except Exception:
        logger.exception("Background warm-up failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_mlflow()
    app.state.ready = False
    task = asyncio.create_task(_warm_up(app))
    yield
    task.cancel()


app = FastAPI(title="Ruimtelijke Assistent", lifespan=lifespan)

# CORS
origins = (
    settings.ALLOWED_ORIGINS.split(",") if settings.ALLOWED_ORIGINS != "*" else ["*"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=settings.ALLOWED_ORIGINS != "*",
    allow_methods=["*"],
    allow_headers=["*"],
)


# Routers
app.include_router(health.router)
app.include_router(dictionary.router)
app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(feedback.router)
app.include_router(query.router)
