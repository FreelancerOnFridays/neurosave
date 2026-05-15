from __future__ import annotations

import asyncio
import logging
from zoneinfo import ZoneInfo

from aiogram import Bot
from beartype import beartype

from bot.config_store import get_language, get_timezone
from config import settings
from db.engine import session_factory
from db.repositories import tasks as task_repo

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SECONDS = 60


def _format_reminder(description: str, language: str) -> str:
    if language == "ru":
        return f"⏰ Напоминание: {description}"
    return f"⏰ Reminder: {description}"


@beartype
async def fire_pending_reminders(bot: Bot) -> None:
    async with session_factory() as session:
        pending = await task_repo.get_tasks_with_pending_reminders(
            session, owner_id=settings.owner_chat_id
        )
        if not pending:
            return
        lang = get_language()
        for task in pending:
            try:
                text = _format_reminder(task.description, lang)
                await bot.send_message(chat_id=settings.owner_chat_id, text=text)
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
