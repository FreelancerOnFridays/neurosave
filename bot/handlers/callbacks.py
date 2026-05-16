from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message as TgMessage
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config_store import t
from bot.schedule import build_today_schedule
import bot.telethon_client as tg_client
from db.repositories import contacts as contact_repo
from db.repositories import messages as msg_repo
from db.repositories import tasks as task_repo
from db.repositories import user_settings as us_repo
from services.ai import generate_nudge_message, get_style_profile

logger = logging.getLogger(__name__)
router = Router()


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


@router.callback_query(F.data.startswith("lang:"))
async def handle_lang_select(query: CallbackQuery, session: AsyncSession) -> None:
    if query.data is None:
        await query.answer()
        return
    lang = query.data.split(":")[1]
    if lang not in ("ru", "en"):
        await query.answer()
        return
    owner_id = query.from_user.id if query.from_user else 0
    await us_repo.update_settings(session, owner_id, language=lang)
    key = "lang_set_ru" if lang == "ru" else "lang_set_en"
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
    from bot.handlers.direct_messages import _pending_dispatch

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
        telethon_session = pending.get("telethon_session")

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

        if not sent and send_text:
            client = await tg_client.get_client(owner_id, str(telethon_session) if telethon_session else None)
            if client and await tg_client.is_authorized(owner_id, str(telethon_session) if telethon_session else None):
                try:
                    await client.send_message(contact_user_id, send_text)
                    sent = True
                except Exception:
                    logger.exception("pick_alias: Telethon send failed to %d", contact_user_id)

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


@router.callback_query()
async def handle_callback_fallback(query: CallbackQuery) -> None:
    await query.answer()
