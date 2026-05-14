from __future__ import annotations

import hashlib
import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message as TgMessage
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config_store import get_language, set_language, t
from bot.reminder_store import get_active, remove_reminder
from bot.schedule import build_today_schedule
from config import settings
from db.repositories import messages as msg_repo
from db.repositories import tasks as task_repo
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

    recent = await msg_repo.get_recent_owner_messages(session, settings.owner_chat_id)
    style = await get_style_profile(settings.owner_chat_id, [m.text for m in recent])

    try:
        nudge_text = await generate_nudge_message(
            description=task.description,
            assignee_name=task.assignee_name,
            deadline=task.deadline,
            language=get_language(),
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
async def handle_lang_select(query: CallbackQuery) -> None:
    if query.data is None:
        await query.answer()
        return
    lang = query.data.split(":")[1]
    try:
        set_language(lang)
    except ValueError:
        await query.answer()
        return
    key = "lang_set_ru" if lang == "ru" else "lang_set_en"
    await query.answer(t(key))
    if isinstance(query.message, TgMessage):
        await query.message.delete()


@router.callback_query(F.data.startswith("sched_done:"))
async def handle_sched_done(query: CallbackQuery) -> None:
    if query.from_user.id != settings.owner_chat_id or query.data is None:
        await query.answer()
        return
    h = query.data.split(":")[1]
    owner_id = settings.owner_chat_id
    target = next(
        (r for r in get_active(owner_id)
         if hashlib.md5(r.reminder_text.encode()).hexdigest()[:8] == h),
        None,
    )
    if target:
        remove_reminder(owner_id, target)
        await query.answer("✅ Готово!")
    else:
        await query.answer("Уже выполнено")

    text, markup = build_today_schedule(owner_id)
    if isinstance(query.message, TgMessage):
        try:
            await query.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
        except Exception:
            pass  # nothing left to edit (empty schedule edits to same text)


@router.callback_query()
async def handle_callback_fallback(query: CallbackQuery) -> None:
    await query.answer()
