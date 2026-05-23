from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import UserSettings

_POLICY_URL = "https://telegra.ph/POLITIKA-KONFIDENCIALNOSTI-SERVISA-NEJROSAVE-05-23"

_POLICY_TEXT = (
    "👋 Добро пожаловать в NeuroSave!\n\n"
    "Прежде чем начать, ознакомьтесь с нашей "
    f'<a href="{_POLICY_URL}">Политикой конфиденциальности</a>.\n\n'
    "Нажимая «Принимаю», вы соглашаетесь с условиями обработки ваших данных."
)

_ACCEPT_KEYBOARD = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="✅ Принимаю", callback_data="privacy_accept"),
]])

# Callbacks that are allowed before policy acceptance
_ALLOWED_CALLBACKS = {"privacy_accept"}


class PrivacyGateMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id: int | None = None

        if isinstance(event, Message):
            if event.from_user:
                user_id = event.from_user.id
            # Business messages (forwarded from contacts) — skip gate
            if event.business_connection_id:
                return await handler(event, data)
            # /start is always allowed (it shows the policy itself)
            if event.text and event.text.startswith("/start"):
                return await handler(event, data)

        elif isinstance(event, CallbackQuery):
            if event.from_user:
                user_id = event.from_user.id
            if event.data in _ALLOWED_CALLBACKS:
                return await handler(event, data)

        if user_id is None:
            return await handler(event, data)

        session: AsyncSession | None = data.get("session")
        if session is None:
            return await handler(event, data)

        us = await session.get(UserSettings, user_id)
        if us is not None and us.privacy_accepted_at is not None:
            return await handler(event, data)

        # Not accepted — prompt and block
        if isinstance(event, Message):
            await event.answer(_POLICY_TEXT, parse_mode="HTML", reply_markup=_ACCEPT_KEYBOARD)
        elif isinstance(event, CallbackQuery) and event.bot:
            await event.answer("Сначала примите политику конфиденциальности", show_alert=True)
            await event.bot.send_message(
                chat_id=user_id,
                text=_POLICY_TEXT,
                parse_mode="HTML",
                reply_markup=_ACCEPT_KEYBOARD,
            )
        return None
