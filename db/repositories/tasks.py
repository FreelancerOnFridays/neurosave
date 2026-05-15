from __future__ import annotations

from datetime import datetime, timezone

from beartype import beartype
from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Task, TaskStatus


@beartype
async def create_task(
    session: AsyncSession,
    *,
    owner_id: int,
    chat_id: int,
    message_id: int,
    description: str,
    assignee_name: str | None = None,
    assignee_user_id: int | None = None,
    assignee_username: str | None = None,
    deadline: datetime | None = None,
    business_connection_id: str | None = None,
) -> Task:
    task = Task(
        owner_id=owner_id,
        chat_id=chat_id,
        message_id=message_id,
        description=description,
        assignee_name=assignee_name,
        assignee_user_id=assignee_user_id,
        assignee_username=assignee_username,
        deadline=deadline,
        business_connection_id=business_connection_id,
    )
    session.add(task)
    await session.flush()
    return task


@beartype
async def create_personal_task(
    session: AsyncSession,
    *,
    owner_id: int,
    description: str,
    deadline: datetime | None = None,
    reminder_time: datetime | None = None,
) -> Task:
    task = Task(
        owner_id=owner_id,
        chat_id=owner_id,
        message_id=0,
        description=description,
        is_personal=True,
        deadline=deadline,
        reminder_time=reminder_time,
    )
    session.add(task)
    await session.flush()
    return task


@beartype
async def get_open_tasks(
    session: AsyncSession,
    owner_id: int,
    is_personal: bool | None = None,
) -> list[Task]:
    q = select(Task).where(Task.owner_id == owner_id, Task.status == TaskStatus.open)
    if is_personal is not None:
        q = q.where(Task.is_personal == is_personal)
    q = q.order_by(Task.deadline.asc().nulls_last(), Task.created_at.asc())
    result = await session.execute(q)
    return list(result.scalars().all())


@beartype
async def get_today_tasks(
    session: AsyncSession,
    owner_id: int,
    is_personal: bool | None = None,
) -> list[Task]:
    today = func.current_date()
    q = select(Task).where(
        Task.owner_id == owner_id,
        Task.status == TaskStatus.open,
        cast(Task.deadline, Date) == today,
    )
    if is_personal is not None:
        q = q.where(Task.is_personal == is_personal)
    q = q.order_by(Task.deadline.asc().nulls_last(), Task.created_at.asc())
    result = await session.execute(q)
    return list(result.scalars().all())


@beartype
async def get_tasks_due_today(session: AsyncSession, owner_id: int) -> list[Task]:
    today = func.current_date()
    result = await session.execute(
        select(Task).where(
            Task.owner_id == owner_id,
            Task.status == TaskStatus.open,
            cast(Task.deadline, Date) == today,
        )
    )
    return list(result.scalars().all())


@beartype
async def get_overdue_tasks(session: AsyncSession, owner_id: int) -> list[Task]:
    result = await session.execute(
        select(Task).where(
            Task.owner_id == owner_id,
            Task.status == TaskStatus.open,
            Task.deadline < func.now(),
        )
    )
    return list(result.scalars().all())


@beartype
async def get_tasks_with_pending_reminders(
    session: AsyncSession, owner_id: int
) -> list[Task]:
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(Task).where(
            Task.owner_id == owner_id,
            Task.status == TaskStatus.open,
            Task.reminder_time.isnot(None),
            Task.reminder_time <= now,
            Task.reminder_fired == False,  # noqa: E712
        )
    )
    return list(result.scalars().all())


@beartype
async def set_reminder(
    session: AsyncSession,
    task_id: int,
    reminder_time: datetime | None,
) -> Task | None:
    task = await session.get(Task, task_id)
    if task is None:
        return None
    task.reminder_time = reminder_time
    task.reminder_fired = False
    return task


@beartype
async def mark_reminder_fired(session: AsyncSession, task_id: int) -> None:
    task = await session.get(Task, task_id)
    if task is not None:
        task.reminder_fired = True


@beartype
async def mark_task_done(session: AsyncSession, task_id: int) -> Task | None:
    task = await session.get(Task, task_id)
    if task:
        task.status = TaskStatus.done
    return task


@beartype
async def get_task(session: AsyncSession, task_id: int) -> Task | None:
    return await session.get(Task, task_id)


@beartype
async def delete_task(session: AsyncSession, task_id: int) -> bool:
    task = await session.get(Task, task_id)
    if task is None:
        return False
    await session.delete(task)
    return True
