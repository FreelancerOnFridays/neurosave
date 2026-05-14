from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_owner_id
from api.dependencies import get_db
from bot.config_store import get_language
from config import settings
from db.models import Task, TaskStatus
from db.repositories import messages as msg_repo
from db.repositories import tasks as task_repo
from services.ai import generate_nudge_message, get_style_profile

router = APIRouter()


class TaskOut(BaseModel):
    id: int
    description: str
    assignee_name: str | None
    assignee_user_id: int | None
    assignee_username: str | None
    deadline: datetime | None
    status: str
    created_at: datetime
    chat_id: int

    model_config = {"from_attributes": True}


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> list[TaskOut]:
    result = await session.execute(
        select(Task)
        .where(Task.owner_id == owner_id)
        .order_by(Task.deadline.asc().nulls_last(), Task.created_at.asc())
    )
    tasks = list(result.scalars().all())
    return [TaskOut.model_validate(t) for t in tasks]


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


@router.post("/{task_id}/nudge", status_code=204)
async def nudge_task(
    task_id: int,
    request: Request,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> None:
    task = await task_repo.get_task(session, task_id)
    if task is None or task.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="Task not found")

    recent = await msg_repo.get_recent_owner_messages(session, settings.owner_chat_id)
    style = await get_style_profile(settings.owner_chat_id, [m.text for m in recent])

    try:
        nudge_text = await generate_nudge_message(
            description=task.description,
            assignee_name=task.assignee_name,
            deadline=task.deadline,
            language=get_language(),
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
