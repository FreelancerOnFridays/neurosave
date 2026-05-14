from __future__ import annotations

from datetime import datetime

from beartype import beartype
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Message


@beartype
async def find_chats_by_name(
    session: AsyncSession,
    owner_id: int,
    name: str,
) -> list[tuple[int, str | None]]:
    """Return (chat_id, sender_name) pairs whose sender_name contains *name* (case-insensitive).

    Returns one entry per chat_id — the most recently seen one.
    """
    result = await session.execute(
        select(Message.chat_id, Message.sender_name)
        .where(
            Message.owner_id == owner_id,
            Message.sender_name.ilike(f"%{name}%"),
        )
        .order_by(Message.timestamp.desc())
    )
    seen: dict[int, str | None] = {}
    for chat_id, sender_name in result.all():
        if chat_id not in seen:
            seen[chat_id] = sender_name
    return list(seen.items())


@beartype
async def save_message(
    session: AsyncSession,
    *,
    owner_id: int,
    chat_id: int,
    message_id: int,
    sender_id: int | None,
    sender_name: str | None,
    text: str,
    timestamp: datetime,
) -> Message:
    msg = Message(
        owner_id=owner_id,
        chat_id=chat_id,
        message_id=message_id,
        sender_id=sender_id,
        sender_name=sender_name,
        text=text,
        timestamp=timestamp,
    )
    session.add(msg)
    await session.flush()
    return msg


@beartype
async def get_recent_owner_messages(
    session: AsyncSession,
    owner_id: int,
    limit: int = 30,
) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(
            Message.owner_id == owner_id,
            Message.sender_id == owner_id,
        )
        .order_by(Message.timestamp.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


@beartype
async def get_recent_messages_in_chat(
    session: AsyncSession,
    owner_id: int,
    chat_id: int,
    limit: int = 5,
) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.owner_id == owner_id, Message.chat_id == chat_id)
        .order_by(Message.timestamp.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


@beartype
async def get_messages_in_range(
    session: AsyncSession,
    owner_id: int,
    since: datetime,
    until: datetime,
) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(
            Message.owner_id == owner_id,
            Message.timestamp >= since,
            Message.timestamp <= until,
        )
        .order_by(Message.timestamp.asc())
    )
    return list(result.scalars().all())


@beartype
async def set_embedding(
    session: AsyncSession,
    message_id: int,
    embedding: list[float],
) -> None:
    await session.execute(
        update(Message).where(Message.id == message_id).values(embedding=embedding)
    )


@beartype
async def search_similar(
    session: AsyncSession,
    owner_id: int,
    query_embedding: list[float],
    limit: int = 10,
) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(
            Message.owner_id == owner_id,
            Message.embedding.isnot(None),  # type: ignore[union-attr]
        )
        .order_by(Message.embedding.cosine_distance(query_embedding))  # type: ignore[union-attr]
        .limit(limit)
    )
    return list(result.scalars().all())
