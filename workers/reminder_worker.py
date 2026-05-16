from __future__ import annotations

import asyncio
import logging
from zoneinfo import ZoneInfo

from aiogram import Bot
from beartype import beartype

from db.engine import session_factory
from db.repositories import tasks as task_repo
from db.repositories import user_settings as us_repo

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SECONDS = 60


def _format_reminder(description: str, language: str) -> str:
    if language == "ru":
        return f"⏰ Напоминание: {description}"
    return f"⏰ Reminder: {description}"


@beartype
async def fire_pending_reminders(bot: Bot) -> None:
    async with session_factory() as session:
        owner_ids = await us_repo.get_all_owner_ids(session)
        for owner_id in owner_ids:
            us = await us_repo.get_or_create(session, owner_id)
            pending = await task_repo.get_tasks_with_pending_reminders(session, owner_id=owner_id)
            for task in pending:
                try:
                    text = _format_reminder(task.description, us.language)
                    await bot.send_message(chat_id=owner_id, text=text)
                    await task_repo.mark_reminder_fired(session, task.id)
                except Exception:
                    logger.exception("Failed to fire reminder for task %d", task.id)
        await session.commit()


@beartype
async def run_loop(bot: Bot) -> None:
    while True:
        await asyncio.sleep(_CHECK_INTERVAL_SECONDS)
        try:
            await fire_pending_reminders(bot)
        except Exception:
            logger.exception("Reminder worker check failed")
