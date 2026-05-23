from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_owner_id
from api.dependencies import get_db
from db.models import InquiryCategory
from db.repositories import ghost as ghost_repo
from db.repositories import user_settings as us_repo
from services.ai import generate_away_message

router = APIRouter()


class GhostStatusOut(BaseModel):
    is_active: bool
    away_message: str | None
    activated_at: datetime | None
    silent_mode: bool
    auto_off_at: datetime | None = None
    excluded_contact_ids: list[int] = []
    excluded_labels: list[str] = []


class GhostUpdate(BaseModel):
    is_active: bool
    away_message: str | None = None
    silent_mode: bool = False


class GhostSilentUpdate(BaseModel):
    silent_mode: bool


class GhostAutoOffUpdate(BaseModel):
    auto_off_at: datetime | None = None


class GhostExclusionsUpdate(BaseModel):
    contact_ids: list[int] = []
    labels: list[str] = []


class InquiryOut(BaseModel):
    id: int
    caller_id: int
    caller_name: str | None
    caller_username: str | None
    summary: str | None
    category: str | None
    created_at: datetime
    caller_labels: list[str] = []

    model_config = {"from_attributes": True}


class GenerateReplyOut(BaseModel):
    text: str


def _status_out(gs: object | None) -> GhostStatusOut:
    from db.models import GhostSession as _GS
    if gs is None or not isinstance(gs, _GS):
        return GhostStatusOut(is_active=False, away_message=None, activated_at=None, silent_mode=False)
    return GhostStatusOut(
        is_active=gs.is_active,
        away_message=gs.away_message,
        activated_at=gs.activated_at,
        silent_mode=gs.silent_mode,
        auto_off_at=gs.auto_off_at,
        excluded_contact_ids=gs.excluded_contact_ids or [],
        excluded_labels=gs.excluded_labels or [],
    )


@router.get("", response_model=GhostStatusOut)
async def get_ghost(
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> GhostStatusOut:
    gs = await ghost_repo.get_session(session, owner_id)
    return _status_out(gs)


@router.put("", response_model=GhostStatusOut)
async def update_ghost(
    body: GhostUpdate,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> GhostStatusOut:
    gs = await ghost_repo.set_active(
        session,
        owner_id=owner_id,
        active=body.is_active,
        away_message=body.away_message,
        silent_mode=body.silent_mode,
    )
    return _status_out(gs)


@router.patch("/silent", response_model=GhostStatusOut)
async def update_silent_mode(
    body: GhostSilentUpdate,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> GhostStatusOut:
    gs = await ghost_repo.set_silent_mode(session, owner_id, body.silent_mode)
    if gs is None:
        raise HTTPException(status_code=404, detail="No ghost session found")
    return _status_out(gs)


@router.patch("/auto-off", response_model=GhostStatusOut)
async def update_auto_off(
    body: GhostAutoOffUpdate,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> GhostStatusOut:
    gs = await ghost_repo.set_auto_off(session, owner_id, body.auto_off_at)
    if gs is None:
        raise HTTPException(status_code=404, detail="No ghost session found")
    return _status_out(gs)


@router.patch("/exclusions", response_model=GhostStatusOut)
async def update_exclusions(
    body: GhostExclusionsUpdate,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> GhostStatusOut:
    gs = await ghost_repo.set_exclusions(session, owner_id, body.contact_ids, body.labels)
    return _status_out(gs)


@router.post("/generate-reply", response_model=GenerateReplyOut)
async def generate_reply(
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> GenerateReplyOut:
    us = await us_repo.get_or_create(session, owner_id)
    text = await generate_away_message(us.language)
    return GenerateReplyOut(text=text)


@router.get("/inquiries", response_model=list[InquiryOut])
async def get_inquiries(
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> list[InquiryOut]:
    from db.repositories import contacts as contact_repo

    gs = await ghost_repo.get_session(session, owner_id)
    if gs is None or gs.activated_at is None:
        return []
    inquiries = await ghost_repo.get_inquiries_since(session, owner_id, gs.activated_at)
    result: list[InquiryOut] = []
    for i in inquiries:
        labels: list[str] = []
        if i.caller_id:
            contact = await contact_repo.get_contact(session, owner_id, i.caller_id)
            if contact:
                labels = contact.labels or []
        result.append(InquiryOut(
            id=i.id,
            caller_id=i.caller_id,
            caller_name=i.caller_name,
            caller_username=i.caller_username,
            summary=i.summary,
            category=i.category.value if i.category else None,
            created_at=i.created_at,
            caller_labels=labels,
        ))
    return result
