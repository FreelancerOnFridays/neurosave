from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_owner_id
from api.dependencies import get_db
from db.repositories import user_settings as us_repo

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
async def get_settings(
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> SettingsOut:
    row = await us_repo.get_or_create(session, owner_id)
    return SettingsOut(
        language=row.language,
        timezone=row.timezone,
        brief_time=row.brief_time,
        brief_enabled=row.brief_enabled,
        theme=row.theme,
    )


@router.put("", response_model=SettingsOut)
async def update_settings(
    body: SettingsUpdate,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> SettingsOut:
    row = await us_repo.update_settings(
        session,
        owner_id,
        language=body.language,
        timezone=body.timezone,
        brief_time=body.brief_time,
        brief_enabled=body.brief_enabled,
        theme=body.theme,
    )
    return SettingsOut(
        language=row.language,
        timezone=row.timezone,
        brief_time=row.brief_time,
        brief_enabled=row.brief_enabled,
        theme=row.theme,
    )
