from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from beartype import beartype
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config_store import get_language, get_timezone
from db.models import Task
from db.repositories import tasks as task_repo


def _task_id_str(task_id: int) -> str:
    return str(task_id)


def _fmt_hm(dt: datetime, tz_name: str) -> str:
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(ZoneInfo(tz_name))
        return f"{local.hour:02d}:{local.strftime('%M')}"
    except Exception:
        return ""


def _is_today(dt: datetime | None, tz_name: str) -> bool:
    if dt is None:
        return False
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo(tz_name)).date() == datetime.now(ZoneInfo(tz_name)).date()
    except Exception:
        return False


@beartype
async def build_today_schedule(
    owner_id: int, session: AsyncSession
) -> tuple[str, InlineKeyboardMarkup | None]:
    lang = get_language()
    tz_name = get_timezone()

    personal_tasks = await task_repo.get_today_tasks(session, owner_id, is_personal=True)
    today: list[Task] = sorted(
        personal_tasks,
        key=lambda t: (t.reminder_time or t.deadline or datetime.max.replace(tzinfo=timezone.utc)),
    )

    if not today:
        msg = "📅 На сегодня задач нет." if lang == "ru" else "📅 Nothing scheduled for today."
        return msg, None

    header = "📅 <b>Расписание на сегодня:</b>" if lang == "ru" else "📅 <b>Today's schedule:</b>"
    lines = [header]
    builder = InlineKeyboardBuilder()

    for t in today:
        time_dt = t.reminder_time or t.deadline
        time_str = _fmt_hm(time_dt, tz_name) if time_dt else ""
        entry = f"• {t.description}"
        if time_str:
            entry += f" — <b>{time_str}</b>"
        lines.append(entry)
        btn_label = f"✅  {t.description[:28]}"
        builder.button(text=btn_label, callback_data=f"sched_done:{t.id}")

    builder.adjust(1)
    hint = "\nНажмите кнопку, чтобы отметить выполненным." if lang == "ru" else "\nTap to mark as done."
    lines.append(f"\n<i>{hint.strip()}</i>")
    return "\n".join(lines), builder.as_markup()
