from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import Date, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_owner_id
from api.dependencies import get_db
from db.models import Contact, Task, TaskStatus
from db.repositories import messages as msg_repo
from db.repositories import tasks as task_repo
from db.repositories import user_settings as us_repo
from services.ai import generate_nudge_message, get_style_profile

router = APIRouter()


class TaskOut(BaseModel):
    id: int
    description: str
    assignee_name: str | None
    assignee_user_id: int | None
    assignee_username: str | None
    deadline: datetime | None
    reminder_time: datetime | None
    is_personal: bool
    status: str
    created_at: datetime
    chat_id: int
    team_label: str | None = None

    model_config = {"from_attributes": True}


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


class TaskCreate(BaseModel):
    description: str
    deadline: datetime | None = None
    reminder_time: datetime | None = None


class TaskReminderUpdate(BaseModel):
    reminder_time: datetime | None


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
    type: str | None = Query(default=None),
    has_reminder: bool | None = Query(default=None),
    filter_date: date | None = Query(default=None, alias="date"),
) -> list[TaskOut]:
    q = (
        select(Task)
        .where(Task.owner_id == owner_id)
        .order_by(Task.deadline.asc().nulls_last(), Task.created_at.asc())
    )
    if type == "personal":
        q = q.where(Task.is_personal == True)  # noqa: E712
    elif type == "delegated":
        q = q.where(Task.is_personal == False)  # noqa: E712
    if has_reminder is True:
        q = q.where(Task.reminder_time.isnot(None))
    elif has_reminder is False:
        q = q.where(Task.reminder_time.is_(None))
    if filter_date is not None:
        q = q.where(cast(Task.deadline, Date) == filter_date)
    result = await session.execute(q)
    tasks = list(result.scalars().all())

    assignee_ids = list({t.assignee_user_id for t in tasks if t.assignee_user_id and not t.is_personal})
    team_labels: dict[int, str] = {}
    if assignee_ids:
        cr = await session.execute(
            select(Contact.user_id, Contact.team_label).where(
                Contact.owner_id == owner_id,
                Contact.user_id.in_(assignee_ids),
                Contact.team_label.isnot(None),
            )
        )
        for uid, label in cr.all():
            if label:
                team_labels[uid] = label

    out: list[TaskOut] = []
    for t in tasks:
        task_out = TaskOut.model_validate(t)
        if t.assignee_user_id:
            task_out.team_label = team_labels.get(t.assignee_user_id)
        out.append(task_out)
    return out


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(
    body: TaskCreate,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> TaskOut:
    task = await task_repo.create_personal_task(
        session,
        owner_id=owner_id,
        description=body.description,
        deadline=body.deadline,
        reminder_time=body.reminder_time,
    )
    return TaskOut.model_validate(task)


@router.patch("/{task_id}/status", response_model=TaskOut)
async def update_task_status(
    task_id: int,
    body: TaskStatusUpdate,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> TaskOut:
    task = await session.get(Task, task_id)
    if task is None or task.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = body.status
    await session.flush()
    return TaskOut.model_validate(task)


@router.patch("/{task_id}/reminder", response_model=TaskOut)
async def update_task_reminder(
    task_id: int,
    body: TaskReminderUpdate,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> TaskOut:
    task = await session.get(Task, task_id)
    if task is None or task.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="Task not found")
    updated = await task_repo.set_reminder(session, task_id, body.reminder_time)
    if updated is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskOut.model_validate(updated)


@router.delete("/{task_id}/reminder", response_model=TaskOut)
async def delete_task_reminder(
    task_id: int,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> TaskOut:
    task = await session.get(Task, task_id)
    if task is None or task.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="Task not found")
    updated = await task_repo.set_reminder(session, task_id, None)
    if updated is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskOut.model_validate(updated)


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: int,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> None:
    task = await session.get(Task, task_id)
    if task is None or task.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="Task not found")
    await session.delete(task)
    await session.flush()


class NudgeBody(BaseModel):
    text: str | None = None


@router.get("/{task_id}/nudge/preview")
async def nudge_preview(
    task_id: int,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    task = await task_repo.get_task(session, task_id)
    if task is None or task.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="Task not found")

    us = await us_repo.get_or_create(session, owner_id)
    recent = await msg_repo.get_recent_owner_messages(session, owner_id)
    style = await get_style_profile(owner_id, [m.text for m in recent])

    try:
        nudge_text = await generate_nudge_message(
            description=task.description,
            assignee_name=task.assignee_name,
            deadline=task.deadline,
            language=us.language,
            style_profile=style,
        )
    except Exception:
        nudge_text = task.description

    return {"text": nudge_text}


@router.post("/{task_id}/nudge", status_code=204)
async def nudge_task(
    task_id: int,
    request: Request,
    body: NudgeBody = Body(default_factory=NudgeBody),
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> None:
    task = await task_repo.get_task(session, task_id)
    if task is None or task.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="Task not found")

    if body.text:
        nudge_text = body.text
    else:
        us = await us_repo.get_or_create(session, owner_id)
        recent = await msg_repo.get_recent_owner_messages(session, owner_id)
        style = await get_style_profile(owner_id, [m.text for m in recent])
        try:
            nudge_text = await generate_nudge_message(
                description=task.description,
                assignee_name=task.assignee_name,
                deadline=task.deadline,
                language=us.language,
                style_profile=style,
            )
        except Exception:
            nudge_text = task.description

    bot = request.app.state.bot
    await bot.send_message(
        chat_id=task.chat_id,
        text=nudge_text,
        business_connection_id=task.business_connection_id,
    )
