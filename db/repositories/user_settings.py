from __future__ import annotations

from datetime import datetime, timezone

from beartype import beartype
from sqlalchemy import select, text
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
    business_connection_id: object = _UNSET,
    last_brief_date: object = _UNSET,
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
    if business_connection_id is not _UNSET:
        row.business_connection_id = business_connection_id if isinstance(business_connection_id, str) else None
    if last_brief_date is not _UNSET:
        row.last_brief_date = last_brief_date if isinstance(last_brief_date, str) else None
    return row


@beartype
async def get_owner_by_bcid(session: AsyncSession, bcid: str) -> int | None:
    """Return owner_id for a given business_connection_id, or None if unknown."""
    result = await session.execute(
        select(UserSettings.owner_id).where(UserSettings.business_connection_id == bcid)
    )
    return result.scalar_one_or_none()


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


@beartype
async def get_all_users_ordered(session: AsyncSession) -> list[UserSettings]:
    """Return all users ordered by creation date descending (newest first)."""
    result = await session.execute(
        select(UserSettings).order_by(UserSettings.created_at.desc())
    )
    return list(result.scalars().all())


@beartype
async def accept_privacy(session: AsyncSession, owner_id: int) -> None:
    """Record that the user accepted the privacy policy."""
    row = await get_or_create(session, owner_id)
    row.privacy_accepted_at = datetime.now(timezone.utc)


@beartype
async def delete_all_user_data(session: AsyncSession, owner_id: int) -> None:
    """Permanently delete all data associated with this user across all tables."""
    tables = [
        "tasks",
        "messages",
        "contacts",
        "ghost_sessions",
        "oauth_tokens",
        "integration_configs",
        "user_settings",
    ]
    for table in tables:
        await session.execute(
            text(f"DELETE FROM {table} WHERE owner_id = :uid"),  # noqa: S608
            {"uid": owner_id},
        )
