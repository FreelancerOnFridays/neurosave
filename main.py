from __future__ import annotations

import asyncio
import logging
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.handlers import business_messages, callbacks, commands, direct_messages, ghost
from bot.middlewares.db_session import DbSessionMiddleware
from config import settings
from workers import deadline_reminder, morning_brief
from workers.broker import broker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_ALLOWED_UPDATES = [
    "message",
    "business_message",
    "callback_query",
    "business_connection",
]


async def main() -> None:
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()
    dp.update.middleware(DbSessionMiddleware())
    dp.include_router(commands.router)
    dp.include_router(ghost.router)
    dp.include_router(business_messages.router)
    dp.include_router(callbacks.router)
    dp.include_router(direct_messages.router)

    await broker.startup()
    logger.info("Broker started")

    logger.info("Starting bot (allowed_updates=%s)", _ALLOWED_UPDATES)
    await asyncio.gather(
        dp.start_polling(bot, allowed_updates=_ALLOWED_UPDATES),
        deadline_reminder.run_loop(bot),
        morning_brief.run_loop(bot),
    )


if __name__ == "__main__":
    asyncio.run(main())
