from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Coroutine
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.types import Message
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config_store import get_business_connection_id, get_language, get_timezone, set_timezone
from bot.handlers.ghost import generate_digest_text
from bot.reminder_store import (
    ActiveReminder,
    delay_from_iso,
    get_active,
    remove_reminder,
    schedule_reminder,
)
from config import settings
from db.engine import get_session
from db.repositories import contacts as contact_repo
from db.repositories import ghost as ghost_repo
from db.repositories import messages as msg_repo
from db.repositories import tasks as task_repo
from services.ai import (
    answer_from_context,
    embed_text,
    extract_task_from_message,
    generate_dispatch_message,
    get_style_profile,
    parse_dispatch_command,
    parse_reminder_action,
    transcribe_voice,
)

_RU_LABELS = ("через", "мин", "ч")
_EN_LABELS = ("in", "min", "h")

logger = logging.getLogger(__name__)
router = Router()

_bg_tasks: set[asyncio.Task[None]] = set()


def _replace_event_time(text: str, old_iso: str | None, new_iso: str | None, tz_name: str) -> str:
    """Replace the old event clock time inside a reminder text with the new one."""
    if not old_iso or not new_iso:
        return text
    try:
        tz = ZoneInfo(tz_name)
        old_dt = datetime.fromisoformat(old_iso)
        new_dt = datetime.fromisoformat(new_iso)
        if old_dt.tzinfo is None:
            old_dt = old_dt.replace(tzinfo=timezone.utc)
        if new_dt.tzinfo is None:
            new_dt = new_dt.replace(tzinfo=timezone.utc)
        old_loc = old_dt.astimezone(tz)
        new_loc = new_dt.astimezone(tz)
        for fmt in ("{h:02d}:{m}", "{h}:{m}"):
            old_str = fmt.format(h=old_loc.hour, m=old_loc.strftime("%M"))
            new_str = fmt.format(h=new_loc.hour, m=new_loc.strftime("%M"))
            if old_str in text:
                return text.replace(old_str, new_str)
    except Exception:
        pass
    return text


def _format_delay(seconds: float, lang: str) -> str:
    lbl = _RU_LABELS if lang == "ru" else _EN_LABELS
    total_minutes = int(seconds // 60)
    hours, mins = divmod(total_minutes, 60)
    if hours:
        return f"{lbl[0]} {hours} {lbl[2]} {mins} {lbl[1]}" if mins else f"{lbl[0]} {hours} {lbl[2]}"
    return f"{lbl[0]} {total_minutes} {lbl[1]}"


def _format_time_local(iso: str | None, tz_name: str, lang: str) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(ZoneInfo(tz_name))
        day = str(local_dt.day)
        hour = str(local_dt.hour)
        minute = local_dt.strftime("%M")
        if lang == "ru":
            month_ru = ["", "янв", "фев", "мар", "апр", "май", "июн",
                        "июл", "авг", "сен", "окт", "ноя", "дек"][local_dt.month]
            return f"{day} {month_ru} в {hour}:{minute}"
        month_en = local_dt.strftime("%b")
        return f"{month_en} {day} at {hour}:{minute}"
    except Exception:
        return iso or ""


def _build_reminders_ctx(reminders: list[ActiveReminder], tz_name: str, lang: str) -> str:
    lines: list[str] = []
    for i, r in enumerate(reminders, 1):
        time_str = _format_time_local(r.reminder_time_iso, tz_name, lang)
        event_str = (f", event: {_format_time_local(r.event_time_iso, tz_name, lang)}"
                     if r.event_time_iso else "")
        lines.append(f"{i}. {r.reminder_text} — reminder at {time_str}{event_str}")
    return "\n".join(lines) if lines else "(none)"


def _find_reminder_by_hint(reminders: list[ActiveReminder], hint: str | None) -> ActiveReminder | None:
    if not hint or not reminders:
        return None
    hint_lower = hint.lower()
    for r in reminders:
        if hint_lower in r.reminder_text.lower() or r.reminder_text.lower() in hint_lower:
            return r
    for r in reminders:
        for word in hint_lower.split():
            if len(word) > 2 and word in r.reminder_text.lower():
                return r
    return reminders[-1] if len(reminders) == 1 else None


def _find_matching_reminder(active: list[ActiveReminder], new_text: str) -> ActiveReminder | None:
    new_lower = new_text.lower()
    for r in active:
        existing = r.reminder_text.lower()
        if existing in new_lower or new_lower in existing:
            return r
        existing_words = {w for w in existing.split() if len(w) > 3}
        new_words = {w for w in new_lower.split() if len(w) > 3}
        if existing_words & new_words:
            return r
        # Stem match: handles Russian inflection (доктор / доктору / доктора)
        for ew in existing_words:
            for nw in new_words:
                stem = min(5, len(ew), len(nw))
                if stem >= 4 and ew[:stem] == nw[:stem]:
                    return r
    return None


def _fire(coro: Coroutine[Any, Any, None]) -> None:
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def _delayed_send(
    bot: Bot,
    chat_id: int,
    text: str,
    business_connection_id: str | None,
    delay_seconds: float,
) -> None:
    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            business_connection_id=business_connection_id,
        )
    except Exception:
        logger.exception("Failed to send dispatch message to chat %d", chat_id)


async def _ghost_auto_off(bot: Bot, owner_id: int, delay_seconds: float) -> None:
    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)
    try:
        async with get_session() as session:
            await ghost_repo.set_active(session, owner_id, active=False)
        await bot.send_message(chat_id=owner_id, text="👻 Ghost Mode автоматически выключен.")
    except Exception:
        logger.exception("Failed to auto-deactivate ghost mode for owner %d", owner_id)


@router.message(F.contact)
async def handle_contact_share(message: Message, session: AsyncSession) -> None:
    if message.from_user is None or message.from_user.id != settings.owner_chat_id:
        return
    c = message.contact
    if not c or not c.user_id:
        await message.answer("Не удалось определить Telegram ID этого контакта.")
        return

    parts = [c.first_name]
    if c.last_name:
        parts.append(c.last_name)
    full_name = " ".join(parts)

    await contact_repo.upsert_contact(
        session,
        owner_id=settings.owner_chat_id,
        user_id=c.user_id,
        name=full_name,
        has_business_chat=True,
    )
    await contact_repo.set_saved_name(
        session, owner_id=settings.owner_chat_id, user_id=c.user_id, saved_name=full_name,
    )

    await message.answer(
        f"✅ Контакт сохранён: <b>{full_name}</b>\n"
        f"Теперь можно писать «Напиши {full_name.split()[0]}…»",
        parse_mode="HTML",
    )


async def _process_owner_text(
    text: str,
    message: Message,
    bot: Bot,
    session: AsyncSession,
) -> None:
    owner_id = settings.owner_chat_id
    lang = get_language()
    tz_name = get_timezone()
    original_text = text

    parsed = await parse_dispatch_command(text, language=lang, tz_name=tz_name)

    # ── Settings change (e.g. timezone) ──────────────────────────────────────
    if parsed.is_settings and parsed.timezone_iana:
        try:
            set_timezone(parsed.timezone_iana)
            await message.answer(f"✅ Часовой пояс изменён: <b>{get_timezone()}</b>", parse_mode="HTML")
        except ValueError:
            await message.answer(
                f"❌ Не удалось распознать часовой пояс «{parsed.timezone_iana}». "
                "Попробуйте формат: <code>Europe/Warsaw</code>",
                parse_mode="HTML",
            )
        return

    # ── Ghost Mode activation / deactivation ─────────────────────────────────
    if parsed.is_ghost:
        if parsed.ghost_active:
            gs = await ghost_repo.get_session(session, owner_id)
            already_active = gs is not None and gs.is_active
            if already_active and parsed.ghost_away_message:
                await ghost_repo.update_away_message(session, owner_id, parsed.ghost_away_message)
                await message.answer(f"✅ Сообщение обновлено: «{parsed.ghost_away_message}»")
            else:
                await ghost_repo.set_active(
                    session, owner_id,
                    active=True,
                    away_message=parsed.ghost_away_message,
                )
                reply = "👻 Ghost Mode включён. Отвечаю вместо вас и собираю вопросы."
                if parsed.ghost_away_message:
                    reply += f"\n\nАвтоответ: «{parsed.ghost_away_message}»"
                    reply += "\nЧтобы изменить — напишите: автоответ: ваш текст здесь"
                if parsed.ghost_until_iso:
                    d = delay_from_iso(parsed.ghost_until_iso)
                    _fire(_ghost_auto_off(bot, owner_id, d))
                    time_str = _format_time_local(parsed.ghost_until_iso, tz_name, lang)
                    reply += f"\nАвто-выключение в {time_str}."
                else:
                    reply += "\nНапишите «я свободен» или /ghost off чтобы выключить."
                await message.answer(reply)
        else:
            digest = await generate_digest_text(session, owner_id)
            await ghost_repo.set_active(session, owner_id, active=False)
            await message.answer("👻 Ghost Mode выключен. Добро пожаловать обратно!")
            if digest:
                await message.answer(digest, parse_mode="HTML")
        return

    # ── New or updated personal reminder ────────────────────────────────────
    if parsed.is_reminder and parsed.reminder_text:
        iso = parsed.reminder_time_iso or parsed.scheduled_at_iso
        d = delay_from_iso(iso)

        active = get_active(owner_id)
        existing = _find_matching_reminder(active, parsed.reminder_text)

        # No direct text match but reminders exist → ask parse_reminder_action
        # whether this is actually a reschedule of an existing one (e.g.
        # "доктора перенесли с 20 на 18" doesn't share words with
        # "пойти к доктору в 20:00 сегодня", but the action model has context)
        if existing is None and active:
            ctx = _build_reminders_ctx(active, tz_name, lang)
            try:
                action = await parse_reminder_action(text, ctx, language=lang, tz_name=tz_name)
            except Exception:
                action = None
            if action and action.action == "adjust_time" and action.new_reminder_time_iso:
                target = _find_reminder_by_hint(active, action.reminder_hint)
                if target:
                    remove_reminder(owner_id, target)
                    adj_d = delay_from_iso(action.new_reminder_time_iso)
                    new_text = _replace_event_time(
                        target.reminder_text,
                        old_iso=target.event_time_iso,
                        new_iso=parsed.event_time_iso,
                        tz_name=tz_name,
                    )
                    new_r = ActiveReminder(
                        reminder_text=new_text,
                        reminder_time_iso=action.new_reminder_time_iso,
                        event_time_iso=parsed.event_time_iso or target.event_time_iso,
                        lead_description=action.lead_description,
                    )
                    schedule_reminder(bot, owner_id, new_r, adj_d)
                    time_str = _format_time_local(action.new_reminder_time_iso, tz_name, lang)
                    if action.lead_description:
                        confirm = f"✅ Перенёс {action.lead_description}: {new_text} ({time_str})"
                    else:
                        confirm = f"✅ Перенёс на {time_str}: {new_text}"
                    await message.answer(confirm)
                    return

        is_update = existing is not None
        if is_update and existing:
            remove_reminder(owner_id, existing)

        reminder_text = existing.reminder_text if (is_update and existing) else parsed.reminder_text
        if is_update and existing:
            reminder_text = _replace_event_time(
                reminder_text,
                old_iso=existing.event_time_iso,
                new_iso=parsed.event_time_iso,
                tz_name=tz_name,
            )
        reminder = ActiveReminder(
            reminder_text=reminder_text,
            reminder_time_iso=iso or "",
            event_time_iso=parsed.event_time_iso,
            lead_description=parsed.lead_description,
        )
        schedule_reminder(bot, owner_id, reminder, d)

        time_str = _format_time_local(iso, tz_name, lang) if iso else ""
        verb = "Обновил" if is_update else "Напомню"
        if parsed.lead_description:
            confirm = (
                f"✅ {verb} {parsed.lead_description}: {reminder_text}"
                + (f" ({time_str})" if time_str else "")
                + ".\nЧтобы изменить время или удалить — просто напишите мне."
            )
        elif time_str:
            confirm = (
                f"✅ {verb} в {time_str}: {reminder_text}.\n"
                "Чтобы изменить время или удалить — просто напишите мне."
            )
        else:
            confirm = f"✅ Напоминание {'обновлено' if is_update else 'принято'}: {reminder_text}."
        await message.answer(confirm)
        return

    # ── Dispatch to contacts ──────────────────────────────────────────────────
    if parsed.has_dispatch and parsed.recipients:
        if parsed.literal_message or parsed.message_intent:
            bcid = get_business_connection_id()
            sent_to: list[str] = []
            not_found: list[str] = []

            recent = await msg_repo.get_recent_owner_messages(session, settings.owner_chat_id)
            style = await get_style_profile(settings.owner_chat_id, [m.text for m in recent])
            dispatch_delay = delay_from_iso(parsed.scheduled_at_iso)

            for recipient_name in parsed.recipients:
                matches = await contact_repo.find_contacts_by_name(
                    session, owner_id=settings.owner_chat_id, name=recipient_name,
                )
                if not matches:
                    not_found.append(recipient_name)
                    continue

                contact = matches[0]
                if not contact.has_business_chat:
                    not_found.append(contact.saved_name or contact.name or recipient_name)
                    continue

                chat_id = contact.user_id
                display_name = contact.saved_name or contact.name or recipient_name

                if parsed.literal_message:
                    text = parsed.literal_message
                else:
                    try:
                        text = await generate_dispatch_message(
                            intent=parsed.message_intent,  # type: ignore[arg-type]
                            recipient_name=display_name,
                            language=lang,
                            style_profile=style,
                        )
                    except Exception:
                        logger.exception("Failed to generate dispatch message for %s", display_name)
                        text = parsed.message_intent or ""

                _fire(_delayed_send(bot, chat_id, text, bcid, dispatch_delay))
                if dispatch_delay > 0:
                    sent_to.append(f"{display_name} ({_format_delay(dispatch_delay, lang)})")
                else:
                    sent_to.append(display_name)

                # Extract task from the original owner text (e.g. voice command)
                try:
                    extracted = await extract_task_from_message(
                        original_text, language=lang, tz_name=tz_name
                    )
                    if extracted.has_task and extracted.description:
                        deadline: datetime | None = None
                        if extracted.deadline_iso:
                            try:
                                deadline = datetime.fromisoformat(extracted.deadline_iso)
                                if deadline.tzinfo is None:
                                    deadline = deadline.replace(tzinfo=timezone.utc)
                            except ValueError:
                                pass
                        await task_repo.create_task(
                            session,
                            owner_id=settings.owner_chat_id,
                            chat_id=chat_id,
                            message_id=message.message_id,
                            description=extracted.description,
                            assignee_name=display_name,
                            assignee_user_id=contact.user_id,
                            assignee_username=contact.username,
                            deadline=deadline,
                        )
                except Exception:
                    logger.exception("Task extraction after dispatch failed for %s", display_name)

            lines: list[str] = []
            if sent_to:
                lines.append("✅ Отправлено: " + ", ".join(sent_to))
            if not_found:
                names = ", ".join(f"«{n}»" for n in not_found)
                lines.append(
                    f"❌ Не удалось отправить: {names}\n\n"
                    "Возможно, в Telegram этот контакт указан под другим именем, "
                    "или вы ещё не переписывались с ним через бизнес-подключение. "
                    "Перешлите мне его контакт — я сохраню псевдоним. "
                    "Если переписки не было, напишите ему сначала сами, и бот сможет "
                    "отправлять сообщения от вашего имени."
                )
            if lines:
                await message.answer("\n".join(lines))
            return

    # ── Reminder action (adjust time / delete) ───────────────────────────────
    active = get_active(owner_id)
    if active:
        ctx = _build_reminders_ctx(active, tz_name, lang)
        action = await parse_reminder_action(text, ctx, language=lang, tz_name=tz_name)

        if action.action == "delete":
            target = _find_reminder_by_hint(active, action.reminder_hint)
            if target:
                remove_reminder(owner_id, target)
                await message.answer(f"🗑 Напоминание «{target.reminder_text}» удалено.")
            else:
                await message.answer("Не нашёл такое напоминание. Используйте /reminders чтобы увидеть список.")
            return

        if action.action == "adjust_time" and action.new_reminder_time_iso:
            target = _find_reminder_by_hint(active, action.reminder_hint)
            if target:
                remove_reminder(owner_id, target)

                d = delay_from_iso(action.new_reminder_time_iso)
                new_reminder = ActiveReminder(
                    reminder_text=target.reminder_text,
                    reminder_time_iso=action.new_reminder_time_iso,
                    event_time_iso=target.event_time_iso,
                    lead_description=action.lead_description,
                )
                schedule_reminder(bot, owner_id, new_reminder, d)

                time_str = _format_time_local(action.new_reminder_time_iso, tz_name, lang)
                if action.lead_description:
                    confirm = f"✅ Напомню {action.lead_description}: {target.reminder_text} ({time_str})"
                else:
                    confirm = f"✅ Напомню в {time_str}: {target.reminder_text}"
                await message.answer(confirm)
            else:
                await message.answer("Не нашёл такое напоминание. Используйте /reminders чтобы увидеть список.")
            return

    # ── Semantic history search (fallback) ───────────────────────────────────
    thinking = await message.answer("🔍 Ищу в истории переписок…")
    try:
        query_vec = await embed_text(text)
        results = await msg_repo.search_similar(session, owner_id, query_vec, limit=12)
        if not results:
            await thinking.edit_text("Не нашёл ничего похожего в истории переписок.")
            return
        name_map = await contact_repo.get_name_map(session, owner_id)
        ans = await answer_from_context(
            text, results,
            language=lang,
            name_map=name_map,
            tz_name=tz_name,
        )
        await thinking.edit_text(ans, parse_mode="HTML")
    except Exception:
        logger.exception("Semantic search fallback failed")
        await thinking.edit_text("❌ Не удалось выполнить поиск.")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_owner_dispatch(message: Message, bot: Bot, session: AsyncSession) -> None:
    if message.from_user is None or message.from_user.id != settings.owner_chat_id:
        return
    if not message.text:
        return
    await _process_owner_text(message.text, message, bot, session)


@router.message(F.voice)
async def handle_owner_voice(message: Message, bot: Bot, session: AsyncSession) -> None:
    if message.from_user is None or message.from_user.id != settings.owner_chat_id:
        return
    if not message.voice:
        return
    thinking = await message.answer("🎙 Распознаю…")
    try:
        buf = await bot.download(message.voice)
        if buf is None:
            await thinking.edit_text("❌ Не удалось скачать голосовое сообщение.")
            return
        text = await transcribe_voice(buf.read())
    except Exception:
        logger.exception("Voice transcription failed")
        await thinking.edit_text("❌ Не удалось распознать голосовое сообщение.")
        return
    await thinking.edit_text(f"🎙 <i>{text}</i>", parse_mode="HTML")
    await _process_owner_text(text, message, bot, session)


async def cmd_reminders(message: Message) -> None:
    """Called from commands router — lists active reminders for the owner."""
    if message.from_user is None or message.from_user.id != settings.owner_chat_id:
        return
    owner_id = message.from_user.id
    tz_name = get_timezone()
    lang = get_language()
    active = get_active(owner_id)
    if not active:
        await message.answer("Активных напоминаний нет.")
        return
    lines = ["⏰ <b>Активные напоминания:</b>"]
    for i, r in enumerate(active, 1):
        time_str = _format_time_local(r.reminder_time_iso, tz_name, lang)
        lines.append(f"{i}. {r.reminder_text}" + (f" — {time_str}" if time_str else ""))
    lines.append("\nЧтобы изменить или удалить — напишите, например: «удали напоминание про стрижку» или «перенеси встречу на 8 утра».")
    await message.answer("\n".join(lines), parse_mode="HTML")
