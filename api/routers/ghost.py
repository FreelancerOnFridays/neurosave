from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_owner_id
from api.dependencies import get_db
from db.models import InquiryCategory
from db.repositories import ghost as ghost_repo

router = APIRouter()


class GhostStatusOut(BaseModel):
    is_active: bool
    away_message: str | None
    activated_at: datetime | None


class GhostUpdate(BaseModel):
    is_active: bool
    away_message: str | None = None


class InquiryOut(BaseModel):
    id: int
    caller_id: int
    caller_name: str | None
    caller_username: str | None
    summary: str | None
    category: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=GhostStatusOut)
async def get_ghost(
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> GhostStatusOut:
    gs = await ghost_repo.get_session(session, owner_id)
    if gs is None:
        return GhostStatusOut(is_active=False, away_message=None, activated_at=None)
    return GhostStatusOut(
        is_active=gs.is_active,
        away_message=gs.away_message,
        activated_at=gs.activated_at,
    )


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
    )
    return GhostStatusOut(
        is_active=gs.is_active,
        away_message=gs.away_message,
        activated_at=gs.activated_at,
    )


@router.get("/inquiries", response_model=list[InquiryOut])
async def get_inquiries(
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> list[InquiryOut]:
    gs = await ghost_repo.get_session(session, owner_id)
    if gs is None or gs.activated_at is None:
        return []
    inquiries = await ghost_repo.get_inquiries_since(session, owner_id, gs.activated_at)
    return [
        InquiryOut(
            id=i.id,
            caller_id=i.caller_id,
            caller_name=i.caller_name,
            caller_username=i.caller_username,
            summary=i.summary,
            category=i.category.value if i.category else None,
            created_at=i.created_at,
        )
        for i in inquiries
    ]
