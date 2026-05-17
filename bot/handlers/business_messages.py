from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Coroutine

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config_store import get_language, get_timezone, set_business_connection_id, t
from bot.handlers.ghost import DEFAULT_AWAY_RU, DEFAULT_AWAY_EN
from config import settings
from db.engine import get_session
from db.models import InquiryCategory
from db.repositories import contacts as contact_repo
from db.repositories import ghost as ghost_repo
from db.repositories import messages as msg_repo
from db.repositories import tasks as task_repo
from services.ai import classify_inquiry, embed_text, extract_reminder_from_context, extract_task_from_message

logger = logging.getLogger(__name__)
router = Router()

_bg_tasks: set[asyncio.Task[None]] = set()

# task_id → {chat_id, bcid, bc_msg_id, dm_chat_id, dm_msg_id}
_bc_cancel_store: dict[int, dict[str, object]] = {}

_REMIND_KEYWORDS = {"напомни", "remind", "напоминание", "reminder", "поставь напомни"}


def _fire(coro: Coroutine[Any, Any, None]) -> None:
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


def _is_remind_trigger(text: str) -> bool:
    lower = text.lower().strip()
    return any(kw in lower for kw in _REMIND_KEYWORDS)


async def _embed_message(message_id: int, text: str) -> None:
    try:
        vec = await embed_text(text)
        async with get_session() as session:
            await msg_repo.set_embedding(session, message_id, vec)
    except Exception:
        logger.warning("Embedding failed for message %d", message_id, exc_info=True)


async def _send_and_delete(
    bot: Bot,
    chat_id: int,
    text: str,
    business_connection_id: str | None,
    delay: int = 5,
) -> None:
    try:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=text,
            business_connection_id=business_connection_id,
        )
        logger.debug("Sent notification msg_id=%d to chat %d", sent.message_id, chat_id)
        await asyncio.sleep(delay)
        if business_connection_id:
            await bot.delete_business_messages(
                business_connection_id=business_connection_id,
                message_ids=[sent.message_id],
            )
        else:
            await bot.delete_message(chat_id=chat_id, message_id=sent.message_id)
        logger.debug("Deleted notification msg_id=%d from chat %d", sent.message_id, chat_id)
    except Exception:
        logger.warning("Notification send/delete failed for chat %d", chat_id, exc_info=True)


async def _handle_remind_trigger(
    bot: Bot,
    message: Message,
    session: AsyncSession,
) -> None:
    """Owner typed 'remind me' in a business chat — create a reminder from context."""
    bcid = message.business_connection_id
    lang = get_language()
    tz_name = get_timezone()

    # Get context: replied-to message, or most recent message in this chat from DB
    context_text: str | None = None
    if message.reply_to_message and message.reply_to_message.text:
        context_text = message.reply_to_message.text
    else:
        recent = await msg_repo.get_recent_messages_in_chat(
            session, settings.owner_chat_id, message.chat.id, limit=1
        )
        if recent:
            context_text = recent[0].text

    if not context_text:
        return

    try:
        parsed = await extract_reminder_from_context(
            context_text=context_text,
            trigger_text=message.text or "напомни",
            language=lang,
            tz_name=tz_name,
        )
    except Exception:
        logger.exception("extract_reminder_from_context failed")
        return

    if not parsed.is_reminder or not parsed.reminder_text:
        return

    from datetime import datetime, timezone as _tz
    iso = parsed.reminder_time_iso or parsed.scheduled_at_iso
    reminder_time: datetime | None = None
    if iso:
        try:
            reminder_time = datetime.fromisoformat(iso)
            if reminder_time.tzinfo is None:
                reminder_time = reminder_time.replace(tzinfo=_tz.utc)
        except ValueError:
            pass
    deadline: datetime | None = None
    if parsed.event_time_iso:
        try:
            deadline = datetime.fromisoformat(parsed.event_time_iso)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=_tz.utc)
        except ValueError:
            pass

    await task_repo.create_personal_task(
        session,
        owner_id=settings.owner_chat_id,
        description=parsed.reminder_text,
        deadline=deadline,
        reminder_time=reminder_time,
    )

    # Send confirmation in the business chat, then delete trigger + confirmation
    try:
        sent = await bot.send_message(
            chat_id=message.chat.id,
            text="📌 Добавлено в напоминания",
            business_connection_id=bcid,
        )
        await asyncio.sleep(3)
        if bcid:
            ids = [sent.message_id, message.message_id]
            await bot.delete_business_messages(
                business_connection_id=bcid,
                message_ids=ids,
            )
    except Exception:
        logger.warning("Could not send/delete reminder confirmation in chat %d", message.chat.id)


@router.business_message()
async def handle_business_message(
    message: Message, bot: Bot, session: AsyncSession
) -> None:
    if not message.text:
        return

    sender_id = message.from_user.id if message.from_user else None
    sender_name = message.from_user.full_name if message.from_user else None
    sender_username = message.from_user.username if message.from_user else None

    if message.business_connection_id:
        set_business_connection_id(message.business_connection_id)

    if message.chat.type == "private" and message.chat.id != settings.owner_chat_id:
        await contact_repo.upsert_contact(
            session,
            owner_id=settings.owner_chat_id,
            user_id=message.chat.id,
            name=message.chat.full_name,
            username=message.chat.username,
            has_business_chat=True,
        )

    saved_msg = await msg_repo.save_message(
        session,
        owner_id=settings.owner_chat_id,
        chat_id=message.chat.id,
        message_id=message.message_id,
        sender_id=sender_id,
        sender_name=sender_name,
        text=message.text,
        timestamp=message.date,
    )
    display_name = sender_name
    if sender_id and sender_id != settings.owner_chat_id:
        contact = await contact_repo.get_contact(session, settings.owner_chat_id, sender_id)
        if contact and contact.saved_name:
            display_name = contact.saved_name
    embed_text = f"{display_name}: {message.text}" if display_name else message.text
    _fire(_embed_message(saved_msg.id, embed_text))

    is_incoming = sender_id != settings.owner_chat_id
    is_in_business_chat = message.chat.id != settings.owner_chat_id

    # ── Owner "remind me" trigger in a business chat ─────────────────────────
    if not is_incoming and is_in_business_chat and _is_remind_trigger(message.text):
        _fire(_handle_remind_trigger(bot, message, session))
        return

    # ── Ghost Mode for incoming messages ─────────────────────────────────────
    if is_incoming and sender_id is not None:
        gs = await ghost_repo.get_session(session, settings.owner_chat_id)
        if gs and gs.is_active:
            is_vip = False
            if sender_name:
                contacts = await contact_repo.find_contacts_by_name(
                    session, owner_id=settings.owner_chat_id, name=sender_name
                )
                is_vip = contacts[0].is_vip if contacts else False

            if not is_vip:
                lang = get_language()
                bcid = message.business_connection_id
                session_start = gs.activated_at or datetime.min.replace(tzinfo=timezone.utc)
                existing = await ghost_repo.get_session_inquiry(
                    session, settings.owner_chat_id, sender_id, since=session_start
                )

                if existing is None:
                    # First message in this ghost session — classify and send away reply
                    try:
                        category, summary, has_question = await classify_inquiry(message.text, language=lang)
                        if category == InquiryCategory.spam:
                            return  # Confirmed spam — no reply, no log
                    except Exception:
                        logger.exception("classify_inquiry failed for chat %d", message.chat.id)
                        category, summary, has_question = InquiryCategory.team, "", True

                    if not gs.silent_mode:
                        away = gs.away_message or (DEFAULT_AWAY_RU if lang == "ru" else DEFAULT_AWAY_EN)
                        try:
                            await bot.send_message(
                                chat_id=message.chat.id,
                                text=away,
                                business_connection_id=bcid,
                            )
                        except Exception:
                            logger.warning("Ghost auto-reply failed for chat %d", message.chat.id)

                    if has_question:
                        inquiry = await ghost_repo.create_inquiry(
                            session,
                            owner_id=settings.owner_chat_id,
                            caller_id=sender_id,
                            caller_name=sender_name,
                            caller_username=sender_username,
                            chat_id=message.chat.id,
                        )
                        await ghost_repo.resolve_inquiry(session, inquiry, summary, category)
                    else:
                        await ghost_repo.create_inquiry(
                            session,
                            owner_id=settings.owner_chat_id,
                            caller_id=sender_id,
                            caller_name=sender_name,
                            caller_username=sender_username,
                            chat_id=message.chat.id,
                        )
                    return

                elif existing.ghost_pending:
                    # Follow-up message — classify and resolve
                    try:
                        category, summary, _ = await classify_inquiry(message.text, language=lang)
                        await ghost_repo.resolve_inquiry(session, existing, summary, category)
                    except Exception:
                        logger.exception("classify_inquiry failed for chat %d", message.chat.id)
                    return

                else:
                    # Already collected in this session — ignore
                    return

    # ── Task extraction (outgoing messages only — owner assigns tasks to others) ──
    if is_incoming:
        return

    try:
        extracted = await extract_task_from_message(
            message.text, language=get_language(), tz_name=get_timezone()
        )
    except Exception:
        logger.exception("Task extraction failed for message %d", message.message_id)
        return

    if not extracted.has_task or not extracted.description:
        return

    deadline: datetime | None = None
    if extracted.deadline_iso:
        try:
            deadline = datetime.fromisoformat(extracted.deadline_iso)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
        except ValueError:
            logger.warning("Could not parse deadline: %s", extracted.deadline_iso)

    # In a 1:1 business chat, chat.id IS the contact's Telegram user_id
    is_private_business_chat = (
        message.chat.type == "private" and message.chat.id != settings.owner_chat_id
    )
    new_task = await task_repo.create_task(
        session,
        owner_id=settings.owner_chat_id,
        chat_id=message.chat.id,
        message_id=message.message_id,
        description=extracted.description,
        assignee_name=extracted.assignee_name,
        assignee_user_id=message.chat.id if is_private_business_chat else None,
        assignee_username=message.chat.username if is_private_business_chat else None,
        deadline=deadline,
        business_connection_id=message.business_connection_id,
    )

    _fire(_notify_task_created(
        bot=bot,
        task_id=new_task.id,
        description=new_task.description,
        assignee_name=new_task.assignee_name,
        deadline=new_task.deadline,
        chat_id=message.chat.id,
        bcid=message.business_connection_id,
        owner_id=settings.owner_chat_id,
    ))


async def _notify_task_created(
    bot: Bot,
    task_id: int,
    description: str,
    assignee_name: str | None,
    deadline: "datetime | None",
    chat_id: int,
    bcid: str | None,
    owner_id: int,
) -> None:
    """Send task notification in business chat + owner DM, store IDs for cross-cancel."""
    # ── Business chat: inline ❌ button ───────────────────────────────────────
    bc_msg_id: int | None = None
    try:
        bc_sent = await bot.send_message(
            chat_id=chat_id,
            text="📝 Задача добавлена",
            business_connection_id=bcid,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="❌ Отменить", callback_data=f"bc_cancel:{task_id}")
            ]]),
        )
        bc_msg_id = bc_sent.message_id
    except Exception:
        logger.warning("Could not send business chat task notif to chat %d", chat_id)

    # ── Owner DM: inline ❌ button ────────────────────────────────────────────
    dm_text = f"📝 <b>Задача добавлена</b>\n{description}"
    if assignee_name:
        dm_text += f"\n👤 {assignee_name}"
    if deadline:
        dm_text += f"\n📅 {deadline.strftime('%d.%m %H:%M')}"
    dm_msg_id: int | None = None
    try:
        dm_sent = await bot.send_message(
            chat_id=owner_id,
            text=dm_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="❌ Отменить задачу", callback_data=f"task_cancel:{task_id}")
            ]]),
        )
        dm_msg_id = dm_sent.message_id
    except Exception:
        logger.warning("Could not send DM task notif to owner %d", owner_id)

    # Store for cross-cancellation
    _bc_cancel_store[task_id] = {
        "chat_id": chat_id,
        "bcid": bcid,
        "bc_msg_id": bc_msg_id,
        "dm_chat_id": owner_id,
        "dm_msg_id": dm_msg_id,
    }


@router.callback_query(F.data.startswith("bc_cancel:"))
async def handle_bc_cancel(
    query: CallbackQuery, session: AsyncSession
) -> None:
    """User tapped ❌ on the business chat task notification."""
    if query.data is None:
        await query.answer()
        return

    task_id = int(query.data.split(":")[1])
    task = await task_repo.cancel_task(session, task_id)
    entry = _bc_cancel_store.pop(task_id, None)

    if not task:
        await query.answer("Задача уже отменена")
        return

    await query.answer("Задача отменена")

    # Edit the business chat message to show cancellation
    if isinstance(query.message, Message):
        try:
            await query.message.edit_text("❌ Задача отменена", reply_markup=None)
        except Exception:
            pass

    # Sync: update the DM notification (remove button, show cancelled)
    if entry:
        dm_chat_id = entry.get("dm_chat_id")
        dm_msg_id = entry.get("dm_msg_id")
        if dm_chat_id and dm_msg_id:
            try:
                await query.bot.edit_message_text(
                    chat_id=int(dm_chat_id),
                    message_id=int(dm_msg_id),
                    text=f"❌ <b>Задача отменена</b>\n{task.description}",
                    parse_mode="HTML",
                    reply_markup=None,
                )
            except Exception:
                pass
