from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from beartype import beartype

from db.engine import session_factory
from db.repositories import tasks as task_repo
from db.repositories import user_settings as us_repo

logger = logging.getLogger(__name__)

_REMINDER_WINDOW_MINUTES = 60
_CHECK_INTERVAL_SECONDS = 15 * 60


@beartype
async def send_deadline_reminders(bot: Bot) -> None:
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(minutes=_REMINDER_WINDOW_MINUTES)
    async with session_factory() as session:
        owner_ids = await us_repo.get_all_owner_ids(session)
        for owner_id in owner_ids:
            due_tasks = await task_repo.get_open_tasks(session, owner_id=owner_id)
            upcoming = [
                t for t in due_tasks
                if t.deadline is not None and now <= t.deadline <= window_end
            ]
            if not upcoming:
                continue
            lines = ["⏰ <b>Задачи с дедлайном в ближайший час:</b>"]
            for task in upcoming:
                deadline_str = task.deadline.strftime("%H:%M") if task.deadline else ""
                assignee = f" ({task.assignee_name})" if task.assignee_name else ""
                lines.append(f"• {task.description}{assignee} — {deadline_str}")
            try:
                await bot.send_message(chat_id=owner_id, text="\n".join(lines), parse_mode="HTML")
            except Exception:
                logger.exception("Failed to send deadline reminder for user %d", owner_id)


@beartype
async def run_loop(bot: Bot) -> None:
    while True:
        await asyncio.sleep(_CHECK_INTERVAL_SECONDS)
        try:
            await send_deadline_reminders(bot)
        except Exception:
            logger.exception("Deadline reminder check failed")
