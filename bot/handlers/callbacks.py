from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message as TgMessage
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config_store import t
from bot.schedule import build_today_schedule
from db.repositories import contacts as contact_repo
from db.repositories import ghost as ghost_repo
from db.repositories import messages as msg_repo
from db.repositories import tasks as task_repo
from db.repositories import user_settings as us_repo
from services.ai import generate_nudge_message, get_style_profile

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data.startswith("task_cancel:"))
async def handle_task_cancel(
    query: CallbackQuery, bot: Bot, session: AsyncSession
) -> None:
    if query.data is None:
        await query.answer()
        return
    task_id = int(query.data.split(":")[1])
    task = await task_repo.cancel_task(session, task_id)
    if task:
        await query.answer("Задача отменена")
        if isinstance(query.message, TgMessage):
            await query.message.edit_text(
                f"❌ <b>Задача отменена</b>\n{task.description}",
                parse_mode="HTML",
                reply_markup=None,
            )
        # Sync: delete the business chat notification if still present
        from bot.handlers.business_messages import _bc_cancel_store
        entry = _bc_cancel_store.pop(task_id, None)
        if entry:
            bcid = entry.get("bcid")
            bc_msg_id = entry.get("bc_msg_id")
            bc_chat_id = entry.get("chat_id")
            if bcid and bc_msg_id:
                try:
                    await bot.delete_business_messages(
                        business_connection_id=str(bcid),
                        message_ids=[int(bc_msg_id)],
                    )
                except Exception:
                    pass
            elif bc_chat_id and bc_msg_id:
                try:
                    await bot.delete_message(chat_id=int(bc_chat_id), message_id=int(bc_msg_id))
                except Exception:
                    pass
    else:
        await query.answer(t("task_not_found"))


@router.callback_query(F.data.startswith("task_done:"))
async def handle_task_done(
    query: CallbackQuery, session: AsyncSession
) -> None:
    if query.data is None:
        await query.answer()
        return
    task_id = int(query.data.split(":")[1])
    task = await task_repo.mark_task_done(session, task_id)
    if task:
        await query.answer(t("task_done_answer"))
        if isinstance(query.message, TgMessage):
            await query.message.delete()
    else:
        await query.answer(t("task_not_found"))


@router.callback_query(F.data.startswith("task_delete:"))
async def handle_task_delete(
    query: CallbackQuery, session: AsyncSession
) -> None:
    if query.data is None:
        await query.answer()
        return
    task_id = int(query.data.split(":")[1])
    deleted = await task_repo.delete_task(session, task_id)
    if deleted:
        await query.answer(t("task_deleted_answer"))
        if isinstance(query.message, TgMessage):
            await query.message.delete()
    else:
        await query.answer(t("task_not_found"))


@router.callback_query(F.data.startswith("task_nudge:"))
async def handle_task_nudge(
    query: CallbackQuery, bot: Bot, session: AsyncSession
) -> None:
    if query.data is None:
        await query.answer()
        return
    task_id = int(query.data.split(":")[1])
    task = await task_repo.get_task(session, task_id)
    if task is None:
        await query.answer(t("task_not_found"))
        return

    owner_id = query.from_user.id if query.from_user else 0
    us = await us_repo.get_or_create(session, owner_id)
    recent = await msg_repo.get_recent_owner_messages(session, owner_id)
    style = await get_style_profile(owner_id, [m.text for m in recent])

    try:
        nudge_text = await generate_nudge_message(
            description=task.description,
            assignee_name=task.assignee_name,
            deadline=task.deadline,
            language=us.language,
            style_profile=style,
        )
    except Exception:
        logger.exception("Failed to generate nudge for task %d", task_id)
        nudge_text = task.description

    try:
        await bot.send_message(
            chat_id=task.chat_id,
            text=nudge_text,
            business_connection_id=task.business_connection_id,
        )
        await query.answer(t("nudge_sent"))
    except Exception:
        logger.exception("Failed to send nudge for task %d", task_id)
        await query.answer(t("nudge_failed"))


@router.callback_query(F.data == "send_preview_send")
async def handle_send_preview_send(
    query: CallbackQuery, bot: Bot, session: AsyncSession
) -> None:
    if query.from_user is None or not isinstance(query.message, TgMessage):
        await query.answer()
        return
    owner_id = query.from_user.id
    from bot.handlers.direct_messages import _pending_send_preview, _execute_send_from_preview
    data = _pending_send_preview.pop(owner_id, None)
    if data is None:
        await query.answer()
        return
    await query.answer("Отправляю…")
    await _execute_send_from_preview(owner_id, data, bot, session, query.message)


@router.callback_query(F.data == "send_preview_edit")
async def handle_send_preview_edit(query: CallbackQuery) -> None:
    if query.from_user is None or not isinstance(query.message, TgMessage):
        await query.answer()
        return
    owner_id = query.from_user.id
    from bot.handlers.direct_messages import _pending_send_preview
    data = _pending_send_preview.get(owner_id)
    if data is None:
        await query.answer()
        return
    first_name = data["contacts"][0]["name"] if data["contacts"] else "получателя"
    data["edit_mode"] = True
    data["conf_msg_id"] = query.message.message_id
    await query.answer()
    await query.message.edit_text(
        f"✏️ Отправьте новый текст для <b>{first_name}</b>:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔄 Сгенерировать", callback_data="send_preview_generate"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="send_preview_cancel"),
        ]]),
    )


@router.callback_query(F.data == "send_preview_cancel")
async def handle_send_preview_cancel(query: CallbackQuery) -> None:
    if query.from_user is not None:
        from bot.handlers.direct_messages import _pending_send_preview
        _pending_send_preview.pop(query.from_user.id, None)
    await query.answer()
    if isinstance(query.message, TgMessage):
        try:
            await query.message.delete()
        except Exception:
            pass


@router.callback_query(F.data == "send_preview_generate")
async def handle_send_preview_generate(query: CallbackQuery) -> None:
    if query.from_user is None or not isinstance(query.message, TgMessage):
        await query.answer()
        return
    owner_id = query.from_user.id
    from bot.handlers.direct_messages import _pending_send_preview
    from services.ai import generate_dispatch_message
    data = _pending_send_preview.get(owner_id)
    if data is None:
        await query.answer()
        return
    await query.answer("Генерирую…")
    first_name = data["contacts"][0]["name"] if data["contacts"] else ""
    try:
        new_text = await generate_dispatch_message(
            intent=data["intent"],
            recipient_name=first_name,
            language=data.get("lang", "ru"),
            style_profile=data.get("style", ""),
        )
    except Exception:
        await query.answer("Ошибка генерации")
        return
    data["send_text"] = new_text
    data["edit_mode"] = False
    names = ", ".join(c["name"] for c in data["contacts"])
    is_personalized = data.get("is_personalized", False)
    personalized_note = "\n<i>(сообщение персонализировано для каждого)</i>" if is_personalized else ""
    from bot.handlers.direct_messages import _preview_keyboard
    await query.message.edit_text(
        f"📤 <b>{names}</b> будет отправлено:{personalized_note}\n\n«{new_text}»\n\nХотите изменить?",
        parse_mode="HTML",
        reply_markup=_preview_keyboard(),
    )


@router.callback_query(F.data == "dispatch_task_yes")
async def handle_dispatch_task_yes(
    query: CallbackQuery, session: AsyncSession
) -> None:
    if query.from_user is None:
        await query.answer()
        return
    owner_id = query.from_user.id
    from bot.handlers.direct_messages import _pending_dispatch_tasks
    data = _pending_dispatch_tasks.pop(owner_id, None)
    if data:
        for contact in data["contacts"]:
            for extracted in data["extracted"]:
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
                    chat_id=contact["user_id"],
                    message_id=0,
                    description=extracted.description or "",
                    assignee_name=contact["name"] or None,
                    assignee_user_id=contact["user_id"],
                    assignee_username=contact["username"] or None,
                    deadline=task_deadline,
                    business_connection_id=data.get("bcid"),
                )
        await query.answer("✅ Задачи добавлены")
        if isinstance(query.message, TgMessage):
            try:
                await query.message.edit_text(
                    (query.message.text or "") + "\n\n✅ <b>Добавлено в задачи</b>",
                    parse_mode="HTML",
                    reply_markup=None,
                )
            except Exception:
                pass
    else:
        await query.answer()


@router.callback_query(F.data == "dispatch_task_no")
async def handle_dispatch_task_no(query: CallbackQuery) -> None:
    if query.from_user is not None:
        from bot.handlers.direct_messages import _pending_dispatch_tasks
        _pending_dispatch_tasks.pop(query.from_user.id, None)
    await query.answer()
    if isinstance(query.message, TgMessage):
        try:
            await query.message.delete()
        except Exception:
            pass


@router.callback_query(F.data.startswith("lang:"))
async def handle_lang_select(query: CallbackQuery, session: AsyncSession) -> None:
    if query.data is None:
        await query.answer()
        return
    lang = query.data.split(":")[1]
    if lang not in ("ru", "en", "ua"):
        await query.answer()
        return
    owner_id = query.from_user.id if query.from_user else 0
    await us_repo.update_settings(session, owner_id, language=lang)
    key = "lang_set_ru" if lang == "ru" else ("lang_set_uk" if lang == "ua" else "lang_set_en")
    await query.answer(t(key))
    if isinstance(query.message, TgMessage):
        await query.message.delete()


@router.callback_query(F.data.startswith("sched_done:"))
async def handle_sched_done(
    query: CallbackQuery, session: AsyncSession
) -> None:
    if query.from_user is None or query.data is None:
        await query.answer()
        return
    task_id_str = query.data.split(":")[1]
    owner_id = query.from_user.id
    try:
        task_id = int(task_id_str)
        task = await task_repo.mark_task_done(session, task_id)
        if task:
            await query.answer("✅ Готово!")
        else:
            await query.answer("Уже выполнено")
    except (ValueError, Exception):
        await query.answer("Уже выполнено")

    text, markup = await build_today_schedule(owner_id, session)
    if isinstance(query.message, TgMessage):
        try:
            await query.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
        except Exception:
            pass


@router.callback_query(F.data.startswith("pick_alias:"))
async def handle_pick_alias(
    query: CallbackQuery, bot: Bot, session: AsyncSession
) -> None:
    from bot.handlers.direct_messages import _pending_dispatch, _pending_ask

    await query.answer()
    if query.data is None or query.from_user is None:
        return

    parts = query.data.split(":", 2)
    if len(parts) < 3:
        return

    alias, contact_user_id_str = parts[1], parts[2]
    owner_id = query.from_user.id

    try:
        contact_user_id = int(contact_user_id_str)
    except ValueError:
        return

    # Save alias
    await contact_repo.set_saved_name(session, owner_id, contact_user_id, alias)

    # Get contact display name for confirmation
    contact = await contact_repo.get_contact(session, owner_id, contact_user_id)
    tg_name = contact.name or contact.username or str(contact_user_id) if contact else str(contact_user_id)

    # Send the pending message if any
    pending = _pending_dispatch.pop(owner_id, None)
    if pending:
        send_text = str(pending.get("text", ""))
        bcid = pending.get("business_connection_id")

        sent = False
        if contact and contact.has_business_chat and send_text:
            try:
                await bot.send_message(
                    chat_id=contact_user_id,
                    text=send_text,
                    business_connection_id=str(bcid) if bcid else None,
                )
                sent = True
            except Exception:
                logger.exception("pick_alias: Bot API send failed to %d", contact_user_id)

        if isinstance(query.message, TgMessage):
            if sent:
                await query.message.edit_text(
                    f"✅ Отправлено «{tg_name}».\n"
                    f"Запомнил: «{alias}» = {tg_name} — теперь можно обращаться по этому имени."
                )
            else:
                await query.message.edit_text(
                    f"💾 Псевдоним сохранён: «{alias}» = {tg_name}.\n"
                    "⚠️ Не удалось отправить сообщение — попробуйте ещё раз."
                )
    else:
        if isinstance(query.message, TgMessage):
            await query.message.edit_text(
                f"💾 Псевдоним сохранён: «{alias}» = {tg_name}.\n"
                f"Теперь можете обращаться к этому контакту по имени «{alias}»."
            )

    # If there's a pending /ask search — run it now filtered by the selected contact
    pending_query = _pending_ask.pop(owner_id, None)
    if pending_query:
        from services.ai import answer_from_context
        from db.repositories import messages as msg_repo
        from db.repositories import user_settings as us_repo
        from bot.handlers.direct_messages import _parse_search_time_range
        chat_id = query.message.chat.id if query.message else owner_id
        searching_msg = await bot.send_message(chat_id=chat_id, text="🔍 Ищу в истории переписок…")
        try:
            us = await us_repo.get_or_create(session, owner_id)
            name_map = await contact_repo.get_name_map(session, owner_id)
            since, until = _parse_search_time_range(pending_query, us.timezone)
            time_range_explicit = since is not None
            effective_since = since or (datetime.now(timezone.utc) - timedelta(days=14))
            effective_until = until or datetime.now(timezone.utc)
            results = await msg_repo.get_messages_in_chat(
                session, owner_id, contact_user_id,
                since=effective_since, until=effective_until, limit=80,
            )
            if not results and time_range_explicit:
                results = await msg_repo.get_messages_in_chat(
                    session, owner_id, contact_user_id, limit=60,
                )
            if not results:
                await searching_msg.edit_text("Не нашёл ничего в переписке с этим контактом.")
            else:
                answer = await answer_from_context(
                    pending_query, results,
                    language=us.language,
                    name_map=name_map,
                    tz_name=us.timezone,
                )
                await searching_msg.edit_text(answer, parse_mode="HTML")
        except Exception:
            logger.exception("handle_pick_alias: pending ask search failed")
            await searching_msg.edit_text("❌ Не удалось выполнить поиск.")


@router.callback_query(F.data.startswith("email_send:"))
async def handle_email_send(
    query: CallbackQuery, bot: Bot, session: AsyncSession
) -> None:
    from bot.handlers.direct_messages import _pending_email
    from services import gmail as gmail_svc

    await query.answer()
    if query.from_user is None or query.data is None:
        return
    owner_id = int(query.data.split(":")[1])
    if query.from_user.id != owner_id:
        return

    pending = _pending_email.get(owner_id)
    if pending is None or pending.get("status") != "preview":
        if isinstance(query.message, TgMessage):
            await query.message.edit_reply_markup(reply_markup=None)
        return

    to = str(pending.get("to") or "")
    subject = str(pending.get("subject") or "")
    body = str(pending.get("body") or "")
    has_attachment = bool(pending.get("has_attachment"))
    queued_file_id: str | None = pending.get("queued_file_id")  # type: ignore[assignment]
    queued_filename = str(pending.get("queued_filename") or "attachment")
    queued_mime = str(pending.get("queued_mime") or "application/octet-stream")

    gmail_service = await gmail_svc.get_gmail_service(owner_id, session)
    if gmail_service is None:
        _pending_email.pop(owner_id, None)
        if isinstance(query.message, TgMessage):
            await query.message.edit_text("❌ Gmail не подключён.", reply_markup=None)
        return

    if queued_file_id:
        try:
            buf = await bot.download(queued_file_id)
            if buf is None:
                raise RuntimeError("empty buffer")
            file_bytes = buf.read()
        except Exception:
            logger.exception("Failed to download queued attachment for owner %d", owner_id)
            if isinstance(query.message, TgMessage):
                await query.message.edit_text("❌ Не удалось скачать файл.", reply_markup=None)
            return
        _pending_email.pop(owner_id, None)
        try:
            await gmail_svc.send_email(
                gmail_service, to=[to], subject=subject, body=body,
                attachments=[(queued_filename, file_bytes, queued_mime)],
            )
            if isinstance(query.message, TgMessage):
                await query.message.edit_text(
                    f"✅ Письмо с вложением <b>{queued_filename}</b> отправлено на <b>{to}</b>",
                    parse_mode="HTML", reply_markup=None,
                )
        except Exception as exc:
            logger.exception("Gmail send with attachment failed: %s", exc)
            if isinstance(query.message, TgMessage):
                await query.message.edit_text("❌ Не удалось отправить письмо.", reply_markup=None)

    elif has_attachment:
        # No queued file yet — ask user to attach one now
        _pending_email[owner_id] = {"to": to, "subject": subject, "body": body}
        if isinstance(query.message, TgMessage):
            await query.message.edit_text(
                f"📎 Прикрепи файл следующим сообщением. Письмо будет отправлено на {to}.",
                reply_markup=None,
            )

    else:
        _pending_email.pop(owner_id, None)
        try:
            await gmail_svc.send_email(gmail_service, to=[to], subject=subject, body=body)
            if isinstance(query.message, TgMessage):
                await query.message.edit_text(
                    f"✅ Письмо отправлено на <b>{to}</b>\n"
                    f"<b>Тема:</b> {subject}\n\n{body[:300]}{'…' if len(body) > 300 else ''}",
                    parse_mode="HTML", reply_markup=None,
                )
        except Exception as exc:
            logger.exception("Gmail send failed: %s", exc)
            if isinstance(query.message, TgMessage):
                await query.message.edit_text("❌ Не удалось отправить письмо.", reply_markup=None)


@router.callback_query(F.data.startswith("email_cancel:"))
async def handle_email_cancel(query: CallbackQuery) -> None:
    from bot.handlers.direct_messages import _pending_email

    await query.answer("Отменено")
    if query.from_user is None or query.data is None:
        return
    owner_id = int(query.data.split(":")[1])
    _pending_email.pop(owner_id, None)
    if isinstance(query.message, TgMessage):
        await query.message.edit_text("❌ Отправка отменена.", reply_markup=None)


@router.callback_query(F.data.startswith("email_edit:"))
async def handle_email_edit(query: CallbackQuery) -> None:
    from bot.handlers.direct_messages import _pending_email

    await query.answer()
    if query.from_user is None or query.data is None:
        return
    owner_id = int(query.data.split(":")[1])
    pending = _pending_email.get(owner_id)
    if pending is None or pending.get("status") != "preview":
        if isinstance(query.message, TgMessage):
            await query.message.edit_reply_markup(reply_markup=None)
        return
    pending["status"] = "edit"
    if isinstance(query.message, TgMessage):
        await query.message.edit_text("✏️ Введи новый текст письма:", reply_markup=None)


@router.callback_query(F.data.startswith("tut:"))
async def handle_tutorial_nav(query: CallbackQuery, bot: Bot) -> None:
    from bot.tutorial import PAGES, send_tutorial_page

    await query.answer()
    if query.data is None:
        return

    suffix = query.data[4:]
    if suffix == "noop":
        return

    chat_id = query.message.chat.id if query.message else (query.from_user.id if query.from_user else 0)

    if suffix == "faq":
        from bot.tutorial import FAQ_TEXT
        if query.message and isinstance(query.message, TgMessage):
            try:
                await query.message.delete()
            except Exception:
                pass
        if chat_id:
            await bot.send_message(
                chat_id=chat_id,
                text=FAQ_TEXT,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="📖 Инструкция к боту", callback_data="tut:0"),
                ]]),
            )
        return

    try:
        page_idx = int(suffix)
    except ValueError:
        return

    if page_idx < 0 or page_idx >= len(PAGES):
        return

    if query.message and isinstance(query.message, TgMessage):
        try:
            await query.message.delete()
        except Exception:
            pass

    if chat_id:
        await send_tutorial_page(bot, chat_id, page_idx)


@router.callback_query(F.data.startswith("reminder_done:"))
async def handle_reminder_done(query: CallbackQuery, session: AsyncSession) -> None:
    if query.data is None:
        await query.answer()
        return
    task_id = int(query.data.split(":")[1])
    task = await task_repo.mark_task_done(session, task_id)
    if task:
        await query.answer("✅ Задача выполнена")
        if isinstance(query.message, TgMessage):
            await query.message.edit_text(
                f"✅ <b>Выполнено</b>\n{task.description}",
                parse_mode="HTML",
                reply_markup=None,
            )
    else:
        await query.answer(t("task_not_found"))


@router.callback_query(F.data.startswith("reminder_snooze:"))
async def handle_reminder_snooze(query: CallbackQuery, session: AsyncSession) -> None:
    if query.data is None or query.from_user is None:
        await query.answer()
        return
    task_id = int(query.data.split(":")[1])
    task = await task_repo.get_task(session, task_id)
    if task is None:
        await query.answer(t("task_not_found"))
        return

    from bot.handlers.direct_messages import _pending_snooze
    owner_id = query.from_user.id
    if isinstance(query.message, TgMessage):
        _pending_snooze[owner_id] = {
            "task_id": task_id,
            "task_description": task.description,
            "chat_id": query.message.chat.id,
            "message_id": query.message.message_id,
        }
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⏰ Через час", callback_data=f"reminder_snooze_hour:{task_id}"),
        ]])
        await query.answer()
        await query.message.edit_text(
            f"⏰ <b>Когда напомнить?</b>\n<i>{task.description}</i>\n\nНапишите время или нажмите кнопку:",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    else:
        await query.answer()


@router.callback_query(F.data.startswith("reminder_snooze_hour:"))
async def handle_reminder_snooze_hour(query: CallbackQuery, session: AsyncSession) -> None:
    if query.data is None or query.from_user is None:
        await query.answer()
        return
    task_id = int(query.data.split(":")[1])
    from bot.handlers.direct_messages import _pending_snooze
    owner_id = query.from_user.id
    _pending_snooze.pop(owner_id, None)
    new_time = datetime.now(timezone.utc) + timedelta(hours=1)
    task = await task_repo.set_reminder(session, task_id, new_time)
    await query.answer("⏰ Напомню через час")
    if task and isinstance(query.message, TgMessage):
        await query.message.edit_text(
            f"⏰ Напомню через час\n<i>{task.description}</i>",
            parse_mode="HTML",
            reply_markup=None,
        )


@router.callback_query(F.data.startswith("reminder_cancel:"))
async def handle_reminder_cancel(query: CallbackQuery, session: AsyncSession) -> None:
    if query.data is None:
        await query.answer()
        return
    task_id = int(query.data.split(":")[1])
    task = await task_repo.cancel_task(session, task_id)
    if task:
        await query.answer("❌ Задача отменена")
        if isinstance(query.message, TgMessage):
            await query.message.edit_text(
                f"❌ <b>Задача отменена</b>\n{task.description}",
                parse_mode="HTML",
                reply_markup=None,
            )
    else:
        await query.answer(t("task_not_found"))


@router.callback_query(F.data == "ghost_regen")
async def handle_ghost_regen(query: CallbackQuery, session: AsyncSession) -> None:
    from bot.handlers.direct_messages import (
        _ghost_contexts,
        _build_ghost_status_lines,
        _ghost_activation_keyboard,
    )
    from services.ai import generate_away_message

    if query.from_user is None or not isinstance(query.message, TgMessage):
        await query.answer()
        return
    owner_id = query.from_user.id
    await query.answer("Генерирую…")

    ctx = _ghost_contexts.get(owner_id, {})
    lang = str(ctx.get("lang", "ru"))
    tz_name = str(ctx.get("tz_name", "Europe/Moscow"))
    context = str(ctx.get("context", "")) or None

    try:
        new_away = await generate_away_message(language=lang, context=context)
    except Exception:
        logger.exception("ghost_regen: generate_away_message failed")
        await query.answer("❌ Ошибка генерации")
        return

    await ghost_repo.update_away_message(session, owner_id, new_away)

    auto_off_iso = ctx.get("auto_off_iso")
    silent_mode = bool(ctx.get("silent_mode", False))
    lines = _build_ghost_status_lines(
        new_away, lang, tz_name,
        str(auto_off_iso) if auto_off_iso else None,
    )
    try:
        await query.message.edit_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=_ghost_activation_keyboard(silent_mode),
        )
    except Exception:
        logger.exception("ghost_regen: failed to edit message")


@router.callback_query(F.data == "ghost_change_text")
async def handle_ghost_change_text(query: CallbackQuery) -> None:
    from bot.handlers.direct_messages import _pending_ghost_text

    await query.answer()
    if query.from_user is None or not isinstance(query.message, TgMessage):
        return
    owner_id = query.from_user.id
    _pending_ghost_text[owner_id] = query.message.message_id

    await query.message.edit_text(
        "✏️ <b>Введите новый текст автоответа:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Отмена", callback_data="ghost_change_text_cancel"),
        ]]),
    )


@router.callback_query(F.data == "ghost_change_text_cancel")
async def handle_ghost_change_text_cancel(query: CallbackQuery, session: AsyncSession) -> None:
    from bot.handlers.direct_messages import (
        _pending_ghost_text,
        _ghost_contexts,
        _build_ghost_status_lines,
        _ghost_activation_keyboard,
    )

    await query.answer("Отменено")
    if query.from_user is None or not isinstance(query.message, TgMessage):
        return
    owner_id = query.from_user.id
    _pending_ghost_text.pop(owner_id, None)

    ctx = _ghost_contexts.get(owner_id, {})
    lang = str(ctx.get("lang", "ru"))
    tz_name = str(ctx.get("tz_name", "Europe/Moscow"))
    auto_off_iso = ctx.get("auto_off_iso")

    gs = await ghost_repo.get_session(session, owner_id)
    away_text = (gs.away_message or "") if gs else ""
    silent_mode = bool(ctx.get("silent_mode", gs.silent_mode if gs else False))

    lines = _build_ghost_status_lines(
        away_text, lang, tz_name,
        str(auto_off_iso) if auto_off_iso else None,
    )
    try:
        await query.message.edit_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=_ghost_activation_keyboard(silent_mode),
        )
    except Exception:
        pass


@router.callback_query(F.data == "ghost_change_time")
async def handle_ghost_change_time(query: CallbackQuery) -> None:
    from bot.handlers.direct_messages import _pending_ghost_time

    await query.answer()
    if query.from_user is None or not isinstance(query.message, TgMessage):
        return
    owner_id = query.from_user.id
    _pending_ghost_time[owner_id] = query.message.message_id

    await query.message.edit_text(
        "⏰ <b>Когда выключить Ghost Mode?</b>\n\n"
        "Напишите время, например:\n"
        "• «через 30 минут»\n"
        "• «в 19:30»",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Отмена", callback_data="ghost_change_time_cancel"),
        ]]),
    )


@router.callback_query(F.data == "ghost_change_time_cancel")
async def handle_ghost_change_time_cancel(query: CallbackQuery, session: AsyncSession) -> None:
    from bot.handlers.direct_messages import (
        _pending_ghost_time,
        _ghost_contexts,
        _build_ghost_status_lines,
        _ghost_activation_keyboard,
    )

    await query.answer("Отменено")
    if query.from_user is None or not isinstance(query.message, TgMessage):
        return
    owner_id = query.from_user.id
    _pending_ghost_time.pop(owner_id, None)

    ctx = _ghost_contexts.get(owner_id, {})
    lang = str(ctx.get("lang", "ru"))
    tz_name = str(ctx.get("tz_name", "Europe/Moscow"))
    auto_off_iso = ctx.get("auto_off_iso")

    gs = await ghost_repo.get_session(session, owner_id)
    away_text = (gs.away_message or "") if gs else ""
    silent_mode = bool(ctx.get("silent_mode", gs.silent_mode if gs else False))

    lines = _build_ghost_status_lines(
        away_text, lang, tz_name,
        str(auto_off_iso) if auto_off_iso else None,
    )
    try:
        await query.message.edit_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=_ghost_activation_keyboard(silent_mode),
        )
    except Exception:
        pass


@router.callback_query(F.data == "ghost_toggle_silent")
async def handle_ghost_toggle_silent(query: CallbackQuery, session: AsyncSession) -> None:
    from bot.handlers.direct_messages import (
        _ghost_contexts,
        _build_ghost_status_lines,
        _ghost_activation_keyboard,
    )

    if query.from_user is None or not isinstance(query.message, TgMessage):
        await query.answer()
        return
    owner_id = query.from_user.id

    gs = await ghost_repo.get_session(session, owner_id)
    if gs is None:
        await query.answer()
        return

    new_silent = not (gs.silent_mode or False)
    await ghost_repo.set_silent_mode(session, owner_id, new_silent)

    ctx = _ghost_contexts.get(owner_id, {})
    _ghost_contexts[owner_id] = {**ctx, "silent_mode": new_silent}

    lang = str(ctx.get("lang", "ru"))
    tz_name = str(ctx.get("tz_name", "Europe/Moscow"))
    auto_off_iso = ctx.get("auto_off_iso")
    away_text = gs.away_message or ""

    status_note = "🔕 Автоответ отключён" if new_silent else "🔔 Автоответ включён"
    await query.answer(status_note)

    lines = _build_ghost_status_lines(
        away_text, lang, tz_name,
        str(auto_off_iso) if auto_off_iso else None,
    )
    try:
        await query.message.edit_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=_ghost_activation_keyboard(new_silent),
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("gmail_reply:") & ~F.data.startswith("gmail_reply_cancel:"))
async def handle_gmail_reply_start(
    query: CallbackQuery, bot: Bot
) -> None:
    import re
    from workers.gmail_reply_worker import _gmail_reply_store
    from bot.handlers.direct_messages import _pending_gmail_reply

    await query.answer()
    if query.from_user is None or query.data is None:
        return

    parts = query.data.split(":", 2)
    if len(parts) < 3:
        return
    try:
        owner_id = int(parts[1])
    except ValueError:
        return
    msg_id = parts[2]

    if query.from_user.id != owner_id:
        return

    msg_info = _gmail_reply_store.get(msg_id)
    if not msg_info:
        if isinstance(query.message, TgMessage):
            await query.message.edit_reply_markup(reply_markup=None)
        return

    from_ = str(msg_info.get("from_", ""))
    m = re.search(r"<([^>]+)>", from_)
    display = m.group(1) if m else from_

    _pending_gmail_reply[owner_id] = dict(msg_info)

    prompt = await bot.send_message(
        chat_id=owner_id,
        text=f"✉️ <b>Ответ для {display}</b>\n\nВведите текст ответа:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"gmail_reply_cancel:{owner_id}"),
        ]]),
    )
    _pending_gmail_reply[owner_id]["prompt_msg_id"] = prompt.message_id


@router.callback_query(F.data.startswith("gmail_reply_cancel:"))
async def handle_gmail_reply_cancel(
    query: CallbackQuery,
) -> None:
    from bot.handlers.direct_messages import _pending_gmail_reply

    await query.answer("Отменено")
    if query.from_user is None or query.data is None:
        return
    try:
        owner_id = int(query.data.split(":")[1])
    except ValueError:
        return
    if query.from_user.id != owner_id:
        return

    _pending_gmail_reply.pop(owner_id, None)
    if isinstance(query.message, TgMessage):
        try:
            await query.message.delete()
        except Exception:
            pass


@router.callback_query(F.data == "privacy_accept")
async def handle_privacy_accept(query: CallbackQuery, session: AsyncSession) -> None:
    if query.from_user is None:
        await query.answer()
        return
    owner_id = query.from_user.id
    await us_repo.accept_privacy(session, owner_id)
    await query.answer("✅ Принято")
    if isinstance(query.message, TgMessage):
        try:
            await query.message.delete()
        except Exception:
            pass
    # Show the normal welcome screen
    from aiogram.types import WebAppInfo
    from config import settings as cfg
    await query.bot.send_message(  # type: ignore[union-attr]
        chat_id=owner_id,
        text=(
            "🧠 <b>НейроSave — ИИ-помощник, который экономит ваше время и нейроресурс</b>\n\n"
            "Забудьте про потерянные задачи, пропущенные письма и утренний хаос.\n\n"
            "📌 <b>Задачи</b> — сам извлекает дедлайны из чатов и напоминает вовремя\n"
            "👻 <b>Ghost-режим</b> — отвечает за вас пока вы заняты, собирает суть вопросов\n"
            "🔍 <b>Память чатов</b> — находит любую договорённость за секунды по запросу\n"
            "📨 <b>Gmail</b> — важные письма прямо в Telegram, ответ без смены приложения\n"
            "☀️ <b>Утренний брифинг</b> — дедлайны, просрочки и ночная сводка каждое утро\n\n"
            "━━━━━━━━━━━━━━━━━\n"
            "⚙️ <b>Дайте боту доступ к чатам</b> — без этого бот не сможет работать.\n"
            "Инструкция по кнопке ниже 👇"
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📖 Инструкция к боту", callback_data="tut:0"),
            InlineKeyboardButton(text="📱 Мини-приложение", web_app=WebAppInfo(url=cfg.miniapp_url)),
        ]]),
    )


@router.callback_query(F.data == "delete_data_confirm")
async def handle_delete_data_confirm(query: CallbackQuery, session: AsyncSession) -> None:
    if query.from_user is None:
        await query.answer()
        return
    owner_id = query.from_user.id
    await query.answer("Удаляю…")
    if isinstance(query.message, TgMessage):
        try:
            await query.message.edit_text("🗑 Удаляю данные…", reply_markup=None)
        except Exception:
            pass
    try:
        await us_repo.delete_all_user_data(session, owner_id)
        if isinstance(query.message, TgMessage):
            await query.message.edit_text(
                "✅ <b>Все ваши данные удалены.</b>\n\n"
                "История задач, контакты, настройки и интеграции — всё стёрто из базы данных.\n"
                "Если захотите вернуться — просто отправьте /start.",
                parse_mode="HTML",
            )
    except Exception:
        logger.exception("delete_all_user_data failed for owner %d", owner_id)
        if isinstance(query.message, TgMessage):
            await query.message.edit_text(
                "❌ Не удалось удалить данные. Попробуйте позже или обратитесь в поддержку.",
                reply_markup=None,
            )


@router.callback_query(F.data == "delete_data_cancel")
async def handle_delete_data_cancel(query: CallbackQuery) -> None:
    await query.answer("Отменено")
    if isinstance(query.message, TgMessage):
        try:
            await query.message.delete()
        except Exception:
            pass


@router.callback_query(F.data == "file_pending_cancel")
async def handle_file_pending_cancel(query: CallbackQuery) -> None:
    from bot.handlers.direct_messages import _pending_file
    await query.answer("Отменено")
    if query.from_user is not None:
        _pending_file.pop(query.from_user.id, None)
    if isinstance(query.message, TgMessage):
        try:
            await query.message.delete()
        except Exception:
            pass


@router.callback_query()
async def handle_callback_fallback(query: CallbackQuery) -> None:
    await query.answer()
