from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import get_owner_id
from bot.config_store import (
    get_brief_time,
    get_language,
    get_theme,
    get_timezone,
    is_brief_enabled,
    set_brief_enabled,
    set_brief_time,
    set_language,
    set_theme,
    set_timezone,
)

router = APIRouter()


class SettingsOut(BaseModel):
    language: str
    timezone: str
    brief_time: str
    brief_enabled: bool
    theme: str


class SettingsUpdate(BaseModel):
    language: str | None = None
    timezone: str | None = None
    brief_time: str | None = None
    brief_enabled: bool | None = None
    theme: str | None = None


@router.get("", response_model=SettingsOut)
async def get_settings(owner_id: int = Depends(get_owner_id)) -> SettingsOut:
    return SettingsOut(
        language=get_language(),
        timezone=get_timezone(),
        brief_time=get_brief_time(),
        brief_enabled=is_brief_enabled(),
        theme=get_theme(),
    )


@router.put("", response_model=SettingsOut)
async def update_settings(
    body: SettingsUpdate,
    owner_id: int = Depends(get_owner_id),
) -> SettingsOut:
    if body.language is not None:
        set_language(body.language)
    if body.timezone is not None:
        set_timezone(body.timezone)
    if body.brief_time is not None:
        set_brief_time(body.brief_time)
    if body.brief_enabled is not None:
        set_brief_enabled(body.brief_enabled)
    if body.theme is not None:
        set_theme(body.theme)
    return SettingsOut(
        language=get_language(),
        timezone=get_timezone(),
        brief_time=get_brief_time(),
        brief_enabled=is_brief_enabled(),
        theme=get_theme(),
    )
