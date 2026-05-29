from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings


def make_engine(**engine_kwargs):
    return create_async_engine(
        settings.DATABASE_URL, echo=settings.DEBUG, **engine_kwargs
    )


engine = make_engine()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
