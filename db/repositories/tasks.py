from __future__ import annotations

from datetime import datetime

from beartype import beartype
from sqlalchemy import func, select
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
        deadline=deadline,
        business_connection_id=business_connection_id,
    )
    session.add(task)
    await session.flush()
    return task


@beartype
async def get_open_tasks(session: AsyncSession, owner_id: int) -> list[Task]:
    result = await session.execute(
        select(Task)
        .where(Task.owner_id == owner_id, Task.status == TaskStatus.open)
        .order_by(Task.deadline.asc().nulls_last(), Task.created_at.asc())
    )
    return list(result.scalars().all())


@beartype
async def get_tasks_due_today(session: AsyncSession, owner_id: int) -> list[Task]:
    from sqlalchemy import cast, func, Date

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
