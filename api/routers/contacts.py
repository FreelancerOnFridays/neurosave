from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_owner_id
from api.dependencies import get_db
from bot.config_store import get_last_contact_sync, set_last_contact_sync
from config import settings
from db.models import Contact
from db.repositories import user_settings as us_repo

logger = logging.getLogger(__name__)
router = APIRouter()


class ContactOut(BaseModel):
    id: int
    user_id: int
    name: str | None
    username: str | None
    phone: str | None
    email: str | None
    team_label: str | None
    synced_from: str | None
    last_seen: datetime | None
    last_synced_at: datetime | None

    model_config = {"from_attributes": True}


class SyncStatus(BaseModel):
    last_sync: str | None
    telethon_authorized: bool
    telethon_configured: bool


class FolderOut(BaseModel):
    name: str


@router.get("", response_model=list[ContactOut])
async def list_contacts(
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> list[Contact]:
    result = await session.execute(
        select(Contact)
        .where(Contact.owner_id == owner_id)
        .order_by(Contact.name.asc().nulls_last())
    )
    return list(result.scalars().all())


@router.get("/status", response_model=SyncStatus)
async def sync_status(
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> SyncStatus:
    import bot.telethon_client as tg_client

    us = await us_repo.get_or_create(session, owner_id)
    last_sync = get_last_contact_sync()
    configured = tg_client.is_configured()
    authorized = await tg_client.is_authorized(owner_id, us.telethon_session) if configured else False
    return SyncStatus(
        last_sync=last_sync or None,
        telethon_authorized=authorized,
        telethon_configured=configured,
    )


@router.get("/folders", response_model=list[FolderOut])
async def get_folders(
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> list[FolderOut]:
    import bot.telethon_client as tg_client
    from services.contact_sync import list_folders

    us = await us_repo.get_or_create(session, owner_id)
    if not tg_client.is_configured():
        raise HTTPException(status_code=503, detail="Telethon not configured")
    if not await tg_client.is_authorized(owner_id, us.telethon_session):
        raise HTTPException(status_code=503, detail="Telethon not authorized")

    client = await tg_client.get_client(owner_id, us.telethon_session)
    if client is None:
        raise HTTPException(status_code=503, detail="Telethon client unavailable")

    folders = await list_folders(client)
    return [FolderOut(name=name) for name in folders]


async def _run_sync(owner_id: int, session_str: str | None) -> None:
    import bot.telethon_client as tg_client
    from services.contact_sync import sync_all_with_folders
    from db.engine import session_factory

    client = await tg_client.get_client(owner_id, session_str)
    if client is None:
        return
    async with session_factory() as db:
        async with db.begin():
            count = await sync_all_with_folders(client, owner_id, db)
    set_last_contact_sync(datetime.now(timezone.utc).isoformat())
    logger.info("API-triggered sync complete: %d contacts for owner %d", count, owner_id)


@router.post("/sync", status_code=202)
async def trigger_sync(
    background_tasks: BackgroundTasks,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    import bot.telethon_client as tg_client

    us = await us_repo.get_or_create(session, owner_id)
    if not tg_client.is_configured():
        raise HTTPException(status_code=503, detail="Telethon not configured")
    if not await tg_client.is_authorized(owner_id, us.telethon_session):
        raise HTTPException(status_code=503, detail="Telethon not authorized — use /sync_contacts in bot chat first")

    background_tasks.add_task(_run_sync, owner_id, us.telethon_session)
    return {"status": "syncing"}


@router.post("/sync-folder", status_code=202)
async def trigger_folder_sync(
    body: dict[str, str],
    background_tasks: BackgroundTasks,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    import bot.telethon_client as tg_client

    folder_name = body.get("folder_name", "").strip()
    if not folder_name:
        raise HTTPException(status_code=422, detail="folder_name is required")
    us = await us_repo.get_or_create(session, owner_id)
    if not tg_client.is_configured():
        raise HTTPException(status_code=503, detail="Telethon not configured")
    if not await tg_client.is_authorized(owner_id, us.telethon_session):
        raise HTTPException(status_code=503, detail="Telethon not authorized")

    session_str = us.telethon_session

    async def _run() -> None:
        from services.contact_sync import sync_folder_contacts
        from db.engine import session_factory

        client = await tg_client.get_client(owner_id, session_str)
        if client is None:
            return
        async with session_factory() as db:
            async with db.begin():
                await sync_folder_contacts(client, owner_id, folder_name, db)

    background_tasks.add_task(_run)
    return {"status": "syncing", "folder": folder_name}
