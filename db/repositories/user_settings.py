from __future__ import annotations

from beartype import beartype
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import UserSettings

_DEFAULT_LANG = "ru"
_DEFAULT_TZ = "Europe/Moscow"
_DEFAULT_BRIEF_TIME = "09:00"


@beartype
async def get_or_create(session: AsyncSession, owner_id: int) -> UserSettings:
    row = await session.get(UserSettings, owner_id)
    if row is None:
        row = UserSettings(owner_id=owner_id)
        session.add(row)
        await session.flush()
    return row


_UNSET = object()


async def update_settings(
    session: AsyncSession,
    owner_id: int,
    language: str | None = None,
    timezone: str | None = None,
    brief_time: str | None = None,
    brief_enabled: bool | None = None,
    theme: str | None = None,
    telethon_session: object = _UNSET,
) -> UserSettings:
    row = await get_or_create(session, owner_id)
    if language is not None:
        row.language = language
    if timezone is not None:
        row.timezone = timezone
    if brief_time is not None:
        row.brief_time = brief_time
    if brief_enabled is not None:
        row.brief_enabled = brief_enabled
    if theme is not None:
        row.theme = theme
    if telethon_session is not _UNSET:
        row.telethon_session = telethon_session if isinstance(telethon_session, str) else None
    return row


@beartype
async def get_all_owner_ids(session: AsyncSession) -> list[int]:
    """Return all owner_ids that have a settings row (i.e. ever used the bot)."""
    result = await session.execute(select(UserSettings.owner_id))
    return list(result.scalars().all())


@beartype
async def get_brief_users(session: AsyncSession) -> list[UserSettings]:
    """Return all users with brief_enabled=True."""
    result = await session.execute(
        select(UserSettings).where(UserSettings.brief_enabled.is_(True))
    )
    return list(result.scalars().all())
