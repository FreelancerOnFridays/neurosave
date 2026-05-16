from __future__ import annotations

import logging
from datetime import datetime, timezone

from beartype import beartype
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient
from telethon.tl.functions.contacts import GetContactsRequest
from telethon.tl.functions.messages import GetDialogFiltersRequest
from telethon.tl.types import (
    DialogFilter,
    User,
)

from db.models import Contact

logger = logging.getLogger(__name__)


@beartype
async def list_folders(client: TelegramClient) -> list[str]:
    """Return names of all custom chat folders the user has."""
    result = await client(GetDialogFiltersRequest())
    names: list[str] = []
    for f in result.filters:
        if isinstance(f, DialogFilter) and hasattr(f, "title"):
            title = f.title
            if hasattr(title, "text"):
                names.append(title.text)
            elif isinstance(title, str):
                names.append(title)
    return names


async def _get_folder_filter(client: TelegramClient, folder_name: str) -> DialogFilter | None:
    """Return the DialogFilter for a folder by name, or None if not found."""
    result = await client(GetDialogFiltersRequest())
    for f in result.filters:
        if isinstance(f, DialogFilter) and hasattr(f, "title"):
            title = f.title
            title_text = title.text if hasattr(title, "text") else str(title)
            if title_text.lower() == folder_name.lower():
                return f
    return None


async def get_folder_users(client: TelegramClient, folder_name: str) -> list[User]:
    """Return User objects for all private chats explicitly listed in a Telegram folder."""
    folder_filter = await _get_folder_filter(client, folder_name)
    if folder_filter is None:
        return []

    # Collect user_ids from include_peers and pinned_peers (explicit members of the folder)
    folder_user_ids: set[int] = set()
    for peer in list(getattr(folder_filter, "include_peers", [])) + list(getattr(folder_filter, "pinned_peers", [])):
        if hasattr(peer, "user_id"):
            folder_user_ids.add(peer.user_id)

    if not folder_user_ids:
        return []

    # Resolve entities via all dialogs (reliable, avoids folder_id quirks)
    all_dialogs = await client.get_dialogs(limit=500)
    users: list[User] = []
    for dialog in all_dialogs:
        entity = dialog.entity
        if isinstance(entity, User) and not entity.bot and entity.id in folder_user_ids:
            users.append(entity)
    return users


def _build_display_name(user: User) -> str | None:
    parts = [user.first_name or "", user.last_name or ""]
    name = " ".join(p for p in parts if p).strip()
    return name or user.username or None


async def _upsert_from_tg_user(
    session: AsyncSession,
    owner_id: int,
    user: User,
    team_label: str | None = None,
) -> bool:
    """Upsert one Telegram user into contacts. Returns True if new row was created."""
    result = await session.execute(
        select(Contact).where(
            Contact.owner_id == owner_id,
            Contact.user_id == user.id,
        )
    )
    contact = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    display_name = _build_display_name(user)

    if contact is None:
        phone: str | None = getattr(user, "phone", None)
        contact = Contact(
            owner_id=owner_id,
            user_id=user.id,
            name=display_name,
            username=user.username,
            tg_first_name=user.first_name,
            tg_last_name=user.last_name,
            phone=phone,
            team_label=team_label,
            synced_from="telethon",
            last_synced_at=now,
        )
        session.add(contact)
        return True
    else:
        if display_name:
            contact.name = display_name
        if user.username:
            contact.username = user.username
        contact.tg_first_name = user.first_name
        contact.tg_last_name = user.last_name
        phone = getattr(user, "phone", None)
        if phone:
            contact.phone = phone
        if team_label:
            contact.team_label = team_label
        contact.synced_from = "telethon"
        contact.last_synced_at = now
        return False


@beartype
async def sync_all_contacts(
    client: TelegramClient,
    owner_id: int,
    session: AsyncSession,
) -> int:
    """Pull all phone-book contacts via MTProto and upsert to contacts table. Returns count added/updated."""
    result = await client(GetContactsRequest(hash=0))
    users: list[User] = [u for u in result.users if isinstance(u, User) and not u.bot]

    added = 0
    updated = 0
    for user in users:
        is_new = await _upsert_from_tg_user(session, owner_id, user)
        if is_new:
            added += 1
        else:
            updated += 1

    await session.flush()
    logger.info("sync_all_contacts: added=%d updated=%d for owner=%d", added, updated, owner_id)
    return added + updated


@beartype
async def sync_all_with_folders(
    client: TelegramClient,
    owner_id: int,
    session: AsyncSession,
) -> int:
    """Sync all phone-book contacts then tag each by their Telegram folder."""
    total = await sync_all_contacts(client, owner_id, session)
    try:
        folders = await list_folders(client)
        for folder_name in folders:
            try:
                await sync_folder_contacts(client, owner_id, folder_name, session)
            except Exception:
                logger.warning("Failed to sync folder '%s' for owner %d", folder_name, owner_id)
    except Exception:
        logger.warning("Failed to list folders for owner %d during full sync", owner_id)
    return total


@beartype
async def sync_folder_contacts(
    client: TelegramClient,
    owner_id: int,
    folder_name: str,
    session: AsyncSession,
) -> int:
    """Pull contacts from a specific chat folder and label them with team_label=folder_name."""
    users = await get_folder_users(client, folder_name)
    if not users:
        folder_filter = await _get_folder_filter(client, folder_name)
        if folder_filter is None:
            raise ValueError(f"Folder '{folder_name}' not found")

    count = 0
    for user in users:
        await _upsert_from_tg_user(session, owner_id, user, team_label=folder_name)
        count += 1

    await session.flush()
    logger.info("sync_folder_contacts: folder=%s count=%d for owner=%d", folder_name, count, owner_id)
    return count
