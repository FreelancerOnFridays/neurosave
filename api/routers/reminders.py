from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from beartype import beartype
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.auth import get_owner_id
from bot.reminder_store import (
    ActiveReminder,
    delay_from_iso,
    get_active,
    remove_reminder,
    schedule_reminder,
)

router = APIRouter()


class ReminderOut(BaseModel):
    id: str
    reminder_text: str
    reminder_time_iso: str
    event_time_iso: str | None
    lead_description: str | None


class ReminderCreate(BaseModel):
    reminder_text: str
    reminder_time_iso: str
    event_time_iso: str | None = None
    lead_description: str | None = None


def _reminder_id(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:8]


def _to_out(r: ActiveReminder) -> ReminderOut:
    return ReminderOut(
        id=_reminder_id(r.reminder_text),
        reminder_text=r.reminder_text,
        reminder_time_iso=r.reminder_time_iso,
        event_time_iso=r.event_time_iso,
        lead_description=r.lead_description,
    )


@router.get("", response_model=list[ReminderOut])
async def list_reminders(owner_id: int = Depends(get_owner_id)) -> list[ReminderOut]:
    return [_to_out(r) for r in get_active(owner_id)]


@router.post("", response_model=ReminderOut, status_code=201)
async def create_reminder(
    body: ReminderCreate,
    request: Request,
    owner_id: int = Depends(get_owner_id),
) -> ReminderOut:
    bot = request.app.state.bot
    reminder = ActiveReminder(
        reminder_text=body.reminder_text,
        reminder_time_iso=body.reminder_time_iso,
        event_time_iso=body.event_time_iso,
        lead_description=body.lead_description,
    )
    delay = delay_from_iso(body.reminder_time_iso)
    schedule_reminder(bot, owner_id, reminder, delay)
    return _to_out(reminder)


@router.delete("/{hash_id}", status_code=204)
async def delete_reminder(
    hash_id: str,
    owner_id: int = Depends(get_owner_id),
) -> None:
    active = get_active(owner_id)
    target = next((r for r in active if _reminder_id(r.reminder_text) == hash_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    remove_reminder(owner_id, target)
