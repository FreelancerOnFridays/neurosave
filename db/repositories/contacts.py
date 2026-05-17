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
    username: str | None = None,
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
            username=username,
            has_business_chat=has_business_chat,
            last_seen=now,
        )
        session.add(contact)
    else:
        if name:
            contact.name = name
        if username:
            contact.username = username
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
async def find_contacts_by_label(
    session: AsyncSession,
    owner_id: int,
    label: str,
) -> list[Contact]:
    result = await session.execute(
        select(Contact)
        .where(
            Contact.owner_id == owner_id,
            Contact.team_label.ilike(label),
        )
        .order_by(Contact.last_seen.desc().nulls_last())
    )
    return list(result.scalars().all())


@beartype
async def set_contact_labels(
    session: AsyncSession,
    owner_id: int,
    user_id: int,
    labels: list[str],
) -> Contact | None:
    result = await session.execute(
        select(Contact).where(Contact.owner_id == owner_id, Contact.user_id == user_id)
    )
    contact = result.scalar_one_or_none()
    if contact:
        contact.labels = labels
    return contact


@beartype
async def get_all_labels(session: AsyncSession, owner_id: int) -> list[str]:
    result = await session.execute(
        select(Contact.labels).where(Contact.owner_id == owner_id)
    )
    all_labels: set[str] = set()
    for (labels_arr,) in result.all():
        if labels_arr:
            all_labels.update(labels_arr)
    return sorted(all_labels)


@beartype
async def add_label_to_contact(
    session: AsyncSession,
    owner_id: int,
    user_id: int,
    label: str,
) -> Contact | None:
    result = await session.execute(
        select(Contact).where(Contact.owner_id == owner_id, Contact.user_id == user_id)
    )
    contact = result.scalar_one_or_none()
    if contact:
        existing = list(contact.labels or [])
        if label not in existing:
            existing.append(label)
            contact.labels = existing
    return contact


@beartype
async def get_recent_contacts(
    session: AsyncSession,
    owner_id: int,
    limit: int = 12,
) -> list[Contact]:
    result = await session.execute(
        select(Contact)
        .where(Contact.owner_id == owner_id)
        .order_by(Contact.last_seen.desc().nulls_last())
        .limit(limit)
    )
    return list(result.scalars().all())


@beartype
async def set_email(
    session: AsyncSession,
    owner_id: int,
    user_id: int,
    email: str,
) -> Contact | None:
    result = await session.execute(
        select(Contact).where(Contact.owner_id == owner_id, Contact.user_id == user_id)
    )
    contact = result.scalar_one_or_none()
    if contact:
        contact.email = email
    return contact


@beartype
async def find_contact_by_email(
    session: AsyncSession,
    owner_id: int,
    email: str,
) -> Contact | None:
    result = await session.execute(
        select(Contact).where(Contact.owner_id == owner_id, Contact.email == email)
    )
    return result.scalar_one_or_none()


@beartype
async def get_vip_list(session: AsyncSession, owner_id: int) -> list[Contact]:
    result = await session.execute(
        select(Contact).where(Contact.owner_id == owner_id, Contact.is_vip.is_(True))
    )
    return list(result.scalars().all())
