from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TypedDict
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from beartype import beartype

from db.engine import session_factory
from db.models import InquiryCategory
from db.repositories import contacts as contact_repo
from db.repositories import ghost as ghost_repo
from db.repositories import messages as msg_repo
from db.repositories import tasks as task_repo
from db.repositories import user_settings as us_repo
from services.ai import generate_agenda_recommendation, merge_inquiry_summaries

logger = logging.getLogger(__name__)

_CHECK_INTERVAL = 60  # seconds

_MONTH_RU = ["", "янв", "фев", "мар", "апр", "май", "июн",
             "июл", "авг", "сен", "окт", "ноя", "дек"]
_MONTH_UA = ["", "січ", "лют", "бер", "кві", "тра", "чер",
             "лип", "сер", "вер", "жов", "лис", "гру"]

_CATEGORY_LABELS: dict[InquiryCategory, str] = {
    InquiryCategory.urgent: "🔴 Срочно",
    InquiryCategory.team: "👥 Команда",
    InquiryCategory.sales: "💼 Продажи",
    InquiryCategory.spam: "🗑 Спам",
    InquiryCategory.normal: "💬 Не срочно",
}

_CATEGORY_SORT: dict[InquiryCategory | None, int] = {
    InquiryCategory.urgent: 0,
    InquiryCategory.team: 1,
    InquiryCategory.sales: 2,
    InquiryCategory.normal: 3,
    None: 4,
}

# Display names for contact labels (lower-case keys); fallback: 🏷 {label}
_LABEL_DISPLAY: dict[str, str] = {
    "команда": "👥 Команда",
    "team": "👥 Team",
    "срочно": "🔴 Срочно",
    "urgent": "🔴 Urgent",
    "продажи": "💼 Продажи",
    "sales": "💼 Sales",
    "спам": "🗑 Спам",
    "spam": "🗑 Spam",
    "личное": "👤 Личное",
    "personal": "👤 Personal",
    "vip": "⭐ VIP",
}


def _label_category_prefix(labels: list[str]) -> str:
    """Return the display prefix for the first recognized or custom label."""
    if not labels:
        return ""
    return _LABEL_DISPLAY.get(labels[0].lower(), f"🏷 {labels[0]}") + " "


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
        return "сьогодні" if lang == "ua" else ("сегодня" if lang == "ru" else "today")
    if days == 1:
        return "вчора" if lang == "ua" else ("вчера" if lang == "ru" else "yesterday")
    return f"{days} дн. тому" if lang == "ua" else (f"{days} дн. назад" if lang == "ru" else f"{days}d ago")


def _is_today_iso(iso: str, tz_name: str) -> bool:
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(ZoneInfo(tz_name))
        return local.date() == datetime.now(ZoneInfo(tz_name)).date()
    except Exception:
        return False


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

        # Load contact labels for night digest callers
        caller_labels: dict[int, list[str]] = {}
        for inq in ghost_inquiries:
            if inq.caller_id not in caller_labels:
                c = await contact_repo.get_contact(session, owner_id, inq.caller_id)
                caller_labels[inq.caller_id] = c.labels if c and c.labels else []

    # Group raw incoming messages by sender (fallback when ghost was off)
    incoming_by_sender: dict[int, _SenderInfo] = {}
    for m in night_msgs:
        if m.sender_id is not None and m.sender_id != owner_id:
            if m.sender_id not in incoming_by_sender:
                incoming_by_sender[m.sender_id] = _SenderInfo(name=m.sender_name, count=0, last="")
            incoming_by_sender[m.sender_id]["count"] += 1
            incoming_by_sender[m.sender_id]["last"] = m.text[:80]

    _DIV = "──────────────────"

    if lang == "ua":
        date_str = f"{now_local.day} {_MONTH_UA[now_local.month]}"
        lines: list[str] = [f"☕ <b>Доброго ранку, {date_str}!</b>"]
    elif lang == "ru":
        date_str = f"{now_local.day} {_MONTH_RU[now_local.month]}"
        lines = [f"☕ <b>Доброе утро, {date_str}!</b>"]
    else:
        date_str = now_local.strftime("%b %d")
        lines = [f"☕ <b>Good morning, {date_str}!</b>"]

    # ── Section 1: Owner's personal tasks ────────────────────────────────────
    if my_tasks:
        lines.append(_DIV)
        lines.append("✅ <b>Мої завдання сьогодні</b>" if lang == "ua" else ("✅ <b>Мои задачи сегодня</b>" if lang == "ru" else "✅ <b>My tasks today</b>"))
        for idx, task in enumerate(my_tasks, 1):
            time_dt = task.reminder_time or task.deadline
            time_str = _fmt_time(time_dt, tz_name) if time_dt else ""
            suffix = f"  ⏰ {time_str}" if time_str else ""
            lines.append(f"{idx}. {task.description}{suffix}")

    # ── Section 2: Delegated tasks due today (assigned to others) ────────────
    if delegated_today:
        lines.append(_DIV)
        lines.append("📌 <b>Делеговано сьогодні</b>" if lang == "ua" else ("📌 <b>Делегировано сегодня</b>" if lang == "ru" else "📌 <b>Delegated today</b>"))
        for t in delegated_today:
            time_str = _fmt_time(t.deadline, tz_name) if t.deadline else ""
            assignee = f"  → <b>{t.assignee_name}</b>" if t.assignee_name else ""
            suffix = f"  ⏰ {time_str}" if time_str else ""
            lines.append(f"• {t.description}{assignee}{suffix}")

    # ── Section 3: Overdue delegated tasks ───────────────────────────────────
    today_ids = {t.id for t in delegated_today}
    truly_overdue = [t for t in overdue if t.id not in today_ids]
    if truly_overdue:
        lines.append(_DIV)
        lines.append("🔴 <b>Прострочено</b>" if lang == "ua" else ("🔴 <b>Просрочено</b>" if lang == "ru" else "🔴 <b>Overdue</b>"))
        for t in truly_overdue[:5]:
            when = _days_ago(t.deadline, lang) if t.deadline else "?"
            assignee = f"  → <b>{t.assignee_name}</b>" if t.assignee_name else ""
            lines.append(f"• {t.description}{assignee}  <i>{when}</i>")
        if len(truly_overdue) > 5:
            extra = len(truly_overdue) - 5
            lines.append(f"<i>  + ще {extra}</i>" if lang == "ua" else (f"<i>  + ещё {extra}</i>" if lang == "ru" else f"<i>  + {extra} more</i>"))

    # ── Section 4: Night digest ───────────────────────────────────────────────
    non_spam = [i for i in ghost_inquiries if i.category != InquiryCategory.spam]

    # Group by caller_id, then merge summaries when one sender sent multiple messages
    from collections import defaultdict
    _grouped: dict[int, list] = defaultdict(list)
    for inq in non_spam:
        _grouped[inq.caller_id].append(inq)

    ghost_digest: list[dict] = []
    for caller_id, entries in _grouped.items():
        best = min(entries, key=lambda i: _CATEGORY_SORT.get(i.category, 4))
        latest = max(entries, key=lambda i: i.created_at)
        if len(entries) > 1:
            raw_summaries = [e.summary for e in entries if e.summary]
            try:
                combined_summary = await merge_inquiry_summaries(raw_summaries, language=lang) if raw_summaries else "—"
            except Exception:
                combined_summary = entries[-1].summary or "—"
        else:
            combined_summary = entries[0].summary or "—"
        ghost_digest.append({
            "caller_id": caller_id,
            "caller_name": best.caller_name,
            "category": best.category,
            "summary": combined_summary,
            "created_at": latest.created_at,
        })

    ghost_digest.sort(key=lambda d: _CATEGORY_SORT.get(d["category"], 4))

    if ghost_digest:
        lines.append(_DIV)
        lines.append("🌙 <b>Нічний дайджест</b>" if lang == "ua" else ("🌙 <b>Ночной дайджест</b>" if lang == "ru" else "🌙 <b>Night digest</b>"))
        for entry in ghost_digest[:8]:
            name = entry["caller_name"] or f"ID {entry['caller_id']}"
            summary = entry["summary"] or "—"
            time_str = _fmt_time(entry["created_at"], tz_name)
            labels = caller_labels.get(entry["caller_id"], [])
            if labels:
                prefix = _label_category_prefix(labels)
            else:
                cat_label = _CATEGORY_LABELS.get(entry["category"], "") if entry["category"] else ""
                prefix = f"{cat_label} " if cat_label else ""
            lines.append(f"{prefix}<b>{name}</b>  <i>{time_str}</i>\n<i>  {summary}</i>")
    elif not ghost_inquiries and incoming_by_sender:
        lines.append(_DIV)
        lines.append("🌙 <b>Нічний дайджест</b>" if lang == "ua" else ("🌙 <b>Ночной дайджест</b>" if lang == "ru" else "🌙 <b>Night digest</b>"))
        for sender_id, info in list(incoming_by_sender.items())[:8]:
            name = info["name"] or f"ID {sender_id}"
            count = info["count"]
            snippet = info["last"]
            if len(snippet) > 70:
                snippet = snippet[:70] + "…"
            count_label = f"{count} повід." if lang == "ua" else (f"{count} сообщ." if lang == "ru" else f"{count} msg")
            lines.append(f"<b>{name}</b> ({count_label})\n<i>  {snippet}</i>")

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
                lines.append(_DIV)
                lines.append("💡 <b>Рекомендація</b>" if lang == "ua" else ("💡 <b>Рекомендация</b>" if lang == "ru" else "💡 <b>Agenda</b>"))
                lines.append(f"<blockquote>{agenda}</blockquote>")
        except Exception:
            logger.warning("generate_agenda_recommendation failed", exc_info=True)

    # Detect empty brief — only the greeting header was added
    is_empty = len(lines) == 1
    if is_empty:
        if lang == "ua":
            lines.append(_DIV)
            lines.append("📭 <b>На сьогодні все спокійно</b>\n\n"
                         "• Завдань на сьогодні немає\n"
                         "• Вночі ніхто не писав\n"
                         "• Прострочених завдань немає\n\n"
                         "<i>Якщо бот ще не відслідковує ваші чати — натисніть кнопку нижче і перегляньте інструкцію.</i>")
        elif lang == "ru":
            lines.append(_DIV)
            lines.append("📭 <b>На сегодня всё спокойно</b>\n\n"
                         "• Задач на сегодня нет\n"
                         "• Ночью никто не писал\n"
                         "• Просроченных задач нет\n\n"
                         "<i>Если бот ещё не отслеживает ваши чаты — нажмите кнопку ниже и посмотрите инструкцию.</i>")
        else:
            lines.append(_DIV)
            lines.append("📭 <b>All quiet today</b>\n\n"
                         "• No tasks scheduled for today\n"
                         "• No messages received overnight\n"
                         "• No overdue tasks\n\n"
                         "<i>If the bot isn't tracking your chats yet — tap the button below to view the setup guide.</i>")

    reply_markup: InlineKeyboardMarkup | None = None
    if is_empty:
        if lang == "ua":
            btn_label = "📖 Інструкція до бота"
        elif lang == "ru":
            btn_label = "📖 Инструкция к боту"
        else:
            btn_label = "📖 Bot guide"
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=btn_label, callback_data="tut:0"),
        ]])

    await bot.send_message(
        chat_id=owner_id,
        text="\n".join(lines),
        parse_mode="HTML",
        reply_markup=reply_markup,
    )
    logger.info("Morning brief sent to owner %d (empty=%s)", owner_id, is_empty)


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
                    already_sent = us.last_brief_date == today_str
                    time_reached = (
                        now_local.hour > brief_h
                        or (now_local.hour == brief_h and now_local.minute >= brief_m)
                    )
                    # New user who registered today after the brief time should not
                    # receive today's brief — mark as sent and start from tomorrow.
                    if (
                        not already_sent
                        and time_reached
                        and us.last_brief_date is None
                        and us.created_at is not None
                    ):
                        created_local = us.created_at.astimezone(tz)
                        if created_local.date() == now_local.date() and (
                            created_local.hour > brief_h
                            or (created_local.hour == brief_h and created_local.minute >= brief_m)
                        ):
                            async with session_factory() as skip_session:
                                await us_repo.update_settings(skip_session, us.owner_id, last_brief_date=today_str)
                                await skip_session.commit()
                            continue
                    if time_reached and not already_sent:
                        async with session_factory() as upd_session:
                            await us_repo.update_settings(upd_session, us.owner_id, last_brief_date=today_str)
                            await upd_session.commit()
                        await build_and_send_brief(bot, us.owner_id)
                except Exception:
                    logger.exception("Morning brief failed for user %d", us.owner_id)
        except Exception:
            logger.exception("Morning brief loop iteration failed")
