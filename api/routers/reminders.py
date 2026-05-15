from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_owner_id
from api.dependencies import get_db
from db.models import Task
from db.repositories import tasks as task_repo

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


def _task_to_out(task_id: int, description: str, reminder_time: datetime | None, deadline: datetime | None) -> ReminderOut:
    return ReminderOut(
        id=str(task_id),
        reminder_text=description,
        reminder_time_iso=reminder_time.isoformat() if reminder_time else "",
        event_time_iso=deadline.isoformat() if deadline else None,
        lead_description=None,
    )


@router.get("", response_model=list[ReminderOut])
async def list_reminders(
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> list[ReminderOut]:
    tasks = await task_repo.get_open_tasks(session, owner_id, is_personal=True)
    return [_task_to_out(t.id, t.description, t.reminder_time, t.deadline) for t in tasks if t.reminder_time]


@router.post("", response_model=ReminderOut, status_code=201)
async def create_reminder(
    body: ReminderCreate,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> ReminderOut:
    reminder_time: datetime | None = None
    try:
        reminder_time = datetime.fromisoformat(body.reminder_time_iso)
        if reminder_time.tzinfo is None:
            reminder_time = reminder_time.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    deadline: datetime | None = None
    if body.event_time_iso:
        try:
            deadline = datetime.fromisoformat(body.event_time_iso)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    task = await task_repo.create_personal_task(
        session,
        owner_id=owner_id,
        description=body.reminder_text,
        deadline=deadline,
        reminder_time=reminder_time,
    )
    return _task_to_out(task.id, task.description, task.reminder_time, task.deadline)


@router.delete("/{reminder_id}", status_code=204)
async def delete_reminder(
    reminder_id: str,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> None:
    try:
        task_id = int(reminder_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Reminder not found")
    task = await session.get(Task, task_id)
    if task is None or task.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="Reminder not found")
    await task_repo.delete_task(session, task_id)
