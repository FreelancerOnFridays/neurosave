from __future__ import annotations

from datetime import datetime, timezone

from beartype import beartype
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import OAuthToken


@beartype
async def get_token(session: AsyncSession, owner_id: int, provider: str) -> OAuthToken | None:
    result = await session.execute(
        select(OAuthToken).where(
            OAuthToken.owner_id == owner_id,
            OAuthToken.provider == provider,
        )
    )
    return result.scalar_one_or_none()


@beartype
async def upsert_token(
    session: AsyncSession,
    owner_id: int,
    provider: str,
    access_token: str,
    refresh_token: str | None = None,
    token_expiry: datetime | None = None,
    scopes: str | None = None,
    email: str | None = None,
) -> OAuthToken:
    row = await get_token(session, owner_id, provider)
    if row is None:
        row = OAuthToken(owner_id=owner_id, provider=provider)
        session.add(row)
    row.access_token = access_token
    if refresh_token is not None:
        row.refresh_token = refresh_token
    if token_expiry is not None:
        row.token_expiry = token_expiry
    if scopes is not None:
        row.scopes = scopes
    if email is not None:
        row.email = email
    row.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return row


@beartype
async def delete_token(session: AsyncSession, owner_id: int, provider: str) -> None:
    row = await get_token(session, owner_id, provider)
    if row is not None:
        await session.delete(row)
        await session.flush()


@beartype
async def get_expiring_soon(session: AsyncSession, threshold_minutes: int = 10) -> list[OAuthToken]:
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) + timedelta(minutes=threshold_minutes)
    result = await session.execute(
        select(OAuthToken).where(
            OAuthToken.refresh_token.isnot(None),
            OAuthToken.token_expiry <= cutoff,
        )
    )
    return list(result.scalars().all())
