from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from bot.handlers.direct_messages import _PERSON_RE, _normalize_ru_name, _contact_picker_keyboard, _pending_ask
from config import settings
from db.repositories import contacts as contact_repo
from db.repositories import messages as msg_repo
from db.repositories import user_settings as us_repo
from services.ai import answer_from_context, embed_text

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    owner_id = message.from_user.id

    us = await us_repo.get_or_create(session, owner_id)
    if us.privacy_accepted_at is None:
        from bot.middlewares.privacy_gate import _POLICY_TEXT, _ACCEPT_KEYBOARD
        await message.answer(_POLICY_TEXT, parse_mode="HTML", reply_markup=_ACCEPT_KEYBOARD)
        return

    buttons: list[InlineKeyboardButton] = [
        InlineKeyboardButton(text="📖 Инструкция к боту", callback_data="tut:0"),
    ]
    if settings.miniapp_url.startswith("https://"):
        buttons.append(InlineKeyboardButton(
            text="📱 Мини-приложение",
            web_app=WebAppInfo(url=settings.miniapp_url),
        ))
    await message.answer(
        "🧠 <b>НейроSave — ИИ-помощник, который экономит ваше время и нейроресурс</b>\n\n"
        "Забудьте про потерянные задачи, пропущенные письма и утренний хаос.\n\n"
        "📌 <b>Задачи</b> — сам извлекает дедлайны из чатов и напоминает вовремя\n"
        "👻 <b>Ghost-режим</b> — отвечает за вас пока вы заняты, собирает суть вопросов\n"
        "🔍 <b>Память чатов</b> — находит любую договорённость за секунды по запросу\n"
        "📨 <b>Gmail</b> — важные письма прямо в Telegram, ответ без смены приложения\n"
        "☀️ <b>Утренний брифинг</b> — дедлайны, просрочки и ночная сводка каждое утро\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "⚙️ <b>Дайте боту доступ к чатам</b> — без этого бот не сможет работать.\n"
        "Инструкция по кнопке ниже 👇",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[buttons]),
    )


@router.message(Command("app"))
async def cmd_app(message: Message) -> None:
    if message.from_user is None:
        return
    if not settings.miniapp_url.startswith("https://"):
        await message.answer("📱 Мини-приложение: " + settings.miniapp_url)
        return
    await message.answer(
        "📱 NeuroSave Mini App:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="Открыть приложение",
                    web_app=WebAppInfo(url=settings.miniapp_url),
                )
            ]]
        ),
    )


@router.message(Command("ask"))
async def cmd_ask(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    owner_id = message.from_user.id
    query = (message.text or "").removeprefix("/ask").strip()
    if not query:
        await message.answer(
            "Использование: <code>/ask ваш вопрос</code>\n"
            "Пример: /ask что мы договорились с Димой по комиссии?",
            parse_mode="HTML",
        )
        return

    thinking = await message.answer("🔍 Ищу в истории переписок…")
    try:
        us = await us_repo.get_or_create(session, owner_id)
        name_map = await contact_repo.get_name_map(session, owner_id)

        # Determine chat filter for the query.
        # Priority 1: saved_name match with stem (user-set aliases — reliable, no false positives).
        # Priority 2: exact Telegram name match (no stem — avoids matching wrong people).
        # If query mentions a person but nothing matches → show contact picker.
        chat_id_filter: int | None = None
        query_lower = query.lower()
        query_words = query_lower.split()

        saved_name_map = await contact_repo.get_saved_name_map(session, owner_id)
        # Match only on user-set saved_name aliases (reliable, no false positives).
        # Handles Russian case inflections: "Андрей".startswith("андрей") catches "андреем".
        for uid, sn in saved_name_map.items():
            sn_lower = sn.lower()
            if any(w == sn_lower or w.startswith(sn_lower) for w in query_words):
                chat_id_filter = uid
                break

        # Person name detected but no contact found → offer picker
        if chat_id_filter is None:
            m = _PERSON_RE.search(query)
            if m:
                person_alias = _normalize_ru_name(m.group(1))
                recent_contacts = await contact_repo.get_recent_contacts(session, owner_id, limit=12)
                if recent_contacts:
                    _pending_ask[owner_id] = query
                    await thinking.delete()
                    await message.answer(
                        f"❓ Не нашёл контакт «{person_alias}» — выберите кого вы имеете в виду:\n"
                        "Запомню псевдоним и выполню поиск.",
                        reply_markup=_contact_picker_keyboard(person_alias, recent_contacts),
                    )
                    return

        query_vec = await embed_text(query)
        results = await msg_repo.search_similar(
            session, owner_id, query_vec, limit=25, chat_id_filter=chat_id_filter
        )
        if not results:
            await thinking.edit_text("Не нашёл ничего похожего — возможно, история ещё не проиндексирована.")
            return
        answer = await answer_from_context(
            query, results,
            language=us.language,
            name_map=name_map,
            tz_name=us.timezone,
        )
        await thinking.edit_text(answer, parse_mode="HTML")
    except Exception:
        logger.exception("cmd_ask failed")
        await thinking.edit_text("❌ Не удалось выполнить поиск.")


@router.message(Command("admin"))
async def cmd_admin(message: Message, bot: Bot, session: AsyncSession) -> None:
    if message.from_user is None or message.from_user.id != settings.owner_chat_id:
        return

    users = await us_repo.get_all_users_ordered(session)
    if not users:
        await message.answer("Пользователей пока нет.")
        return

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    month_start = today_start - timedelta(days=30)

    def _ts(u: object) -> datetime:
        from db.models import UserSettings as _US
        assert isinstance(u, _US)
        return u.created_at if u.created_at.tzinfo else u.created_at.replace(tzinfo=timezone.utc)

    total = len(users)
    new_today = sum(1 for u in users if _ts(u) >= today_start)
    new_week = sum(1 for u in users if _ts(u) >= week_start)
    new_month = sum(1 for u in users if _ts(u) >= month_start)

    # Daily breakdown for the last 7 days
    day_counts: Counter[str] = Counter()
    for u in users:
        ts = _ts(u)
        if ts >= week_start:
            day_key = ts.strftime("%d.%m")
            day_counts[day_key] += 1
    # Sort days chronologically
    day_lines = [f"  {day}: +{cnt}" for day, cnt in sorted(day_counts.items())]

    lines = [
        "👑 <b>Админ-панель NeuroSave</b>",
        "",
        f"👥 Всего пользователей: <b>{total}</b>",
        "",
        "📈 <b>Прирост:</b>",
        f"  Сегодня: <b>+{new_today}</b>",
        f"  За 7 дней: <b>+{new_week}</b>",
        f"  За 30 дней: <b>+{new_month}</b>",
    ]

    if day_lines:
        lines += ["", "🗓 <b>По дням (последние 7):</b>"] + day_lines

    # Last 20 users — try to resolve names via Telegram
    lines += ["", "🆕 <b>Последние пользователи:</b>"]
    recent = users[:20]
    for i, u in enumerate(recent, 1):
        from db.models import UserSettings as _US
        assert isinstance(u, _US)
        ts = _ts(u)
        date_str = ts.strftime("%d.%m.%y")
        display = f"<code>{u.owner_id}</code>"
        try:
            chat = await bot.get_chat(u.owner_id)
            parts = []
            if chat.username:
                parts.append(f"@{chat.username}")
            name = " ".join(filter(None, [chat.first_name, chat.last_name]))
            if name:
                parts.append(name)
            if parts:
                display = " · ".join(parts)
        except Exception:
            pass
        lines.append(f"  {i}. {display} — {date_str}")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("delete_my_data"))
async def cmd_delete_my_data(message: Message) -> None:
    if message.from_user is None:
        return
    await message.answer(
        "⚠️ <b>Удаление всех данных</b>\n\n"
        "Будут безвозвратно удалены:\n"
        "• Все задачи и напоминания\n"
        "• История переписки и индексы\n"
        "• Контакты и метки\n"
        "• Настройки и подключённые интеграции\n"
        "• Ghost Mode и все сессии\n\n"
        "Это действие <b>необратимо</b>. Вы уверены?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Да, удалить всё", callback_data="delete_data_confirm"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="delete_data_cancel"),
            ]
        ]),
    )




