from __future__ import annotations

from beartype import beartype
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config_store import t


@beartype
def task_action_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("btn_done"), callback_data=f"task_done:{task_id}"),
                InlineKeyboardButton(text=t("btn_remind"), callback_data=f"task_nudge:{task_id}"),
                InlineKeyboardButton(text=t("btn_delete"), callback_data=f"task_delete:{task_id}"),
            ]
        ]
    )
