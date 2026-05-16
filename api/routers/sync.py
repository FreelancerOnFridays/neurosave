from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

import bot.telethon_client as tg_client
from api.auth import get_owner_id
from api.dependencies import get_db
from db.repositories import user_settings as us_repo

logger = logging.getLogger(__name__)
router = APIRouter()


def _state_to_step(raw: str | None) -> str | None:
    if raw == "awaiting_phone":
        return "phone"
    if raw and raw.startswith("awaiting_code:"):
        return "code"
    if raw == "awaiting_password":
        return "password"
    return None


class SyncStatusOut(BaseModel):
    authorized: bool
    configured: bool
    awaiting_auth: bool
    auth_step: str | None


class AuthTextIn(BaseModel):
    text: str


class AuthResultOut(BaseModel):
    done: bool
    message: str
    next_step: str | None


@router.get("", response_model=SyncStatusOut)
async def get_status(
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> SyncStatusOut:
    us = await us_repo.get_or_create(session, owner_id)
    configured = tg_client.is_configured()
    authorized = (
        await tg_client.is_authorized(owner_id, us.telethon_session)
        if configured
        else False
    )
    raw = tg_client._pending_auth.get(owner_id)
    return SyncStatusOut(
        authorized=authorized,
        configured=configured,
        awaiting_auth=tg_client.is_awaiting_auth(owner_id),
        auth_step=_state_to_step(raw),
    )


@router.post("/start", response_model=AuthResultOut)
async def start_auth(
    owner_id: int = Depends(get_owner_id),
) -> AuthResultOut:
    message = await tg_client.start_auth(owner_id)
    return AuthResultOut(done=False, message=message, next_step="phone")


@router.post("/input", response_model=AuthResultOut)
async def submit_input(
    body: AuthTextIn,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> AuthResultOut:
    message, session_str = await tg_client.handle_auth_input(owner_id, body.text)
    if session_str:
        await us_repo.update_settings(session, owner_id, telethon_session=session_str)
        return AuthResultOut(done=True, message=message, next_step=None)
    raw = tg_client._pending_auth.get(owner_id)
    return AuthResultOut(done=False, message=message, next_step=_state_to_step(raw))


@router.delete("/session", status_code=204)
async def disconnect(
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> None:
    await tg_client.reset_session(owner_id)
    await us_repo.update_settings(session, owner_id, telethon_session=None)
