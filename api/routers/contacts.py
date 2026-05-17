from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func as sql_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_owner_id
from api.dependencies import get_db
from bot.config_store import get_last_contact_sync, set_last_contact_sync
from db.models import Contact
from db.repositories import user_settings as us_repo

logger = logging.getLogger(__name__)
router = APIRouter()


class ContactOut(BaseModel):
    id: int
    user_id: int
    name: str | None
    saved_name: str | None = None
    username: str | None
    phone: str | None
    email: str | None
    team_label: str | None
    labels: list[str] = []
    synced_from: str | None
    last_seen: datetime | None
    last_synced_at: datetime | None
    is_vip: bool = False

    model_config = {"from_attributes": True}


class ContactPatchIn(BaseModel):
    saved_name: str | None = None
    email: str | None = None


class ContactLabelsIn(BaseModel):
    labels: list[str]


class SyncStatus(BaseModel):
    last_sync: str | None
    telethon_authorized: bool
    telethon_configured: bool
    contact_count: int = 0


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
    count_result = await session.execute(
        select(sql_func.count()).select_from(Contact).where(Contact.owner_id == owner_id)
    )
    contact_count = count_result.scalar_one()
    return SyncStatus(
        last_sync=last_sync or None,
        telethon_authorized=authorized,
        telethon_configured=configured,
        contact_count=contact_count,
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


@router.get("/labels", response_model=list[str])
async def get_labels(
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> list[str]:
    from db.repositories import contacts as contact_repo
    return await contact_repo.get_all_labels(session, owner_id)


@router.put("/{user_id}/labels", response_model=ContactOut)
async def set_contact_labels(
    user_id: int,
    body: ContactLabelsIn,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> Contact:
    from db.repositories import contacts as contact_repo

    contact = await contact_repo.set_contact_labels(session, owner_id, user_id, body.labels)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    await session.commit()
    return contact


@router.patch("/{user_id}", response_model=ContactOut)
async def update_contact(
    user_id: int,
    body: ContactPatchIn,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> Contact:
    from db.repositories import contacts as contact_repo
    from db.repositories import integration_configs as cfg_repo

    contact = await contact_repo.get_contact(session, owner_id, user_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    if body.saved_name is not None:
        contact.saved_name = body.saved_name.strip() or None
    if body.email is not None:
        contact.email = body.email.strip() or None
        if contact.saved_name or contact.name:
            name_key = (contact.saved_name or contact.name or "").lower()
            await cfg_repo.set_config(session, owner_id, f"email_for:{name_key}", contact.email or "")
    await session.commit()
    return contact


@router.get("/{user_id}/avatar")
async def get_contact_avatar(
    user_id: int,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> Response:
    import httpx
    from config import settings as app_settings

    token = app_settings.bot_token
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            photos_resp = await client.get(
                f"https://api.telegram.org/bot{token}/getUserProfilePhotos",
                params={"user_id": user_id, "limit": 1},
            )
            photos_data = photos_resp.json()
            photos = photos_data.get("result", {}).get("photos", [])
            if not photos:
                raise HTTPException(status_code=404, detail="No avatar")
            file_id = photos[0][-1]["file_id"]

            file_resp = await client.get(
                f"https://api.telegram.org/bot{token}/getFile",
                params={"file_id": file_id},
            )
            file_path = file_resp.json().get("result", {}).get("file_path")
            if not file_path:
                raise HTTPException(status_code=404, detail="No avatar")

            img_resp = await client.get(
                f"https://api.telegram.org/file/bot{token}/{file_path}"
            )
            return Response(content=img_resp.content, media_type="image/jpeg")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Avatar fetch failed for user %d: %s", user_id, exc)
        raise HTTPException(status_code=404, detail="Avatar unavailable")


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


