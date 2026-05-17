from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TypedDict
from zoneinfo import ZoneInfo

from aiogram import Bot
from beartype import beartype

from db.engine import session_factory
from db.models import InquiryCategory
from db.repositories import ghost as ghost_repo
from db.repositories import messages as msg_repo
from db.repositories import tasks as task_repo
from db.repositories import user_settings as us_repo
from services.ai import generate_agenda_recommendation

logger = logging.getLogger(__name__)

_CHECK_INTERVAL = 60  # seconds

_MONTH_RU = ["", "янв", "фев", "мар", "апр", "май", "июн",
             "июл", "авг", "сен", "окт", "ноя", "дек"]

_CATEGORY_LABELS: dict[InquiryCategory, str] = {
    InquiryCategory.urgent: "🔴 Срочно",
    InquiryCategory.team: "👥 Команда",
    InquiryCategory.sales: "💼 Продажи",
    InquiryCategory.spam: "🗑 Спам",
}


class _SenderInfo(TypedDict):
    name: str | None
    count: int
    last: str


def _fmt_time(dt: datetime, tz_name: str) -> str:
    try:
        local = dt.astimezone(ZoneInfo(tz_name))
        return f"{local.hour:02d}:{local.strftime('%M')}"
    except Exception:
        return dt.strftime("%H:%M")


def _fmt_time_iso(iso: str, tz_name: str, lang: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(ZoneInfo(tz_name))
        hour = str(local.hour)
        minute = local.strftime("%M")
        if lang == "ru":
            return f"{hour}:{minute}"
        return f"{hour}:{minute}"
    except Exception:
        return iso


def _days_ago(dt: datetime, lang: str) -> str:
    days = max(0, (datetime.now(timezone.utc) - dt).days)
    if days == 0:
        return "сегодня" if lang == "ru" else "today"
    if days == 1:
        return "вчера" if lang == "ru" else "yesterday"
    return f"{days} дн. назад" if lang == "ru" else f"{days}d ago"


def _is_today_iso(iso: str, tz_name: str) -> bool:
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(ZoneInfo(tz_name))
        return local.date() == datetime.now(ZoneInfo(tz_name)).date()
    except Exception:
        return False


_last_brief_dates: dict[int, str] = {}


async def build_and_send_brief(bot: Bot, user_id: int) -> None:
    owner_id = user_id
    async with session_factory() as _us_sess:
        us = await us_repo.get_or_create(_us_sess, owner_id)
        lang = us.language
        tz_name = us.timezone
    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)
    midnight_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    midnight_utc = midnight_local.astimezone(timezone.utc)

    async with session_factory() as session:
        delegated_today = await task_repo.get_today_tasks(session, owner_id, is_personal=False)
        my_tasks = await task_repo.get_today_tasks(session, owner_id, is_personal=True)
        overdue = await task_repo.get_overdue_tasks(session, owner_id)
        night_msgs = await msg_repo.get_messages_in_range(
            session, owner_id, since=midnight_utc, until=datetime.now(timezone.utc)
        )
        ghost_inquiries = await ghost_repo.get_inquiries_since(session, owner_id, since=midnight_utc)

    # Group raw incoming messages by sender (fallback when ghost was off)
    incoming_by_sender: dict[int, _SenderInfo] = {}
    for m in night_msgs:
        if m.sender_id is not None and m.sender_id != owner_id:
            if m.sender_id not in incoming_by_sender:
                incoming_by_sender[m.sender_id] = _SenderInfo(name=m.sender_name, count=0, last="")
            incoming_by_sender[m.sender_id]["count"] += 1
            incoming_by_sender[m.sender_id]["last"] = m.text[:80]

    if lang == "ru":
        date_str = f"{now_local.day} {_MONTH_RU[now_local.month]}"
        lines: list[str] = [f"☕ <b>Доброе утро! {date_str}</b>"]
    else:
        date_str = now_local.strftime("%b %d")
        lines = [f"☕ <b>Good morning! {date_str}</b>"]

    # ── Section 1: Owner's personal tasks ────────────────────────────────────
    if my_tasks:
        lines.append("")
        lines.append("✅ <b>Ваши задачи на сегодня</b>" if lang == "ru" else "✅ <b>Your tasks today</b>")
        for task in my_tasks:
            time_dt = task.reminder_time or task.deadline
            time_str = _fmt_time(time_dt, tz_name) if time_dt else ""
            lines.append(f"• {task.description}" + (f"  <i>{time_str}</i>" if time_str else ""))

    # ── Section 2: Delegated tasks due today (assigned to others) ────────────
    if delegated_today:
        lines.append("")
        lines.append("📌 <b>Делегировано сегодня</b>" if lang == "ru" else "📌 <b>Delegated today</b>")
        for t in delegated_today:
            time_str = _fmt_time(t.deadline, tz_name) if t.deadline else ""
            assignee = f" · {t.assignee_name}" if t.assignee_name else ""
            lines.append(f"• {t.description}{assignee}" + (f"  <i>{time_str}</i>" if time_str else ""))

    # ── Section 3: Overdue delegated tasks ───────────────────────────────────
    today_ids = {t.id for t in delegated_today}
    truly_overdue = [t for t in overdue if t.id not in today_ids]
    if truly_overdue:
        lines.append("")
        lines.append("⚠️ <b>Просрочено</b>" if lang == "ru" else "⚠️ <b>Overdue</b>")
        for t in truly_overdue[:5]:
            when = _days_ago(t.deadline, lang) if t.deadline else "?"
            assignee = f" · {t.assignee_name}" if t.assignee_name else ""
            lines.append(f"• {t.description}{assignee}  <i>{when}</i>")
        if len(truly_overdue) > 5:
            extra = len(truly_overdue) - 5
            lines.append(f"<i>+ ещё {extra}</i>" if lang == "ru" else f"<i>+ {extra} more</i>")

    # ── Section 4: Night digest ───────────────────────────────────────────────
    if ghost_inquiries:
        lines.append("")
        lines.append("🌙 <b>Ночной дайджест</b>" if lang == "ru" else "🌙 <b>Night digest</b>")
        for inq in ghost_inquiries[:8]:
            name = inq.caller_name or f"ID {inq.caller_id}"
            summary = inq.summary or "—"
            cat_label = _CATEGORY_LABELS.get(inq.category, "") if inq.category else ""
            prefix = f"{cat_label} " if cat_label else ""
            lines.append(f"• {prefix}<b>{name}</b>  {summary}")
    elif incoming_by_sender:
        lines.append("")
        lines.append("🌙 <b>Ночной дайджест</b>" if lang == "ru" else "🌙 <b>Night digest</b>")
        for sender_id, info in list(incoming_by_sender.items())[:8]:
            name = info["name"] or f"ID {sender_id}"
            count = info["count"]
            snippet = info["last"]
            if len(snippet) > 60:
                snippet = snippet[:60] + "…"
            count_label = f"{count} сообщ." if lang == "ru" else f"{count} msg"
            lines.append(f"• <b>{name}</b> ({count_label})  {snippet}")

    # ── Section 5: AI agenda recommendation ──────────────────────────────────
    ctx_parts: list[str] = []
    if my_tasks:
        ctx_parts.append("Owner's own tasks today: " + "; ".join(t.description for t in my_tasks))
    if delegated_today:
        ctx_parts.append("Delegated tasks due today: " + "; ".join(
            f"{t.description} ({t.assignee_name or 'no assignee'})" for t in delegated_today
        ))
    if truly_overdue:
        ctx_parts.append("Overdue delegated: " + "; ".join(
            f"{t.description} ({t.assignee_name or 'no assignee'})" for t in truly_overdue[:3]
        ))
    if ghost_inquiries:
        urgent = [i for i in ghost_inquiries if i.category == InquiryCategory.urgent]
        if urgent:
            ctx_parts.append("Urgent night messages: " + "; ".join(
                f"{i.caller_name or 'someone'}: {i.summary}" for i in urgent
            ))
    elif incoming_by_sender:
        ctx_parts.append("Incoming messages from: " + ", ".join(
            (info["name"] or f"ID {sid}") for sid, info in list(incoming_by_sender.items())[:3]
        ))

    if ctx_parts:
        try:
            agenda = await generate_agenda_recommendation("\n".join(ctx_parts), language=lang)
            if agenda:
                lines.append("")
                lines.append("📋 <b>Рекомендация</b>" if lang == "ru" else "📋 <b>Agenda</b>")
                lines.append(agenda)
        except Exception:
            logger.warning("generate_agenda_recommendation failed", exc_info=True)

    await bot.send_message(chat_id=owner_id, text="\n".join(lines), parse_mode="HTML")
    logger.info("Morning brief sent to owner %d", owner_id)


@beartype
async def run_loop(bot: Bot) -> None:
    while True:
        await asyncio.sleep(_CHECK_INTERVAL)
        try:
            async with session_factory() as session:
                users = await us_repo.get_brief_users(session)
            for us in users:
                try:
                    tz = ZoneInfo(us.timezone)
                    now_local = datetime.now(tz)
                    today_str = now_local.strftime("%Y-%m-%d")
                    brief_h, brief_m = map(int, us.brief_time.split(":"))
                    already_sent = _last_brief_dates.get(us.owner_id) == today_str
                    time_reached = (
                        now_local.hour > brief_h
                        or (now_local.hour == brief_h and now_local.minute >= brief_m)
                    )
                    if time_reached and not already_sent:
                        await build_and_send_brief(bot, us.owner_id)
                        _last_brief_dates[us.owner_id] = today_str
                except Exception:
                    logger.exception("Morning brief failed for user %d", us.owner_id)
        except Exception:
            logger.exception("Morning brief loop iteration failed")
