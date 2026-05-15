from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from bot.config_store import get_language, get_timezone, set_timezone, t
from bot.keyboards.settings import language_keyboard
from bot.keyboards.tasks import task_action_keyboard
from bot.handlers.direct_messages import cmd_reminders
from bot.handlers.ghost import cmd_digest
from config import settings
from db.repositories import contacts as contact_repo
from db.repositories import messages as msg_repo
from db.repositories import tasks as task_repo
from services.ai import answer_from_context, embed_text

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "👋 NeuroSave активирован.\n\n"
        "Доступные команды:\n"
        "/app — открыть мини-приложение\n"
        "/today — расписание на сегодня\n"
        "/tasks — делегированные задачи\n"
        "/reminders — активные напоминания\n"
        "/brief — утренний брифинг (отправить сейчас)\n"
        "/brief HH:MM — изменить время брифинга\n"
        "/settings — язык и часовой пояс\n"
        "/tz &lt;часовой_пояс&gt; — сменить часовой пояс (пример: /tz Europe/Moscow)\n"
        "/alias &lt;имя&gt; &lt;псевдоним&gt; — псевдоним контакта\n"
        "/ghost on|off — режим призрака\n"
        "/vip — VIP-контакты\n"
        "/ask — поиск по истории чатов\n"
        "/digest — дайджест пропущенных сообщений"
    )


@router.message(Command("app"))
async def cmd_app(message: Message) -> None:
    if message.from_user is None or message.from_user.id != settings.owner_chat_id:
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


@router.message(Command("tasks"))
async def cmd_tasks(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    tasks = await task_repo.get_open_tasks(session, owner_id=message.from_user.id)
    if not tasks:
        await message.answer(t("tasks_empty"))
        return
    for task in tasks:
        parts = [f"📌 <b>{task.description}</b>"]
        if task.assignee_name:
            parts.append(f"👤 {task.assignee_name}")
        if task.deadline:
            parts.append(f"📅 {task.deadline.strftime('%d.%m.%Y %H:%M')}")
        await message.answer(
            "\n".join(parts),
            parse_mode="HTML",
            reply_markup=task_action_keyboard(task.id),
        )


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    text = t("settings_title").format(
        current_lang=t("lang_current_name"),
        current_tz=get_timezone(),
    )
    await message.answer(text, parse_mode="HTML", reply_markup=language_keyboard())


@router.message(Command("tz"))
async def cmd_tz(message: Message) -> None:
    if message.from_user is None or message.from_user.id != settings.owner_chat_id:
        return
    text = message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            f"Текущий часовой пояс: <b>{get_timezone()}</b>\n\n"
            "Использование: /tz &lt;часовой_пояс&gt;\n"
            "Примеры: /tz Europe/Moscow · /tz +3 · /tz UTC"
        )
        return
    tz_input = parts[1].strip()
    try:
        set_timezone(tz_input)
        from bot.config_store import get_timezone as _get_tz
        await message.answer(f"✅ Часовой пояс: <b>{_get_tz()}</b>")
    except ValueError:
        await message.answer(
            f"❌ Неизвестный часовой пояс: <code>{tz_input}</code>\n"
            "Используйте формат IANA, например: <code>Europe/Moscow</code>, "
            "<code>Asia/Almaty</code>, или смещение: <code>+3</code>"
        )


@router.message(Command("alias"))
async def cmd_alias(message: Message, session: AsyncSession) -> None:
    if message.from_user is None or message.from_user.id != settings.owner_chat_id:
        return
    text = message.text or ""
    parts = text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            "Использование: /alias &lt;имя_в_Telegram&gt; &lt;псевдоним&gt;\n"
            "Пример: /alias Roman Папа"
        )
        return
    telegram_name, alias = parts[1], parts[2]
    matches = await contact_repo.find_contacts_by_name(
        session, owner_id=message.from_user.id, name=telegram_name
    )
    if not matches:
        await message.answer(f"Контакт «{telegram_name}» не найден.")
        return
    contact = matches[0]
    await contact_repo.set_saved_name(
        session, owner_id=message.from_user.id, user_id=contact.user_id, saved_name=alias
    )
    await message.answer(f"✅ «{contact.name}» теперь называется «{alias}»")


@router.message(Command("reminders"))
async def cmd_reminders_handler(message: Message, session: AsyncSession) -> None:
    await cmd_reminders(message, session)


@router.message(Command("vip"))
async def cmd_vip(message: Message) -> None:
    await message.answer("⭐ VIP-список: в разработке.")


@router.message(Command("ask"))
async def cmd_ask(message: Message, session: AsyncSession) -> None:
    if message.from_user is None or message.from_user.id != settings.owner_chat_id:
        return
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
        query_vec = await embed_text(query)
        results = await msg_repo.search_similar(
            session, settings.owner_chat_id, query_vec, limit=10
        )
        if not results:
            await thinking.edit_text("Не нашёл ничего похожего — возможно, история ещё не проиндексирована.")
            return
        name_map = await contact_repo.get_name_map(session, settings.owner_chat_id)
        answer = await answer_from_context(
            query, results,
            language=get_language(),
            name_map=name_map,
            tz_name=get_timezone(),
        )
        await thinking.edit_text(answer, parse_mode="HTML")
    except Exception:
        logger.exception("cmd_ask failed")
        await thinking.edit_text("❌ Не удалось выполнить поиск.")


@router.message(Command("digest"))
async def cmd_digest_handler(message: Message, session: AsyncSession) -> None:
    await cmd_digest(message, session)


@router.message(Command("today"))
async def cmd_today(message: Message, session: AsyncSession) -> None:
    if message.from_user is None or message.from_user.id != settings.owner_chat_id:
        return
    from bot.schedule import build_today_schedule
    text, markup = await build_today_schedule(message.from_user.id, session)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.message(Command("brief"))
async def cmd_brief(message: Message) -> None:
    if message.from_user is None or message.from_user.id != settings.owner_chat_id:
        return
    from bot.config_store import get_brief_time, is_brief_enabled, set_brief_enabled, set_brief_time
    from workers.morning_brief import build_and_send_brief

    text = message.text or ""
    parts = text.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if arg.lower() == "off":
        set_brief_enabled(False)
        await message.answer("☕ Утренний брифинг выключен.")
        return

    if arg.lower() == "on":
        set_brief_enabled(True)
        await message.answer(f"☕ Утренний брифинг включён. Время: <b>{get_brief_time()}</b>", parse_mode="HTML")
        return

    if arg and arg[0].isdigit():
        try:
            set_brief_time(arg)
            await message.answer(f"✅ Время брифинга: <b>{get_brief_time()}</b>", parse_mode="HTML")
        except ValueError:
            await message.answer(
                "❌ Неверный формат. Используйте HH:MM, например: /brief 08:30"
            )
        return

    status = "включён" if is_brief_enabled() else "выключён"
    await message.answer(
        f"☕ Утренний брифинг <b>{status}</b>. Время: <b>{get_brief_time()}</b>\n\n"
        "Отправляю сейчас…",
        parse_mode="HTML",
    )
    if message.bot:
        await build_and_send_brief(message.bot)
