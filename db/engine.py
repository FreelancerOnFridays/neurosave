from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from beartype import beartype
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings

engine = create_async_engine(settings.database_url, echo=False)

session_factory = async_sessionmaker(engine, expire_on_commit=False)


@beartype
@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
