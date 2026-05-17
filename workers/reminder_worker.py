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


def _format_reminder(description: str, language: str, reminder_time: "datetime | None" = None) -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    if language == "ru":
        text = f"⏰ <b>Напоминание</b>\n{description}"
    else:
        text = f"⏰ <b>Reminder</b>\n{description}"

    if reminder_time is not None:
        try:
            local = reminder_time.astimezone(ZoneInfo("Europe/Moscow"))
            time_str = local.strftime("%H:%M")
            date_str = local.strftime("%d.%m")
            today = datetime.now(ZoneInfo("Europe/Moscow")).strftime("%d.%m")
            if date_str == today:
                suffix = f"сегодня в {time_str}" if language == "ru" else f"today at {time_str}"
            else:
                suffix = f"{date_str} в {time_str}" if language == "ru" else f"{date_str} at {time_str}"
            text += f"\n📅 {suffix}"
        except Exception:
            pass
    return text


@beartype
async def fire_pending_reminders(bot: Bot) -> None:
    async with session_factory() as session:
        owner_ids = await us_repo.get_all_owner_ids(session)
        for owner_id in owner_ids:
            us = await us_repo.get_or_create(session, owner_id)
            pending = await task_repo.get_tasks_with_pending_reminders(session, owner_id=owner_id)
            for task in pending:
                try:
                    text = _format_reminder(task.description, us.language, task.reminder_time)
                    await bot.send_message(chat_id=owner_id, text=text, parse_mode="HTML")
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
