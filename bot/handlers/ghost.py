from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config_store import get_timezone
from config import settings
from db.models import InquiryCategory
from db.repositories import ghost as ghost_repo

logger = logging.getLogger(__name__)
router = Router()

DEFAULT_AWAY_RU = (
    "Сейчас занят, отвечу позже. "
    "Если срочно — кратко опишите вопрос, и я свяжусь как освобожусь."
)
DEFAULT_AWAY_EN = (
    "Busy right now, will get back to you later. "
    "If it's urgent, briefly describe your question and I'll reach out when free."
)

_CATEGORY_LABELS: dict[InquiryCategory, str] = {
    InquiryCategory.urgent: "🔴 Срочно",
    InquiryCategory.team: "👥 Команда",
    InquiryCategory.sales: "💼 Продажи",
    InquiryCategory.spam: "🗑 Спам",
}

_CATEGORY_ORDER = [
    InquiryCategory.urgent,
    InquiryCategory.team,
    InquiryCategory.sales,
    InquiryCategory.spam,
]


def _fmt_time(dt: datetime, tz_name: str) -> str:
    try:
        local = dt.astimezone(ZoneInfo(tz_name))
        return f"{local.hour}:{local.strftime('%M')}"
    except Exception:
        return dt.strftime("%H:%M")


def _fmt_date_range(since: datetime, tz_name: str) -> str:
    try:
        local = since.astimezone(ZoneInfo(tz_name))
        now_local = datetime.now(ZoneInfo(tz_name))
        month_ru = ["", "янв", "фев", "мар", "апр", "май", "июн",
                    "июл", "авг", "сен", "окт", "ноя", "дек"][local.month]
        since_str = f"{local.day} {month_ru} {local.hour}:{local.strftime('%M')}"
        now_str = f"{now_local.hour}:{now_local.strftime('%M')}"
        return f"{since_str} – {now_str}"
    except Exception:
        return ""


async def generate_digest_text(
    session: AsyncSession,
    owner_id: int,
) -> str:
    tz_name = get_timezone()

    gs = await ghost_repo.get_session(session, owner_id)
    if gs is None or gs.activated_at is None:
        return ""

    inquiries = await ghost_repo.get_inquiries_since(session, owner_id, gs.activated_at)
    if not inquiries:
        return "📬 Новых запросов нет."

    grouped: dict[InquiryCategory, list[str]] = {}
    for inq in inquiries:
        cat = inq.category or InquiryCategory.spam
        if cat not in grouped:
            grouped[cat] = []
        name = inq.caller_name or f"ID {inq.caller_id}"
        summary = inq.summary or "—"
        time_str = _fmt_time(inq.created_at, tz_name) if inq.created_at else ""
        time_part = f" ({time_str})" if time_str else ""
        grouped[cat].append(f"• <b>{name}</b>{time_part} — {summary}")

    date_range = _fmt_date_range(gs.activated_at, tz_name)
    header = f"📬 <b>Дайджест Ghost Mode</b>"
    if date_range:
        header += f"\n<i>{date_range}</i>"

    lines = [header]
    for cat in _CATEGORY_ORDER:
        if cat in grouped:
            lines.append(f"\n{_CATEGORY_LABELS[cat]}")
            lines.extend(grouped[cat])

    total = sum(len(v) for v in grouped.values())
    lines.append(f"\n<i>Всего запросов: {total}</i>")
    return "\n".join(lines)


@router.message(Command("ghost"))
async def cmd_ghost(message: Message, session: AsyncSession) -> None:
    if message.from_user is None or message.from_user.id != settings.owner_chat_id:
        return
    text = message.text or ""
    parts = text.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""
    cmd = arg.split()[0].lower() if arg else ""

    if cmd not in ("on", "off"):
        gs = await ghost_repo.get_session(session, settings.owner_chat_id)
        status = "активен" if gs and gs.is_active else "выключен"
        current_msg = ""
        if gs and gs.away_message:
            current_msg = f"\nТекущее сообщение: «{gs.away_message}»"
        await message.answer(
            f"👻 Ghost Mode: <b>{status}</b>{current_msg}\n\n"
            "Использование:\n"
            "/ghost on — включить\n"
            "/ghost on Я на встрече до 18:00 — включить с сообщением\n"
            "/ghost off — выключить",
            parse_mode="HTML",
        )
        return

    if cmd == "on":
        gs = await ghost_repo.get_session(session, settings.owner_chat_id)
        already_active = gs is not None and gs.is_active

        custom_msg_part = text.split(maxsplit=2)
        away_msg = custom_msg_part[2].strip() if len(custom_msg_part) > 2 else None

        if already_active and away_msg:
            await ghost_repo.update_away_message(session, settings.owner_chat_id, away_msg)
            await message.answer(f"✅ Сообщение обновлено: «{away_msg}»")
        else:
            await ghost_repo.set_active(session, settings.owner_chat_id, active=True, away_message=away_msg)
            status_text = "👻 Ghost Mode включён. Буду отвечать вместо вас и собирать вопросы.\nИспользуйте /digest для просмотра."
            if away_msg:
                status_text += f"\nСообщение контактам: «{away_msg}»"
            await message.answer(status_text)
    else:
        digest = await generate_digest_text(session, settings.owner_chat_id)
        await ghost_repo.set_active(session, settings.owner_chat_id, active=False)
        await message.answer("👻 Ghost Mode выключен.")
        if digest:
            await message.answer(digest, parse_mode="HTML")


async def cmd_digest(message: Message, session: AsyncSession) -> None:
    """Called from commands router."""
    if message.from_user is None or message.from_user.id != settings.owner_chat_id:
        return
    digest = await generate_digest_text(session, settings.owner_chat_id)
    if not digest:
        await message.answer("Ghost Mode ни разу не активировался — дайджест пуст.")
        return
    await message.answer(digest, parse_mode="HTML")
