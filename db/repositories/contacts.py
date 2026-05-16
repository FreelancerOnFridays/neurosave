from __future__ import annotations

from datetime import datetime, timezone

from beartype import beartype
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Contact, Task, TaskStatus


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
async def update_crm(
    session: AsyncSession,
    owner_id: int,
    contact_id: int,
    crm_status: str | None = None,
    notes: str | None = None,
    next_action: str | None = None,
    next_action_date: datetime | None = None,
    importance: int | None = None,
    email: str | None = None,
) -> Contact | None:
    result = await session.execute(
        select(Contact).where(Contact.owner_id == owner_id, Contact.id == contact_id)
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        return None
    if crm_status is not None:
        contact.crm_status = crm_status
    if notes is not None:
        contact.notes = notes
    if next_action is not None:
        contact.next_action = next_action
    if next_action_date is not None:
        contact.next_action_date = next_action_date
    if importance is not None:
        contact.importance = importance
    if email is not None:
        contact.email = email
    return contact


@beartype
async def get_contact_by_id(session: AsyncSession, owner_id: int, contact_id: int) -> Contact | None:
    result = await session.execute(
        select(Contact).where(Contact.owner_id == owner_id, Contact.id == contact_id)
    )
    return result.scalar_one_or_none()


@beartype
async def get_contact_history(
    session: AsyncSession, owner_id: int, contact_user_id: int
) -> dict[str, int]:
    result = await session.execute(
        select(
            func.count(Task.id).filter(Task.status == TaskStatus.open).label("open_tasks"),
            func.count(Task.id).filter(Task.status == TaskStatus.done).label("done_tasks"),
            func.count(Task.id).label("total_tasks"),
        ).where(
            Task.owner_id == owner_id,
            Task.chat_id == contact_user_id,
            Task.is_personal.is_(False),
        )
    )
    row = result.one()
    return {
        "open_tasks": row.open_tasks or 0,
        "done_tasks": row.done_tasks or 0,
        "total_tasks": row.total_tasks or 0,
    }


@beartype
async def list_crm_contacts(
    session: AsyncSession,
    owner_id: int,
    crm_status: str | None = None,
) -> list[Contact]:
    q = select(Contact).where(Contact.owner_id == owner_id)
    if crm_status:
        q = q.where(Contact.crm_status == crm_status)
    q = q.order_by(Contact.importance.desc(), Contact.last_seen.desc().nulls_last())
    result = await session.execute(q)
    return list(result.scalars().all())


@beartype
async def get_vip_list(session: AsyncSession, owner_id: int) -> list[Contact]:
    result = await session.execute(
        select(Contact).where(Contact.owner_id == owner_id, Contact.is_vip.is_(True))
    )
    return list(result.scalars().all())
