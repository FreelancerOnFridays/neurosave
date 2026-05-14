from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from beartype import beartype

from bot.config_store import get_language, get_timezone
from bot.reminder_store import ActiveReminder, get_active


def reminder_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:8]


def _fmt_hm(iso: str, tz_name: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(ZoneInfo(tz_name))
        return f"{local.hour:02d}:{local.strftime('%M')}"
    except Exception:
        return ""


def _is_today(iso: str, tz_name: str) -> bool:
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo(tz_name)).date() == datetime.now(ZoneInfo(tz_name)).date()
    except Exception:
        return False


@beartype
def build_today_schedule(owner_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    lang = get_language()
    tz_name = get_timezone()

    today: list[ActiveReminder] = sorted(
        [r for r in get_active(owner_id) if _is_today(r.reminder_time_iso, tz_name)],
        key=lambda r: r.reminder_time_iso or "",
    )

    if not today:
        msg = "📅 На сегодня задач нет." if lang == "ru" else "📅 Nothing scheduled for today."
        return msg, None

    header = "📅 <b>Расписание на сегодня:</b>" if lang == "ru" else "📅 <b>Today's schedule:</b>"
    lines = [header]
    builder = InlineKeyboardBuilder()

    for r in today:
        time_str = _fmt_hm(r.reminder_time_iso, tz_name) if r.reminder_time_iso else ""
        entry = f"• {r.reminder_text}"
        if time_str:
            entry += f" — <b>{time_str}</b>"
        lines.append(entry)
        btn_label = f"✅  {r.reminder_text[:28]}"
        builder.button(text=btn_label, callback_data=f"sched_done:{reminder_hash(r.reminder_text)}")

    builder.adjust(1)
    hint = "\nНажмите кнопку, чтобы отметить выполненным." if lang == "ru" else "\nTap to mark as done."
    lines.append(f"\n<i>{hint.strip()}</i>")
    return "\n".join(lines), builder.as_markup()
