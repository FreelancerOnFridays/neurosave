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

from bot.config_store import set_last_contact_sync, t
from bot.keyboards.settings import language_keyboard
from bot.keyboards.tasks import task_action_keyboard
from bot.handlers.direct_messages import cmd_reminders, cmd_notion_db
from bot.handlers.ghost import cmd_digest
import bot.telethon_client as tg_client
from config import settings
from db.repositories import contacts as contact_repo
from db.repositories import messages as msg_repo
from db.repositories import tasks as task_repo
from db.repositories import user_settings as us_repo
from services.ai import answer_from_context, embed_text
from services.contact_sync import list_folders, sync_all_with_folders, sync_folder_contacts

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if message.from_user is None:
        return
    if message.from_user.id == settings.owner_chat_id:
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
            "/digest — дайджест пропущенных сообщений\n\n"
            "<b>Контакты:</b>\n"
            "/sync_contacts — синхронизировать контакты и папки\n"
            "/folders — список папок чатов\n"
            "/sync_folder &lt;название&gt; — синхронизировать отдельную папку\n"
            "(Подключение Telegram: /app → Настройки → Контакты)",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "👋 Привет! Я ваш персональный ассистент NeuroSave.\n\n"
            "Доступные команды:\n"
            "/today — расписание на сегодня\n"
            "/tasks — делегированные задачи\n"
            "/reminders — активные напоминания\n"
            "/brief — утренний брифинг\n"
            "/settings — язык и часовой пояс\n"
            "/tz &lt;часовой_пояс&gt; — сменить часовой пояс\n"
            "/alias &lt;имя&gt; &lt;псевдоним&gt; — псевдоним контакта\n"
            "/ghost on|off — режим призрака\n"
            "/vip — VIP-контакты\n"
            "/ask — поиск по истории чатов\n"
            "/digest — дайджест пропущенных сообщений",
            parse_mode="HTML",
        )


@router.message(Command("app"))
async def cmd_app(message: Message) -> None:
    if message.from_user is None:
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
async def cmd_settings(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    us = await us_repo.get_or_create(session, message.from_user.id)
    text = t("settings_title").format(
        current_lang=us.language,
        current_tz=us.timezone,
    )
    await message.answer(text, parse_mode="HTML", reply_markup=language_keyboard())


@router.message(Command("tz"))
async def cmd_tz(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    _TZ_MAP: dict[str, str] = {
        "+0": "UTC", "+1": "Europe/Berlin", "+2": "Europe/Kyiv",
        "+3": "Europe/Moscow", "+4": "Asia/Dubai", "+5": "Asia/Tashkent",
        "+6": "Asia/Almaty", "+7": "Asia/Krasnoyarsk", "+8": "Asia/Shanghai",
        "+9": "Asia/Tokyo", "+10": "Asia/Vladivostok", "+11": "Asia/Magadan",
        "+12": "Pacific/Auckland", "-3": "America/Sao_Paulo",
        "-5": "America/New_York", "-6": "America/Chicago",
        "-7": "America/Denver", "-8": "America/Los_Angeles",
    }
    user_id = message.from_user.id
    us = await us_repo.get_or_create(session, user_id)
    text = message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            f"Текущий часовой пояс: <b>{us.timezone}</b>\n\n"
            "Использование: /tz &lt;часовой_пояс&gt;\n"
            "Примеры: /tz Europe/Moscow · /tz +3 · /tz UTC",
            parse_mode="HTML",
        )
        return
    tz_input = parts[1].strip()
    resolved = _TZ_MAP.get(tz_input, tz_input)
    try:
        ZoneInfo(resolved)
        await us_repo.update_settings(session, user_id, timezone=resolved)
        await message.answer(f"✅ Часовой пояс: <b>{resolved}</b>", parse_mode="HTML")
    except (KeyError, ZoneInfoNotFoundError):
        await message.answer(
            f"❌ Неизвестный часовой пояс: <code>{tz_input}</code>\n"
            "Используйте формат IANA, например: <code>Europe/Moscow</code>, "
            "<code>Asia/Almaty</code>, или смещение: <code>+3</code>",
            parse_mode="HTML",
        )


@router.message(Command("alias"))
async def cmd_alias(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
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
        query_vec = await embed_text(query)
        results = await msg_repo.search_similar(
            session, owner_id, query_vec, limit=10
        )
        if not results:
            await thinking.edit_text("Не нашёл ничего похожего — возможно, история ещё не проиндексирована.")
            return
        name_map = await contact_repo.get_name_map(session, owner_id)
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


@router.message(Command("digest"))
async def cmd_digest_handler(message: Message, session: AsyncSession) -> None:
    await cmd_digest(message, session)


@router.message(Command("today"))
async def cmd_today(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    from bot.schedule import build_today_schedule
    text, markup = await build_today_schedule(message.from_user.id, session)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.message(Command("sync_contacts"))
async def cmd_sync_contacts(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user_id = message.from_user.id

    if not tg_client.is_configured():
        await message.answer(
            "❌ Telethon не настроен. Добавьте TELEGRAM_API_ID и TELEGRAM_API_HASH в .env"
        )
        return

    us = await us_repo.get_or_create(session, user_id)

    # Allow force-reset: /sync_contacts reset
    text = message.text or ""
    if text.strip().lower().endswith("reset"):
        await tg_client.reset_session(user_id)
        await us_repo.update_settings(session, user_id, telethon_session=None)
        await message.answer("🔄 Сессия сброшена. Подключите Telegram через мини-приложение (/app).")
        return

    try:
        authorized = await tg_client.is_authorized(user_id, us.telethon_session)
    except Exception:
        logger.exception("is_authorized check failed for user %d", user_id)
        await tg_client.reset_session(user_id)
        await us_repo.update_settings(session, user_id, telethon_session=None)
        await message.answer("⚠️ Сессия устарела. Подключите Telegram через мини-приложение (/app).")
        return

    if not authorized:
        await message.answer("🔗 Telegram не подключён. Авторизуйтесь в мини-приложении: /app → Настройки → Контакты.")
        return

    client = await tg_client.get_client(user_id, us.telethon_session)
    if client is None:
        await message.answer("❌ Не удалось подключиться к Telethon.")
        return

    status_msg = await message.answer("🔄 Синхронизирую контакты и папки…")
    try:
        from datetime import datetime, timezone
        count = await sync_all_with_folders(client, user_id, session)
        set_last_contact_sync(datetime.now(timezone.utc).isoformat())
        await status_msg.edit_text(f"✅ Синхронизировано {count} контактов (включая метки папок).")
    except Exception as e:
        logger.exception("sync_contacts failed for user %d", user_id)
        err_name = type(e).__name__
        if any(x in err_name for x in ("AuthKey", "Unauthorized", "Deactivated", "Auth")):
            await tg_client.reset_session(user_id)
            await us_repo.update_settings(session, user_id, telethon_session=None)
            await status_msg.edit_text("⚠️ Сессия устарела. Подключите Telegram через мини-приложение (/app).")
        else:
            await status_msg.edit_text(f"❌ Ошибка синхронизации: {err_name}: {e}")


@router.message(Command("folders"))
async def cmd_folders(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user_id = message.from_user.id
    us = await us_repo.get_or_create(session, user_id)

    if not await tg_client.is_authorized(user_id, us.telethon_session):
        await message.answer("❌ Telethon не авторизован. Используйте /sync_contacts для входа.")
        return

    client = await tg_client.get_client(user_id, us.telethon_session)
    if client is None:
        await message.answer("❌ Не удалось подключиться к Telethon.")
        return

    try:
        folders = await list_folders(client)
        if not folders:
            await message.answer("Папок с чатами не найдено.")
            return
        lines = "\n".join(f"• {name}" for name in folders)
        await message.answer(
            f"📁 <b>Папки чатов:</b>\n{lines}\n\n"
            "Для синхронизации: /sync_folder &lt;название&gt;",
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("folders command failed for user %d", user_id)
        await message.answer("❌ Ошибка при получении папок.")


@router.message(Command("sync_folder"))
async def cmd_sync_folder(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user_id = message.from_user.id

    text = message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Использование: /sync_folder &lt;название папки&gt;\n"
            "Пример: /sync_folder Команда\n\n"
            "Список папок: /folders",
            parse_mode="HTML",
        )
        return

    folder_name = parts[1].strip()
    us = await us_repo.get_or_create(session, user_id)

    if not await tg_client.is_authorized(user_id, us.telethon_session):
        await message.answer("❌ Telethon не авторизован. Используйте /sync_contacts для входа.")
        return

    client = await tg_client.get_client(user_id, us.telethon_session)
    if client is None:
        await message.answer("❌ Не удалось подключиться к Telethon.")
        return

    status_msg = await message.answer(f"🔄 Синхронизирую папку «{folder_name}»…")
    try:
        count = await sync_folder_contacts(client, user_id, folder_name, session)
        await status_msg.edit_text(f"✅ Синхронизировано {count} контактов из папки «{folder_name}».")
    except ValueError as e:
        await status_msg.edit_text(f"❌ {e}")
    except Exception:
        logger.exception("sync_folder failed for user %d", user_id)
        await status_msg.edit_text("❌ Ошибка при синхронизации папки.")


@router.message(Command("brief"))
async def cmd_brief(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    from workers.morning_brief import build_and_send_brief

    user_id = message.from_user.id
    us = await us_repo.get_or_create(session, user_id)
    text = message.text or ""
    parts = text.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if arg.lower() == "off":
        await us_repo.update_settings(session, user_id, brief_enabled=False)
        await message.answer("☕ Утренний брифинг выключен.")
        return

    if arg.lower() == "on":
        await us_repo.update_settings(session, user_id, brief_enabled=True)
        await message.answer(f"☕ Утренний брифинг включён. Время: <b>{us.brief_time}</b>", parse_mode="HTML")
        return

    if arg and arg[0].isdigit():
        h, sep, m = arg.partition(":")
        if sep and h.isdigit() and m.isdigit() and 0 <= int(h) <= 23 and 0 <= int(m) <= 59:
            normalized = f"{int(h):02d}:{int(m):02d}"
            await us_repo.update_settings(session, user_id, brief_time=normalized)
            await message.answer(f"✅ Время брифинга: <b>{normalized}</b>", parse_mode="HTML")
        else:
            await message.answer(
                "❌ Неверный формат. Используйте HH:MM, например: /brief 08:30"
            )
        return

    status = "включён" if us.brief_enabled else "выключен"
    await message.answer(
        f"☕ Утренний брифинг <b>{status}</b>. Время: <b>{us.brief_time}</b>\n\n"
        "Отправляю сейчас…",
        parse_mode="HTML",
    )
    if message.bot:
        await build_and_send_brief(message.bot, user_id)


@router.message(Command("notion_db"))
async def cmd_notion_db_handler(message: Message, session: AsyncSession) -> None:
    await cmd_notion_db(message, session)
