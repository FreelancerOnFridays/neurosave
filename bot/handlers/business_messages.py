from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Coroutine

from aiogram import Bot, F, Router
from aiogram.types import BusinessConnection, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.ghost import DEFAULT_AWAY_RU, DEFAULT_AWAY_EN, DEFAULT_AWAY_UA
from db.engine import get_session
from db.models import InquiryCategory
from db.repositories import contacts as contact_repo
from db.repositories import ghost as ghost_repo
from db.repositories import messages as msg_repo
from db.repositories import tasks as task_repo
from db.repositories import user_settings as us_repo
from services.ai import classify_inquiry, embed_text, extract_reminder_from_context, extract_task_from_message

logger = logging.getLogger(__name__)
router = Router()

_bg_tasks: set[asyncio.Task[None]] = set()

# task_id → {chat_id, bcid, bc_msg_id, dm_chat_id, dm_msg_id}
_bc_cancel_store: dict[int, dict[str, object]] = {}

# confirm_id → {description, deadline, reminder_time, bcid, chat_id}
_PENDING_REMINDS: dict[str, dict[str, object]] = {}

_REMIND_KEYWORDS = {"напомни", "remind", "напоминание", "reminder", "поставь напомни"}
_DELEGATION_KEYWORDS = {"задача", "задачу", "задание"}

# Map contact label → ghost inquiry category (lower-case keys)
_LABEL_CATEGORIES: dict[str, InquiryCategory] = {
    "команда": InquiryCategory.team,
    "team": InquiryCategory.team,
    "срочно": InquiryCategory.urgent,
    "urgent": InquiryCategory.urgent,
    "продажи": InquiryCategory.sales,
    "sales": InquiryCategory.sales,
    "спам": InquiryCategory.spam,
    "spam": InquiryCategory.spam,
}


def _label_to_category(labels: list[str]) -> InquiryCategory | None:
    for label in labels:
        cat = _LABEL_CATEGORIES.get(label.lower())
        if cat:
            return cat
    return None


def _fire(coro: Coroutine[Any, Any, None]) -> None:
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def _resolve_owner(bcid: str | None, bot: Bot, session: AsyncSession) -> int | None:
    """Return owner_id for a business_connection_id. Falls back to Telegram API if not in DB."""
    if not bcid:
        return None
    owner_id = await us_repo.get_owner_by_bcid(session, bcid)
    if owner_id:
        return owner_id
    try:
        bc = await bot.get_business_connection(business_connection_id=bcid)
        owner_id = bc.user.id
        await us_repo.get_or_create(session, owner_id)
        await us_repo.update_settings(session, owner_id, business_connection_id=bcid)
        return owner_id
    except Exception:
        logger.exception("Could not resolve owner for bcid=%s", bcid)
        return None


@router.business_connection()
async def handle_business_connection(event: BusinessConnection, session: AsyncSession) -> None:
    """Store business_connection_id → owner mapping when a user connects the bot."""
    owner_id = event.user.id
    await us_repo.get_or_create(session, owner_id)
    if event.is_enabled:
        await us_repo.update_settings(session, owner_id, business_connection_id=event.id)
        logger.info("Business connection stored: owner=%d bcid=%s", owner_id, event.id)
    else:
        await us_repo.update_settings(session, owner_id, business_connection_id=None)
        logger.info("Business connection removed: owner=%d", owner_id)


def _is_remind_trigger(text: str) -> bool:
    lower = text.lower().strip()
    return any(kw in lower for kw in _REMIND_KEYWORDS)


def _has_delegation_keyword(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _DELEGATION_KEYWORDS)


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


async def _handle_remind_trigger(bot: Bot, message: Message, owner_id: int, lang: str, tz_name: str) -> None:
    """Owner's message contains 'напомни' — extract task and ask for confirmation."""
    bcid = message.business_connection_id

    # Use replied-to message as context if available; otherwise use the message text itself
    if message.reply_to_message and message.reply_to_message.text:
        context_text = message.reply_to_message.text
    else:
        context_text = message.text or ""
    trigger_text = message.text or "напомни"

    if not context_text.strip():
        return

    try:
        parsed = await extract_reminder_from_context(
            context_text=context_text,
            trigger_text=trigger_text,
            language=lang,
            tz_name=tz_name,
        )
    except Exception:
        logger.exception("extract_reminder_from_context failed")
        return

    if not parsed.is_reminder or not parsed.reminder_text:
        return

    from datetime import datetime, timezone as _tz
    from zoneinfo import ZoneInfo
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

    # Default deadline = today midnight when no explicit time given
    if deadline is None and reminder_time is None:
        try:
            tz = ZoneInfo(tz_name)
            today_local = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
            deadline = today_local.astimezone(_tz.utc)
        except Exception:
            pass

    confirm_id = f"{message.chat.id}_{message.message_id}"
    _PENDING_REMINDS[confirm_id] = {
        "description": parsed.reminder_text,
        "deadline": deadline,
        "reminder_time": reminder_time,
        "bcid": bcid,
        "chat_id": message.chat.id,
        "trigger_msg_id": message.message_id,
    }

    # Show task preview in confirmation message
    preview = parsed.reminder_text[:60] + ("…" if len(parsed.reminder_text) > 60 else "")
    if lang == "ua":
        yes_label, no_label = "✅ Так", "❌ Ні"
        confirm_text = f"📌 <b>Додати до завдань?</b>\n<i>{preview}</i>"
    elif lang == "ru":
        yes_label, no_label = "✅ Да", "❌ Нет"
        confirm_text = f"📌 <b>Добавить в задачи?</b>\n<i>{preview}</i>"
    else:
        yes_label, no_label = "✅ Yes", "❌ No"
        confirm_text = f"📌 <b>Add to tasks?</b>\n<i>{preview}</i>"
    try:
        confirm_sent = await bot.send_message(
            chat_id=message.chat.id,
            text=confirm_text,
            parse_mode="HTML",
            business_connection_id=bcid,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=yes_label, callback_data=f"remind_yes:{confirm_id}"),
                InlineKeyboardButton(text=no_label, callback_data=f"remind_no:{confirm_id}"),
            ]]),
        )
    except Exception:
        logger.warning("Could not send remind confirmation for chat %d", message.chat.id)
        _PENDING_REMINDS.pop(confirm_id, None)
        return

    # Auto-expire after 5 seconds — delete bot confirmation + user's trigger message
    async def _expire_remind() -> None:
        await asyncio.sleep(5)
        if _PENDING_REMINDS.pop(confirm_id, None) is not None:
            try:
                if bcid:
                    await bot.delete_business_messages(
                        business_connection_id=bcid,
                        message_ids=[confirm_sent.message_id, message.message_id],
                    )
                else:
                    await bot.delete_message(chat_id=message.chat.id, message_id=confirm_sent.message_id)
            except Exception:
                pass

    _fire(_expire_remind())


async def _extract_and_create_task(bot: Bot, message: Message, owner_id: int, lang: str, tz_name: str) -> None:
    """Background task: extract delegated task from outgoing message and notify."""
    own_text = (message.text or "").strip()

    # When user replies to a message with just "задача", use the replied-to text as context
    replied_text: str | None = None
    if message.reply_to_message and message.reply_to_message.text:
        replied_text = message.reply_to_message.text.strip()

    # Build context: if own text is only the keyword, use replied message; otherwise combine
    if replied_text and _has_delegation_keyword(own_text) and len(own_text) < 20:
        extraction_text = replied_text
    elif replied_text:
        extraction_text = replied_text + "\n" + own_text
    else:
        extraction_text = own_text

    try:
        extracted = await extract_task_from_message(
            extraction_text, language=lang, tz_name=tz_name
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

    is_private_business_chat = (
        message.chat.type == "private" and message.chat.id != owner_id
    )
    async with get_session() as session:
        new_task = await task_repo.create_task(
            session,
            owner_id=owner_id,
            chat_id=message.chat.id,
            message_id=message.message_id,
            description=extracted.description,
            assignee_name=extracted.assignee_name,
            assignee_user_id=message.chat.id if is_private_business_chat else None,
            assignee_username=message.chat.username if is_private_business_chat else None,
            deadline=deadline,
            business_connection_id=message.business_connection_id,
        )
        # Read inside session to avoid DetachedInstanceError after close
        task_id = new_task.id
        task_desc = new_task.description
        task_assignee = new_task.assignee_name
        task_deadline = new_task.deadline

    _fire(_notify_task_created(
        bot=bot,
        task_id=task_id,
        description=task_desc,
        assignee_name=task_assignee,
        deadline=task_deadline,
        chat_id=message.chat.id,
        bcid=message.business_connection_id,
        owner_id=owner_id,
        trigger_msg_id=message.message_id,
    ))


@router.business_message()
async def handle_business_message(
    message: Message, bot: Bot, session: AsyncSession
) -> None:
    if not message.text:
        return

    owner_id = await _resolve_owner(message.business_connection_id, bot, session)
    if owner_id is None:
        return

    us = await us_repo.get_or_create(session, owner_id)
    lang = us.language
    tz_name = us.timezone

    sender_id = message.from_user.id if message.from_user else None
    sender_name = message.from_user.full_name if message.from_user else None
    sender_username = message.from_user.username if message.from_user else None

    if message.chat.type == "private" and message.chat.id != owner_id:
        await contact_repo.upsert_contact(
            session,
            owner_id=owner_id,
            user_id=message.chat.id,
            name=message.chat.full_name,
            username=message.chat.username,
            has_business_chat=True,
        )

    saved_msg = await msg_repo.save_message(
        session,
        owner_id=owner_id,
        chat_id=message.chat.id,
        message_id=message.message_id,
        sender_id=sender_id,
        sender_name=sender_name,
        text=message.text,
        timestamp=message.date,
    )
    display_name = sender_name
    if sender_id and sender_id != owner_id:
        contact = await contact_repo.get_contact(session, owner_id, sender_id)
        if contact and contact.saved_name:
            display_name = contact.saved_name
    embed_str = f"{display_name}: {message.text}" if display_name else message.text
    _fire(_embed_message(saved_msg.id, embed_str))

    is_incoming = sender_id != owner_id
    is_in_business_chat = message.chat.id != owner_id

    # ── Owner "напомни" in a business chat — ask confirmation before saving task ─
    if not is_incoming and is_in_business_chat and _is_remind_trigger(message.text):
        _fire(_handle_remind_trigger(bot, message, owner_id, lang, tz_name))
        return

    # ── Ghost Mode for incoming messages ─────────────────────────────────────
    if is_incoming and sender_id is not None:
        gs = await ghost_repo.get_session(session, owner_id)
        if gs and gs.is_active:
            is_vip = False
            if sender_name:
                contacts = await contact_repo.find_contacts_by_name(
                    session, owner_id=owner_id, name=sender_name
                )
                is_vip = contacts[0].is_vip if contacts else False

            if not is_vip:
                bcid = message.business_connection_id
                session_start = gs.activated_at or datetime.min.replace(tzinfo=timezone.utc)
                existing = await ghost_repo.get_session_inquiry(
                    session, owner_id, sender_id, since=session_start
                )

                if existing is None:
                    # First message in this ghost session — classify and send away reply
                    # Check if this is a known contact (current message already saved → ≥2 means prior history)
                    recent_msgs = await msg_repo.get_recent_messages_in_chat(
                        session, owner_id, message.chat.id, limit=2
                    )
                    is_known_contact = len(recent_msgs) >= 2

                    # Fetch contact record early — needed for spam guard, label override, and context hints
                    contact_for_label = await contact_repo.get_contact(session, owner_id, sender_id)
                    has_labels = bool(contact_for_label and contact_for_label.labels)
                    contact_labels_list = list(contact_for_label.labels) if contact_for_label and contact_for_label.labels else []

                    # Step 1: AI classification with full context
                    try:
                        ai_category, summary, has_question = await classify_inquiry(
                            message.text,
                            language=lang,
                            is_known_contact=is_known_contact,
                            labels=contact_labels_list or None,
                        )
                        if ai_category == InquiryCategory.spam:
                            if is_known_contact:
                                ai_category = InquiryCategory.normal
                            elif not has_labels:
                                return  # Truly unknown unlabeled bot/spam — discard
                    except Exception:
                        logger.exception("classify_inquiry failed for chat %d", message.chat.id)
                        ai_category, summary, has_question = InquiryCategory.team, "", True

                    # Step 2: Greeting-only messages → "Не срочно"
                    if not has_question:
                        ai_category = InquiryCategory.normal

                    # Step 3: Contact labels override category
                    if contact_for_label and contact_for_label.labels:
                        label_cat = _label_to_category(contact_for_label.labels)
                        category = label_cat if label_cat is not None else ai_category
                    else:
                        category = ai_category

                    # Step 4: Check auto-reply exclusions
                    excluded_ids: list[int] = gs.excluded_contact_ids or []
                    excluded_lbls: list[str] = [l.lower() for l in (gs.excluded_labels or [])]
                    contact_labels_lower = [l.lower() for l in (contact_for_label.labels if contact_for_label else [])]
                    skip_reply = (
                        sender_id in excluded_ids
                        or any(l in excluded_lbls for l in contact_labels_lower)
                    )

                    if not gs.silent_mode and not skip_reply:
                        away = gs.away_message or (
                            DEFAULT_AWAY_UA if lang == "ua" else
                            DEFAULT_AWAY_RU if lang == "ru" else
                            DEFAULT_AWAY_EN
                        )
                        try:
                            await bot.send_message(
                                chat_id=message.chat.id,
                                text=away,
                                business_connection_id=bcid,
                            )
                        except Exception:
                            logger.warning("Ghost auto-reply failed for chat %d", message.chat.id)

                    inquiry = await ghost_repo.create_inquiry(
                        session,
                        owner_id=owner_id,
                        caller_id=sender_id,
                        caller_name=sender_name,
                        caller_username=sender_username,
                        chat_id=message.chat.id,
                    )
                    await ghost_repo.resolve_inquiry(session, inquiry, summary, category)
                    return

                elif existing.ghost_pending:
                    # Follow-up message — AI classifies, labels override
                    contact_for_label2 = await contact_repo.get_contact(session, owner_id, sender_id)
                    labels2 = list(contact_for_label2.labels) if contact_for_label2 and contact_for_label2.labels else []
                    try:
                        ai_cat2, summary2, has_question2 = await classify_inquiry(
                            message.text,
                            language=lang,
                            is_known_contact=True,
                            labels=labels2 or None,
                        )
                        if ai_cat2 == InquiryCategory.spam:
                            ai_cat2 = InquiryCategory.normal
                    except Exception:
                        logger.exception("classify_inquiry failed for chat %d", message.chat.id)
                        ai_cat2, summary2, has_question2 = InquiryCategory.team, "", True
                    if not has_question2:
                        ai_cat2 = InquiryCategory.normal
                    if contact_for_label2 and contact_for_label2.labels:
                        label_cat2 = _label_to_category(contact_for_label2.labels)
                        final_cat2 = label_cat2 if label_cat2 is not None else ai_cat2
                    else:
                        final_cat2 = ai_cat2
                    await ghost_repo.resolve_inquiry(session, existing, summary2, final_cat2)
                    return

                else:
                    # Already collected in this session — ignore
                    return

    # ── Task extraction (outgoing messages only — owner assigns tasks to others) ──
    if is_incoming:
        return

    # Only extract delegated tasks when the owner explicitly uses the word "задача"
    if _has_delegation_keyword(message.text or ""):
        _fire(_extract_and_create_task(bot, message, owner_id, lang, tz_name))


async def _notify_task_created(
    bot: Bot,
    task_id: int,
    description: str,
    assignee_name: str | None,
    deadline: "datetime | None",
    chat_id: int,
    bcid: str | None,
    owner_id: int,
    trigger_msg_id: int | None = None,
) -> None:
    """Send task notification in business chat + owner DM, store IDs for cross-cancel."""
    # ── Business chat: ephemeral ❌ button, auto-deletes after 5 s ─────────────
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
        # Schedule deletion in background so we don't block the DM send below
        async def _delete_bc() -> None:
            await asyncio.sleep(5)
            try:
                ids = [bc_sent.message_id]
                if trigger_msg_id is not None:
                    ids.append(trigger_msg_id)
                if bcid:
                    await bot.delete_business_messages(
                        business_connection_id=bcid, message_ids=ids
                    )
                else:
                    for mid in ids:
                        await bot.delete_message(chat_id=chat_id, message_id=mid)
            except Exception:
                pass
        _fire(_delete_bc())
    except Exception:
        logger.warning("Could not send business chat task notif to chat %d", chat_id)

    # ── Owner DM: inline ❌ button ────────────────────────────────────────────
    dm_text = f"📝 <b>Задача добавлена</b>\n{description}"
    if assignee_name:
        dm_text += f"\n👤 {assignee_name}"
    if deadline:
        dm_text += f"\n📅 Дедлайн: {deadline.strftime('%d.%m в %H:%M')}"
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


@router.callback_query(F.data.startswith("remind_yes:"))
async def handle_remind_yes(query: CallbackQuery) -> None:
    """Owner confirmed adding the pending reminder as a task."""
    if query.data is None:
        await query.answer()
        return
    confirm_id = query.data.split(":", 1)[1]
    data = _PENDING_REMINDS.pop(confirm_id, None)
    if data is None:
        await query.answer("Время вышло")
        return

    if query.from_user is None:
        return
    owner_id = query.from_user.id
    await query.answer()

    # Create the task with its own fresh session (avoids the middleware-session lifetime issue)
    async with get_session() as db:
        await task_repo.create_personal_task(
            db,
            owner_id=owner_id,
            description=str(data["description"]),
            deadline=data.get("deadline"),  # type: ignore[arg-type]
            reminder_time=data.get("reminder_time"),  # type: ignore[arg-type]
        )

    # Edit confirmation message then delete bot + trigger messages after 2 seconds
    bcid_val = data.get("bcid")
    trigger_id = data.get("trigger_msg_id")
    if isinstance(query.message, Message):
        try:
            await query.message.edit_text("📌 Добавлено в задачи", reply_markup=None)
            await asyncio.sleep(2)
            if bcid_val:
                ids = [query.message.message_id]
                if trigger_id:
                    ids.append(int(trigger_id))
                await query.bot.delete_business_messages(
                    business_connection_id=str(bcid_val),
                    message_ids=ids,
                )
            else:
                await query.message.delete()
        except Exception:
            pass


@router.callback_query(F.data.startswith("remind_no:"))
async def handle_remind_no(query: CallbackQuery) -> None:
    """Owner declined adding the pending reminder."""
    if query.data is None:
        await query.answer()
        return
    confirm_id = query.data.split(":", 1)[1]
    data = _PENDING_REMINDS.pop(confirm_id, None)
    bcid_val = data.get("bcid") if data else None
    trigger_id = data.get("trigger_msg_id") if data else None

    await query.answer()

    if isinstance(query.message, Message):
        try:
            await query.message.edit_text("✖️ Не добавлено", reply_markup=None)
            await asyncio.sleep(2)
            if bcid_val:
                ids = [query.message.message_id]
                if trigger_id:
                    ids.append(int(trigger_id))
                await query.bot.delete_business_messages(
                    business_connection_id=str(bcid_val),
                    message_ids=ids,
                )
            else:
                await query.message.delete()
        except Exception:
            pass


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

    # Edit DM message to show cancelled (remove button, keep message in bot chat)
    if isinstance(query.message, Message):
        try:
            await query.message.edit_text(
                f"❌ <b>Задача отменена</b>\n{task.description}",
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception:
            pass

    # Send ephemeral "❌ Задача отменена" to the business chat and delete after 5s
    if entry:
        bc_chat_id = entry.get("chat_id")
        bcid = entry.get("bcid")
        if bc_chat_id and bcid:
            async def _send_cancel_to_bc(cid: int, bid: str, desc: str) -> None:
                try:
                    sent = await query.bot.send_message(
                        chat_id=cid,
                        text="❌ Задача отменена",
                        business_connection_id=bid,
                    )
                    await asyncio.sleep(5)
                    await query.bot.delete_business_messages(
                        business_connection_id=bid,
                        message_ids=[sent.message_id],
                    )
                except Exception:
                    pass
            _fire(_send_cancel_to_bc(int(bc_chat_id), str(bcid), task.description))
