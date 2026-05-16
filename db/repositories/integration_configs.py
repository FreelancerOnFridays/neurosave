from __future__ import annotations

from datetime import datetime, timezone

from beartype import beartype
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import IntegrationConfig


@beartype
async def get_config(session: AsyncSession, owner_id: int, key: str) -> str | None:
    result = await session.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.owner_id == owner_id,
            IntegrationConfig.key == key,
        )
    )
    row = result.scalar_one_or_none()
    return row.value if row else None


@beartype
async def set_config(session: AsyncSession, owner_id: int, key: str, value: str) -> None:
    result = await session.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.owner_id == owner_id,
            IntegrationConfig.key == key,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = IntegrationConfig(owner_id=owner_id, key=key, value=value)
        session.add(row)
    else:
        row.value = value
        row.updated_at = datetime.now(timezone.utc)


@beartype
async def delete_config(session: AsyncSession, owner_id: int, key: str) -> None:
    result = await session.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.owner_id == owner_id,
            IntegrationConfig.key == key,
        )
    )
    row = result.scalar_one_or_none()
    if row is not None:
        await session.delete(row)
