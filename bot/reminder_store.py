from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from aiogram import Bot

logger = logging.getLogger(__name__)

_bg_tasks: set[asyncio.Task[None]] = set()


@dataclass
class ActiveReminder:
    reminder_text: str
    reminder_time_iso: str
    event_time_iso: str | None
    lead_description: str | None = None
    task: asyncio.Task[None] | None = field(default=None, repr=False)


# owner_id → list of active reminders
_active_reminders: dict[int, list[ActiveReminder]] = {}


def get_active(owner_id: int) -> list[ActiveReminder]:
    return [r for r in _active_reminders.get(owner_id, []) if r.task is not None and not r.task.done()]


def delay_from_iso(iso: str | None) -> float:
    if not iso:
        return 0.0
    try:
        send_at = datetime.fromisoformat(iso)
        if send_at.tzinfo is None:
            send_at = send_at.replace(tzinfo=timezone.utc)
        return max(0.0, (send_at - datetime.now(timezone.utc)).total_seconds())
    except ValueError:
        logger.warning("Could not parse scheduled time: %s", iso)
        return 0.0


async def _reminder_task(
    bot: Bot,
    owner_id: int,
    reminder: ActiveReminder,
    delay_seconds: float,
) -> None:
    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)
    try:
        await bot.send_message(
            chat_id=owner_id,
            text=f"⏰ {reminder.reminder_text}",
        )
    except Exception:
        logger.exception("Failed to send reminder to owner %d", owner_id)
    finally:
        bucket = _active_reminders.get(owner_id, [])
        if reminder in bucket:
            bucket.remove(reminder)


def schedule_reminder(bot: Bot, owner_id: int, reminder: ActiveReminder, delay_seconds: float) -> None:
    task = asyncio.create_task(_reminder_task(bot, owner_id, reminder, delay_seconds))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    reminder.task = task
    _active_reminders.setdefault(owner_id, []).append(reminder)


def remove_reminder(owner_id: int, reminder: ActiveReminder) -> None:
    if reminder.task is not None:
        reminder.task.cancel()
    bucket = _active_reminders.get(owner_id, [])
    if reminder in bucket:
        bucket.remove(reminder)
