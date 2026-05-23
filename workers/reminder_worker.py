from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from beartype import beartype

from db.engine import session_factory
from db.repositories import ghost as ghost_repo
from db.repositories import tasks as task_repo
from db.repositories import user_settings as us_repo

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SECONDS = 60


def _format_reminder(
    description: str,
    language: str,
    deadline: "datetime | None" = None,
) -> str:
    if language == "ua":
        text = f"⏰ <b>Нагадування</b>\n{description}"
    elif language == "ru":
        text = f"⏰ <b>Напоминание</b>\n{description}"
    else:
        text = f"⏰ <b>Reminder</b>\n{description}"

    if deadline is not None:
        try:
            local = deadline.astimezone(ZoneInfo("Europe/Moscow"))
            time_str = local.strftime("%H:%M")
            date_str = local.strftime("%d.%m")
            today = datetime.now(ZoneInfo("Europe/Moscow")).strftime("%d.%m")
            if language == "ua":
                suffix = f"сьогодні о {time_str}" if date_str == today else f"{date_str} о {time_str}"
                label = "📅 Подія:"
            elif language == "ru":
                suffix = f"сегодня в {time_str}" if date_str == today else f"{date_str} в {time_str}"
                label = "📅 Событие:"
            else:
                suffix = f"today at {time_str}" if date_str == today else f"{date_str} at {time_str}"
                label = "📅 Event:"
            text += f"\n{label} {suffix}"
        except Exception:
            pass

    if language == "ua":
        action_line = "Виберіть дію:"
    elif language == "ru":
        action_line = "Выберите действие:"
    else:
        action_line = "Choose action:"
    text += f"\n\n{action_line}"
    return text


def _reminder_keyboard(task_id: int, language: str) -> InlineKeyboardMarkup:
    if language == "ua":
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Виконано", callback_data=f"reminder_done:{task_id}"),
                InlineKeyboardButton(text="⏰ Пізніше", callback_data=f"reminder_snooze:{task_id}"),
            ],
            [
                InlineKeyboardButton(text="❌ Скасувати завдання", callback_data=f"reminder_cancel:{task_id}"),
            ],
        ])
    if language == "ru":
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Выполнено", callback_data=f"reminder_done:{task_id}"),
                InlineKeyboardButton(text="⏰ Позже", callback_data=f"reminder_snooze:{task_id}"),
            ],
            [
                InlineKeyboardButton(text="❌ Отменить задачу", callback_data=f"reminder_cancel:{task_id}"),
            ],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Done", callback_data=f"reminder_done:{task_id}"),
            InlineKeyboardButton(text="⏰ Later", callback_data=f"reminder_snooze:{task_id}"),
        ],
        [
            InlineKeyboardButton(text="❌ Cancel task", callback_data=f"reminder_cancel:{task_id}"),
        ],
    ])


@beartype
async def fire_pending_reminders(bot: Bot) -> None:
    async with session_factory() as session:
        owner_ids = await us_repo.get_all_owner_ids(session)
        for owner_id in owner_ids:
            us = await us_repo.get_or_create(session, owner_id)
            pending = await task_repo.get_tasks_with_pending_reminders(session, owner_id=owner_id)
            for task in pending:
                try:
                    text = _format_reminder(task.description, us.language, task.deadline)
                    await bot.send_message(
                        chat_id=owner_id,
                        text=text,
                        parse_mode="HTML",
                        reply_markup=_reminder_keyboard(task.id, us.language),
                    )
                    await task_repo.mark_reminder_fired(session, task.id)
                except Exception:
                    logger.exception("Failed to fire reminder for task %d", task.id)
        await session.commit()


@beartype
async def fire_ghost_auto_offs(bot: Bot) -> None:
    async with session_factory() as session:
        pending = await ghost_repo.get_pending_auto_offs(session)
        for gs in pending:
            try:
                gs.is_active = False
                gs.auto_off_at = None
                await session.flush()
                await bot.send_message(chat_id=gs.owner_id, text="👻 Ghost Mode автоматически выключен.")
            except Exception:
                logger.exception("Failed to auto-deactivate ghost for owner %d", gs.owner_id)
        if pending:
            await session.commit()


@beartype
async def run_loop(bot: Bot) -> None:
    while True:
        await asyncio.sleep(_CHECK_INTERVAL_SECONDS)
        try:
            await fire_pending_reminders(bot)
        except Exception:
            logger.exception("Reminder worker check failed")
        try:
            await fire_ghost_auto_offs(bot)
        except Exception:
            logger.exception("Ghost auto-off check failed")
