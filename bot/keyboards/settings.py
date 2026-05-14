from __future__ import annotations

from beartype import beartype
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config_store import t


@beartype
def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("lang_ru_label"), callback_data="lang:ru"),
                InlineKeyboardButton(text=t("lang_en_label"), callback_data="lang:en"),
            ]
        ]
    )
