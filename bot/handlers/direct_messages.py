from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Coroutine
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config_store import get_business_connection_id
import bot.telethon_client as tg_client
from db.repositories import user_settings as us_repo
from bot.handlers.ghost import generate_digest_text
from bot.reminder_store import delay_from_iso
from db.engine import get_session
from db.models import Contact, Task
from db.repositories import contacts as contact_repo
from services.contact_sync import get_folder_users, _upsert_from_tg_user
from db.repositories import ghost as ghost_repo
from db.repositories import messages as msg_repo
from db.repositories import tasks as task_repo
from services.ai import (
    ReminderItem,
    answer_from_context,
    embed_text,
    extract_tasks_from_message,
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

# Pending dispatch when contact not found: owner_id → {alias, text, bcid, session}
_pending_dispatch: dict[int, dict[str, object]] = {}

# Pending email waiting for attachment: owner_id → {to, subject, body}
_pending_email: dict[int, dict[str, object]] = {}


def _replace_event_time(text: str, old_iso: str | None, new_iso: str | None, tz_name: str) -> str:
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
        return f"{local_dt.strftime('%b')} {day} at {hour}:{minute}"
    except Exception:
        return iso or ""


def _task_reminder_iso(task: Task) -> str | None:
    return task.reminder_time.isoformat() if task.reminder_time else None


def _task_deadline_iso(task: Task) -> str | None:
    return task.deadline.isoformat() if task.deadline else None


def _build_reminders_ctx(tasks: list[Task], tz_name: str, lang: str) -> str:
    lines = [
        f"{i}. {t.description} — reminder at "
        f"{_format_time_local(_task_reminder_iso(t), tz_name, lang)}"
        + (f", event: {_format_time_local(_task_deadline_iso(t), tz_name, lang)}" if t.deadline else "")
        for i, t in enumerate(tasks, 1)
    ]
    return "\n".join(lines) if lines else "(none)"


def _find_task_by_hint(tasks: list[Task], hint: str | None) -> Task | None:
    if not hint or not tasks:
        return None
    hint_lower = hint.lower()
    for t in tasks:
        if hint_lower in t.description.lower() or t.description.lower() in hint_lower:
            return t
    for t in tasks:
        if any(len(w) > 2 and w in t.description.lower() for w in hint_lower.split()):
            return t
    return tasks[-1] if len(tasks) == 1 else None


def _find_matching_task(tasks: list[Task], new_text: str) -> Task | None:
    new_lower = new_text.lower()
    for t in tasks:
        existing = t.description.lower()
        if existing in new_lower or new_lower in existing:
            return t
        existing_words = {w for w in existing.split() if len(w) > 3}
        new_words = {w for w in new_lower.split() if len(w) > 3}
        if existing_words & new_words:
            return t
        for ew in existing_words:
            for nw in new_words:
                stem = min(5, len(ew), len(nw))
                if stem >= 4 and ew[:stem] == nw[:stem]:
                    return t
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
        await bot.send_message(chat_id=chat_id, text=text, business_connection_id=business_connection_id)
    except Exception:
        logger.exception("Failed to send dispatch message to chat %d", chat_id)


async def _delayed_send_telethon(
    client: object,
    user_id: int,
    text: str,
    delay_seconds: float,
) -> None:
    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)
    try:
        await client.send_message(user_id, text)  # type: ignore[union-attr]
    except Exception:
        logger.exception("Telethon send failed to user %d", user_id)


async def _ghost_auto_off(bot: Bot, owner_id: int, delay_seconds: float) -> None:
    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)
    try:
        async with get_session() as session:
            await ghost_repo.set_active(session, owner_id, active=False)
        await bot.send_message(chat_id=owner_id, text="👻 Ghost Mode автоматически выключен.")
    except Exception:
        logger.exception("Failed to auto-deactivate ghost mode for owner %d", owner_id)


async def _get_send_client(
    owner_id: int,
    telethon_session: str | None,
) -> object | None:
    """Return an authorized Telethon client, or None if unavailable."""
    client = await tg_client.get_client(owner_id, telethon_session)
    if client and await tg_client.is_authorized(owner_id, telethon_session):
        return client
    return None


async def _dispatch_contact(
    contact: Contact,
    send_text: str,
    bot: Bot,
    bcid: str | None,
    delay_seconds: float,
    owner_id: int,
    telethon_session: str | None,
    session: AsyncSession,
    original_text: str,
    message: Message,
    lang: str,
    tz_name: str,
) -> bool:
    """Fire a send to one contact (Bot API or Telethon fallback). Returns True if queued."""
    if contact.has_business_chat:
        _fire(_delayed_send(bot, contact.user_id, send_text, bcid, delay_seconds))
    else:
        client = await _get_send_client(owner_id, telethon_session)
        if client is None:
            return False
        _fire(_delayed_send_telethon(client, contact.user_id, send_text, delay_seconds))

    display_name = contact.saved_name or contact.name or ""
    try:
        extracted_list = await extract_tasks_from_message(original_text, language=lang, tz_name=tz_name)
        for extracted in extracted_list:
            task_deadline: datetime | None = None
            if extracted.deadline_iso:
                try:
                    task_deadline = datetime.fromisoformat(extracted.deadline_iso)
                    if task_deadline.tzinfo is None:
                        task_deadline = task_deadline.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
            await task_repo.create_task(
                session,
                owner_id=owner_id,
                chat_id=contact.user_id,
                message_id=message.message_id,
                description=extracted.description or "",
                assignee_name=display_name,
                assignee_user_id=contact.user_id,
                assignee_username=contact.username,
                deadline=task_deadline,
            )
    except Exception:
        logger.exception("Task extraction failed for contact %d", contact.user_id)

    return True


def _contact_picker_keyboard(alias: str, contacts: list[Contact]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for c in contacts:
        label = (c.saved_name or c.name or c.username or str(c.user_id))[:20]
        row.append(InlineKeyboardButton(
            text=label,
            callback_data=f"pick_alias:{alias[:20]}:{c.user_id}",
        ))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.contact)
async def handle_contact_share(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    owner_id = message.from_user.id
    c = message.contact
    if not c or not c.user_id:
        await message.answer("Не удалось определить Telegram ID этого контакта.")
        return

    parts = [c.first_name]
    if c.last_name:
        parts.append(c.last_name)
    full_name = " ".join(parts)

    await contact_repo.upsert_contact(session, owner_id=owner_id, user_id=c.user_id,
                                      name=full_name, has_business_chat=True)
    await contact_repo.set_saved_name(session, owner_id=owner_id, user_id=c.user_id,
                                      saved_name=full_name)
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
    owner_id: int,
) -> None:
    us = await us_repo.get_or_create(session, owner_id)
    lang = us.language
    tz_name = us.timezone
    original_text = text

    parsed = await parse_dispatch_command(text, language=lang, tz_name=tz_name)

    # ── Settings change ───────────────────────────────────────────────────────
    if parsed.is_settings and parsed.timezone_iana:
        try:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
            ZoneInfo(parsed.timezone_iana)
            await us_repo.update_settings(session, owner_id, timezone=parsed.timezone_iana)
            await message.answer(f"✅ Часовой пояс изменён: <b>{parsed.timezone_iana}</b>", parse_mode="HTML")
        except (KeyError, ZoneInfoNotFoundError):
            await message.answer(
                f"❌ Не удалось распознать часовой пояс «{parsed.timezone_iana}». "
                "Попробуйте формат: <code>Europe/Warsaw</code>", parse_mode="HTML",
            )
        return

    # ── Ghost Mode ────────────────────────────────────────────────────────────
    if parsed.is_ghost:
        if parsed.ghost_active:
            gs = await ghost_repo.get_session(session, owner_id)
            if gs is not None and gs.is_active and parsed.ghost_away_message:
                await ghost_repo.update_away_message(session, owner_id, parsed.ghost_away_message)
                await message.answer(f"✅ Сообщение обновлено: «{parsed.ghost_away_message}»")
            else:
                await ghost_repo.set_active(session, owner_id, active=True,
                                            away_message=parsed.ghost_away_message)
                reply = "👻 Ghost Mode включён. Отвечаю вместо вас и собираю вопросы."
                if parsed.ghost_away_message:
                    reply += f"\n\nАвтоответ: «{parsed.ghost_away_message}»"
                    reply += "\nЧтобы изменить — напишите: автоответ: ваш текст здесь"
                if parsed.ghost_until_iso:
                    d = delay_from_iso(parsed.ghost_until_iso)
                    _fire(_ghost_auto_off(bot, owner_id, d))
                    reply += f"\nАвто-выключение в {_format_time_local(parsed.ghost_until_iso, tz_name, lang)}."
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

    # ── Personal reminder ─────────────────────────────────────────────────────
    if parsed.is_reminder and (parsed.reminder_items or parsed.reminder_text):
        # ── Multiple reminders: batch create ──────────────────────────────────
        if len(parsed.reminder_items) >= 2:
            confirms: list[str] = []
            for item in parsed.reminder_items:
                r_time: datetime | None = None
                if item.reminder_time_iso:
                    try:
                        r_time = datetime.fromisoformat(item.reminder_time_iso)
                        if r_time.tzinfo is None:
                            r_time = r_time.replace(tzinfo=timezone.utc)
                    except ValueError:
                        pass
                e_time: datetime | None = None
                if item.event_time_iso:
                    try:
                        e_time = datetime.fromisoformat(item.event_time_iso)
                        if e_time.tzinfo is None:
                            e_time = e_time.replace(tzinfo=timezone.utc)
                    except ValueError:
                        pass
                created_t = await task_repo.create_personal_task(
                    session, owner_id=owner_id,
                    description=item.reminder_text,
                    deadline=e_time,
                    reminder_time=r_time,
                )
                time_str = _format_time_local(item.reminder_time_iso, tz_name, lang) if item.reminder_time_iso else ""
                confirms.append(f"• {created_t.description}" + (f" — {time_str}" if time_str else ""))
            await message.answer(
                f"✅ Создано {len(confirms)} напоминания:\n" + "\n".join(confirms)
                + "\nЧтобы изменить или удалить — напишите мне."
            )
            return

        # ── Single reminder: existing logic ───────────────────────────────────
        iso = parsed.reminder_time_iso or parsed.scheduled_at_iso

        reminder_time: datetime | None = None
        if iso:
            try:
                reminder_time = datetime.fromisoformat(iso)
                if reminder_time.tzinfo is None:
                    reminder_time = reminder_time.replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        deadline: datetime | None = None
        if parsed.event_time_iso:
            try:
                deadline = datetime.fromisoformat(parsed.event_time_iso)
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        active_tasks = await task_repo.get_open_tasks(session, owner_id, is_personal=True)
        existing_task = _find_matching_task(active_tasks, parsed.reminder_text)

        if existing_task is None and active_tasks:
            ctx = _build_reminders_ctx(active_tasks, tz_name, lang)
            try:
                action = await parse_reminder_action(text, ctx, language=lang, tz_name=tz_name)
            except Exception:
                action = None
            if action and action.action == "adjust_time" and action.new_reminder_time_iso:
                target = _find_task_by_hint(active_tasks, action.reminder_hint)
                if target:
                    new_reminder_time: datetime | None = None
                    try:
                        new_reminder_time = datetime.fromisoformat(action.new_reminder_time_iso)
                        if new_reminder_time.tzinfo is None:
                            new_reminder_time = new_reminder_time.replace(tzinfo=timezone.utc)
                    except ValueError:
                        pass
                    new_desc = _replace_event_time(target.description, _task_deadline_iso(target),
                                                   parsed.event_time_iso, tz_name)
                    target.description = new_desc
                    await task_repo.set_reminder(session, target.id, new_reminder_time)
                    time_str = _format_time_local(action.new_reminder_time_iso, tz_name, lang)
                    confirm = (
                        f"✅ Перенёс {action.lead_description}: {new_desc} ({time_str})"
                        if action.lead_description else f"✅ Перенёс на {time_str}: {new_desc}"
                    )
                    await message.answer(confirm)
                    return

        is_update = existing_task is not None
        if is_update and existing_task is not None:
            new_desc = _replace_event_time(existing_task.description, _task_deadline_iso(existing_task),
                                           parsed.event_time_iso, tz_name)
            existing_task.description = new_desc
            if deadline is not None:
                existing_task.deadline = deadline
            await task_repo.set_reminder(session, existing_task.id, reminder_time)
            reminder_text = new_desc
        else:
            new_task = await task_repo.create_personal_task(
                session, owner_id=owner_id, description=parsed.reminder_text,
                deadline=deadline, reminder_time=reminder_time,
            )
            reminder_text = new_task.description

        time_str = _format_time_local(iso, tz_name, lang) if iso else ""
        verb = "Обновил" if is_update else "Напомню"
        if parsed.lead_description:
            confirm = (
                f"✅ {verb} {parsed.lead_description}: {reminder_text}"
                + (f" ({time_str})" if time_str else "")
                + ".\nЧтобы изменить время или удалить — просто напишите мне."
            )
        elif time_str:
            confirm = f"✅ {verb} в {time_str}: {reminder_text}.\nЧтобы изменить время или удалить — просто напишите мне."
        else:
            confirm = f"✅ Напоминание {'обновлено' if is_update else 'принято'}: {reminder_text}."
        await message.answer(confirm)
        return

    # ── Email ─────────────────────────────────────────────────────────────────
    if parsed.is_email and parsed.recipients:
        from services import gmail as gmail_svc
        from services.ai import generate_dispatch_message

        gmail_service = await gmail_svc.get_gmail_service(owner_id, session)
        if gmail_service is None:
            await message.answer(
                "❌ Gmail не подключён. Перейди в мини-приложение → Настройки → Интеграции → Gmail."
            )
            return

        recipient_name = parsed.recipients[0]
        contacts = await contact_repo.find_contacts_by_name(session, owner_id, recipient_name)
        contact = contacts[0] if contacts else None

        if contact is None or not contact.email:
            _pending_email[owner_id] = {
                "recipient_name": recipient_name,
                "subject": parsed.email_subject or "",
                "body_intent": parsed.email_body_intent,
                "literal_body": parsed.email_literal_body,
                "has_attachment": parsed.email_has_attachment,
                "contact_id": contact.user_id if contact else None,
            }
            name_display = contact.name or recipient_name if contact else recipient_name
            await message.answer(
                f"📧 Для {name_display} нет email-адреса в базе.\n"
                "Введи адрес электронной почты:"
            )
            return

        body = parsed.email_literal_body
        if not body:
            style = await get_style_profile(owner_id, [])
            body = await generate_dispatch_message(
                intent=parsed.email_body_intent or "",
                recipient_name=contact.name or recipient_name,
                language=lang,
                style_profile=style,
            )
        subject = parsed.email_subject or f"Сообщение от {await gmail_svc.get_gmail_address(owner_id, session) or 'NeuroSave'}"

        if parsed.email_has_attachment:
            _pending_email[owner_id] = {
                "to": contact.email,
                "subject": subject,
                "body": body,
            }
            await message.answer(
                f"📎 Прикрепи файл следующим сообщением. Письмо будет отправлено на {contact.email}."
            )
            return

        try:
            await gmail_svc.send_email(gmail_service, to=[contact.email], subject=subject, body=body)
            await message.answer(
                f"✅ Письмо отправлено на <b>{contact.email}</b>\n"
                f"<b>Тема:</b> {subject}\n\n{body[:200]}{'…' if len(body) > 200 else ''}",
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.exception("Gmail send failed for owner %d: %s", owner_id, exc)
            await message.answer("❌ Не удалось отправить письмо. Проверьте подключение Gmail.")
        return

    # ── Dispatch to contacts ──────────────────────────────────────────────────
    if parsed.has_dispatch and parsed.recipients:
        if not (parsed.literal_message or parsed.message_intent):
            return

        bcid = get_business_connection_id()
        sent_to: list[str] = []
        not_found: list[str] = []

        recent_msgs = await msg_repo.get_recent_owner_messages(session, owner_id)
        style = await get_style_profile(owner_id, [m.text for m in recent_msgs])
        dispatch_delay = delay_from_iso(parsed.scheduled_at_iso)

        for recipient_name in parsed.recipients:
            matches = await contact_repo.find_contacts_by_name(
                session, owner_id=owner_id, name=recipient_name,
            )

            # ── Group / folder dispatch ───────────────────────────────────────
            if not matches:
                group_contacts = await contact_repo.find_contacts_by_label(
                    session, owner_id=owner_id, label=recipient_name,
                )

                # Real-time Telethon folder lookup when DB has no label entries yet
                if not group_contacts:
                    live_client = await _get_send_client(owner_id, us.telethon_session)
                    if live_client:
                        try:
                            folder_users = await get_folder_users(live_client, recipient_name)
                            for fu in folder_users:
                                await _upsert_from_tg_user(session, owner_id, fu, team_label=recipient_name)
                            await session.flush()
                            group_contacts = await contact_repo.find_contacts_by_label(
                                session, owner_id=owner_id, label=recipient_name,
                            )
                        except Exception:
                            logger.exception("Real-time folder lookup failed for '%s'", recipient_name)

                if group_contacts:
                    group_sent: list[str] = []
                    for gc in group_contacts:
                        if parsed.literal_message:
                            send_text: str = parsed.literal_message
                        else:
                            gc_name = gc.saved_name or gc.name or recipient_name
                            try:
                                send_text = await generate_dispatch_message(
                                    intent=parsed.message_intent,  # type: ignore[arg-type]
                                    recipient_name=gc_name,
                                    language=lang,
                                    style_profile=style,
                                )
                            except Exception:
                                send_text = parsed.message_intent or ""

                        ok = await _dispatch_contact(
                            gc, send_text, bot, bcid, dispatch_delay,
                            owner_id, us.telethon_session, session,
                            original_text, message, lang, tz_name,
                        )
                        if ok:
                            group_sent.append(gc.saved_name or gc.name or str(gc.user_id))

                    label_display = recipient_name.capitalize()
                    if group_sent:
                        if dispatch_delay > 0:
                            sent_to.append(f"{label_display} ({_format_delay(dispatch_delay, lang)}): {', '.join(group_sent)}")
                        else:
                            sent_to.append(f"{label_display}: {', '.join(group_sent)}")
                    else:
                        await message.answer(
                            f"⚠️ Не удалось отправить сообщение группе «{label_display}» — "
                            "нет доступа к этим чатам (нет бизнес-подключения и Telethon недоступен)."
                        )
                    continue

                not_found.append(recipient_name)
                continue

            # ── Individual contact dispatch ───────────────────────────────────
            contact = matches[0]
            display_name = contact.saved_name or contact.name or recipient_name

            if parsed.literal_message:
                send_text = parsed.literal_message
            else:
                try:
                    send_text = await generate_dispatch_message(
                        intent=parsed.message_intent,  # type: ignore[arg-type]
                        recipient_name=display_name,
                        language=lang,
                        style_profile=style,
                    )
                except Exception:
                    logger.exception("Failed to generate dispatch message for %s", display_name)
                    send_text = parsed.message_intent or ""

            ok = await _dispatch_contact(
                contact, send_text, bot, bcid, dispatch_delay,
                owner_id, us.telethon_session, session,
                original_text, message, lang, tz_name,
            )
            if ok:
                label = f"{display_name} ({_format_delay(dispatch_delay, lang)})" if dispatch_delay > 0 else display_name
                sent_to.append(label)
            else:
                not_found.append(display_name)

        if sent_to:
            await message.answer("✅ Отправлено: " + ", ".join(sent_to))

        for alias in not_found:
            recent_contacts = await contact_repo.get_recent_contacts(session, owner_id, limit=12)
            if not recent_contacts:
                await message.answer(f"❓ Не нашёл «{alias}» — синхронизируйте контакты (/sync_contacts).")
                continue

            if parsed.literal_message:
                pending_text: str = parsed.literal_message
            else:
                try:
                    pending_text = await generate_dispatch_message(
                        intent=parsed.message_intent,  # type: ignore[arg-type]
                        recipient_name=alias, language=lang, style_profile=style,
                    )
                except Exception:
                    pending_text = parsed.message_intent or ""

            _pending_dispatch[owner_id] = {
                "alias": alias,
                "text": pending_text,
                "business_connection_id": bcid,
                "telethon_session": us.telethon_session,
            }
            await message.answer(
                f"❓ Не нашёл «{alias}» среди контактов.\n"
                "Выберите кого вы имеете в виду — запомню псевдоним и отправлю:",
                reply_markup=_contact_picker_keyboard(alias, recent_contacts),
            )
        return

    # ── Reminder action (adjust / delete) ────────────────────────────────────
    active_tasks = await task_repo.get_open_tasks(session, owner_id, is_personal=True)
    if active_tasks:
        ctx = _build_reminders_ctx(active_tasks, tz_name, lang)
        action = await parse_reminder_action(text, ctx, language=lang, tz_name=tz_name)

        if action.action == "delete":
            target = _find_task_by_hint(active_tasks, action.reminder_hint)
            if target:
                await task_repo.delete_task(session, target.id)
                await message.answer(f"🗑 Напоминание «{target.description}» удалено.")
            else:
                await message.answer("Не нашёл такое напоминание. Используйте /reminders чтобы увидеть список.")
            return

        if action.action == "adjust_time" and action.new_reminder_time_iso:
            target = _find_task_by_hint(active_tasks, action.reminder_hint)
            if target:
                new_rt: datetime | None = None
                try:
                    new_rt = datetime.fromisoformat(action.new_reminder_time_iso)
                    if new_rt.tzinfo is None:
                        new_rt = new_rt.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
                await task_repo.set_reminder(session, target.id, new_rt)
                time_str = _format_time_local(action.new_reminder_time_iso, tz_name, lang)
                confirm = (
                    f"✅ Напомню {action.lead_description}: {target.description} ({time_str})"
                    if action.lead_description else f"✅ Напомню в {time_str}: {target.description}"
                )
                await message.answer(confirm)
            else:
                await message.answer("Не нашёл такое напоминание. Используйте /reminders чтобы увидеть список.")
            return

    # ── Semantic search fallback ──────────────────────────────────────────────
    thinking = await message.answer("🔍 Ищу в истории переписок…")
    try:
        query_vec = await embed_text(text)
        results = await msg_repo.search_similar(session, owner_id, query_vec, limit=12)
        if not results:
            await thinking.edit_text("Не нашёл ничего похожего в истории переписок.")
            return
        name_map = await contact_repo.get_name_map(session, owner_id)
        ans = await answer_from_context(text, results, language=lang, name_map=name_map, tz_name=tz_name)
        await thinking.edit_text(ans, parse_mode="HTML")
    except Exception:
        logger.exception("Semantic search fallback failed")
        await thinking.edit_text("❌ Не удалось выполнить поиск.")


async def _handle_pending_email_address(
    owner_id: int,
    text: str,
    message: Message,
    session: AsyncSession,
) -> bool:
    """If owner is providing an email address for a pending email, handle it. Returns True if consumed."""
    pending = _pending_email.get(owner_id)
    if pending is None or "to" in pending:
        return False

    import re
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", text.strip()):
        return False

    email_addr = text.strip()
    contact_id: int | None = pending.get("contact_id")  # type: ignore[assignment]
    if contact_id is not None:
        await contact_repo.set_email(session, owner_id, contact_id, email_addr)

    from services import gmail as gmail_svc
    from services.ai import generate_dispatch_message

    gmail_service = await gmail_svc.get_gmail_service(owner_id, session)
    if gmail_service is None:
        _pending_email.pop(owner_id, None)
        await message.answer("❌ Gmail не подключён.")
        return True

    us = await us_repo.get_or_create(session, owner_id)
    body = pending.get("literal_body") or ""
    if not body:
        style = await get_style_profile(owner_id, [])
        body = await generate_dispatch_message(
            intent=str(pending.get("body_intent") or ""),
            recipient_name=str(pending.get("recipient_name") or ""),
            language=us.language,
            style_profile=style,
        )
    subject = str(pending.get("subject") or "Сообщение из NeuroSave")

    if pending.get("has_attachment"):
        _pending_email[owner_id] = {"to": email_addr, "subject": subject, "body": body}
        await message.answer(f"📎 Прикрепи файл следующим сообщением. Письмо будет отправлено на {email_addr}.")
        return True

    _pending_email.pop(owner_id, None)
    try:
        await gmail_svc.send_email(gmail_service, to=[email_addr], subject=subject, body=body)
        await message.answer(
            f"✅ Письмо отправлено на <b>{email_addr}</b>\n"
            f"<b>Тема:</b> {subject}\n\n{body[:200]}{'…' if len(body) > 200 else ''}",
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.exception("Gmail send failed for owner %d: %s", owner_id, exc)
        await message.answer("❌ Не удалось отправить письмо.")
    return True


@router.message(F.document | F.photo)
async def handle_owner_attachment(message: Message, bot: Bot, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    owner_id = message.from_user.id
    pending = _pending_email.get(owner_id)
    if pending is None or "to" not in pending:
        return

    from services import gmail as gmail_svc

    gmail_service = await gmail_svc.get_gmail_service(owner_id, session)
    if gmail_service is None:
        _pending_email.pop(owner_id, None)
        await message.answer("❌ Gmail не подключён.")
        return

    file_id: str | None = None
    filename = "attachment"
    mime_type = "application/octet-stream"

    if message.document:
        file_id = message.document.file_id
        filename = message.document.file_name or "document"
        mime_type = message.document.mime_type or "application/octet-stream"
    elif message.photo:
        file_id = message.photo[-1].file_id
        filename = "photo.jpg"
        mime_type = "image/jpeg"

    if not file_id:
        return

    try:
        buf = await bot.download(file_id)
        if buf is None:
            await message.answer("❌ Не удалось скачать файл.")
            return
        file_bytes = buf.read()
    except Exception:
        logger.exception("Failed to download attachment")
        await message.answer("❌ Не удалось скачать файл.")
        return

    to = str(pending["to"])
    subject = str(pending.get("subject") or "")
    body = str(pending.get("body") or "")
    _pending_email.pop(owner_id, None)

    try:
        await gmail_svc.send_email(
            gmail_service,
            to=[to],
            subject=subject,
            body=body,
            attachments=[(filename, file_bytes, mime_type)],
        )
        await message.answer(
            f"✅ Письмо с вложением <b>{filename}</b> отправлено на <b>{to}</b>",
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.exception("Gmail send with attachment failed for owner %d: %s", owner_id, exc)
        await message.answer("❌ Не удалось отправить письмо.")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_owner_dispatch(message: Message, bot: Bot, session: AsyncSession) -> None:
    if message.from_user is None or not message.text:
        return
    owner_id = message.from_user.id
    await us_repo.get_or_create(session, owner_id)
    if await _handle_pending_email_address(owner_id, message.text, message, session):
        return
    await _process_owner_text(message.text, message, bot, session, owner_id)


@router.message(F.voice)
async def handle_owner_voice(message: Message, bot: Bot, session: AsyncSession) -> None:
    if message.from_user is None or not message.voice:
        return
    owner_id = message.from_user.id
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
    await us_repo.get_or_create(session, owner_id)
    await _process_owner_text(text, message, bot, session, owner_id)


async def cmd_reminders(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    owner_id = message.from_user.id
    us = await us_repo.get_or_create(session, owner_id)
    active = await task_repo.get_open_tasks(session, owner_id, is_personal=True)
    if not active:
        await message.answer("Активных напоминаний нет.")
        return
    lines = ["⏰ <b>Активные напоминания:</b>"]
    for i, t in enumerate(active, 1):
        time_str = _format_time_local(_task_reminder_iso(t), us.timezone, us.language)
        lines.append(f"{i}. {t.description}" + (f" — {time_str}" if time_str else ""))
    lines.append("\nЧтобы изменить или удалить — напишите, например: «удали напоминание про стрижку» или «перенеси встречу на 8 утра».")
    await message.answer("\n".join(lines), parse_mode="HTML")
