from __future__ import annotations

from aiogram import Bot
from beartype import beartype
from fastapi import APIRouter, Depends

from api.auth import get_owner_id
from bot.tutorial import send_tutorial_page
from config import settings

router = APIRouter()


@router.post("/tutorial")
@beartype
async def send_tutorial(user_id: int = Depends(get_owner_id)) -> dict[str, bool]:
    bot = Bot(token=settings.bot_token)
    try:
        await send_tutorial_page(bot, user_id, 0)
    finally:
        await bot.session.close()
    return {"ok": True}
