from __future__ import annotations

from datetime import datetime, timezone

from beartype import beartype
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import GhostInquiry, GhostSession, InquiryCategory


@beartype
async def get_session(session: AsyncSession, owner_id: int) -> GhostSession | None:
    result = await session.execute(
        select(GhostSession).where(GhostSession.owner_id == owner_id)
    )
    return result.scalar_one_or_none()


@beartype
async def set_active(
    session: AsyncSession,
    owner_id: int,
    active: bool,
    away_message: str | None = None,
    silent_mode: bool | None = None,
) -> GhostSession:
    existing = await get_session(session, owner_id)
    if existing is None:
        gs = GhostSession(
            owner_id=owner_id,
            is_active=active,
            away_message=away_message,
            activated_at=datetime.now(timezone.utc) if active else None,
            silent_mode=silent_mode if silent_mode is not None else False,
        )
        session.add(gs)
        await session.flush()
        return gs
    was_active = existing.is_active
    existing.is_active = active
    if away_message is not None:
        existing.away_message = away_message
    if silent_mode is not None:
        existing.silent_mode = silent_mode
    if active and (not was_active or existing.activated_at is None):
        existing.activated_at = datetime.now(timezone.utc)
    return existing


@beartype
async def set_silent_mode(
    session: AsyncSession, owner_id: int, silent: bool
) -> GhostSession | None:
    gs = await get_session(session, owner_id)
    if gs is None:
        return None
    gs.silent_mode = silent
    return gs


@beartype
async def update_away_message(
    session: AsyncSession, owner_id: int, away_message: str
) -> None:
    gs = await get_session(session, owner_id)
    if gs is not None:
        gs.away_message = away_message


@beartype
async def get_pending_inquiry(
    session: AsyncSession, owner_id: int, caller_id: int
) -> GhostInquiry | None:
    result = await session.execute(
        select(GhostInquiry).where(
            GhostInquiry.owner_id == owner_id,
            GhostInquiry.caller_id == caller_id,
            GhostInquiry.ghost_pending == True,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


@beartype
async def get_session_inquiry(
    session: AsyncSession,
    owner_id: int,
    caller_id: int,
    since: datetime,
) -> GhostInquiry | None:
    """Return the most recent inquiry for this caller within the current ghost session."""
    result = await session.execute(
        select(GhostInquiry)
        .where(
            GhostInquiry.owner_id == owner_id,
            GhostInquiry.caller_id == caller_id,
            GhostInquiry.created_at >= since,
        )
        .order_by(GhostInquiry.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


@beartype
async def create_inquiry(
    session: AsyncSession,
    owner_id: int,
    caller_id: int,
    caller_name: str | None,
    chat_id: int,
    caller_username: str | None = None,
) -> GhostInquiry:
    inquiry = GhostInquiry(
        owner_id=owner_id,
        caller_id=caller_id,
        caller_name=caller_name,
        caller_username=caller_username,
        chat_id=chat_id,
        ghost_pending=True,
    )
    session.add(inquiry)
    await session.flush()
    return inquiry


@beartype
async def resolve_inquiry(
    session: AsyncSession,
    inquiry: GhostInquiry,
    summary: str,
    category: InquiryCategory,
) -> None:
    inquiry.summary = summary
    inquiry.category = category
    inquiry.ghost_pending = False


@beartype
async def get_inquiries_since(
    session: AsyncSession, owner_id: int, since: datetime
) -> list[GhostInquiry]:
    result = await session.execute(
        select(GhostInquiry)
        .where(
            GhostInquiry.owner_id == owner_id,
            GhostInquiry.created_at >= since,
            GhostInquiry.ghost_pending == False,  # noqa: E712
            GhostInquiry.summary.isnot(None),
        )
        .order_by(GhostInquiry.category, GhostInquiry.created_at)
    )
    return list(result.scalars().all())
