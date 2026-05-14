from __future__ import annotations

from datetime import datetime, timezone

from beartype import beartype
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Contact


@beartype
async def upsert_contact(
    session: AsyncSession,
    owner_id: int,
    user_id: int,
    name: str | None = None,
    has_business_chat: bool = False,
) -> Contact:
    result = await session.execute(
        select(Contact).where(
            Contact.owner_id == owner_id,
            Contact.user_id == user_id,
        )
    )
    contact = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if contact is None:
        contact = Contact(
            owner_id=owner_id,
            user_id=user_id,
            name=name,
            has_business_chat=has_business_chat,
            last_seen=now,
        )
        session.add(contact)
    else:
        if name:
            contact.name = name
        if has_business_chat:
            contact.has_business_chat = True
        contact.last_seen = now
    return contact


@beartype
async def find_contacts_by_name(
    session: AsyncSession,
    owner_id: int,
    name: str,
) -> list[Contact]:
    result = await session.execute(
        select(Contact)
        .where(
            Contact.owner_id == owner_id,
            or_(
                Contact.name.ilike(f"%{name}%"),
                Contact.saved_name.ilike(f"%{name}%"),
            ),
        )
        .order_by(Contact.last_seen.desc().nulls_last())
    )
    return list(result.scalars().all())


@beartype
async def set_saved_name(
    session: AsyncSession,
    owner_id: int,
    user_id: int,
    saved_name: str | None,
) -> Contact | None:
    result = await session.execute(
        select(Contact).where(
            Contact.owner_id == owner_id, Contact.user_id == user_id
        )
    )
    contact = result.scalar_one_or_none()
    if contact:
        contact.saved_name = saved_name
    return contact


@beartype
async def set_vip(
    session: AsyncSession, owner_id: int, user_id: int, is_vip: bool
) -> Contact | None:
    result = await session.execute(
        select(Contact).where(
            Contact.owner_id == owner_id, Contact.user_id == user_id
        )
    )
    contact = result.scalar_one_or_none()
    if contact:
        contact.is_vip = is_vip
    return contact


@beartype
async def is_vip(session: AsyncSession, owner_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(Contact.is_vip).where(
            Contact.owner_id == owner_id, Contact.user_id == user_id
        )
    )
    row = result.scalar_one_or_none()
    return bool(row)


@beartype
async def get_contact(
    session: AsyncSession,
    owner_id: int,
    user_id: int,
) -> Contact | None:
    result = await session.execute(
        select(Contact).where(
            Contact.owner_id == owner_id,
            Contact.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


@beartype
async def get_name_map(session: AsyncSession, owner_id: int) -> dict[int, str]:
    """Returns {user_id: saved_name or name} for every contact that has a display name."""
    result = await session.execute(
        select(Contact.user_id, Contact.saved_name, Contact.name).where(
            Contact.owner_id == owner_id
        )
    )
    mapping: dict[int, str] = {}
    for user_id, saved_name, name in result.all():
        display = saved_name or name
        if display:
            mapping[user_id] = display
    return mapping


@beartype
async def get_vip_list(session: AsyncSession, owner_id: int) -> list[Contact]:
    result = await session.execute(
        select(Contact).where(Contact.owner_id == owner_id, Contact.is_vip.is_(True))
    )
    return list(result.scalars().all())
