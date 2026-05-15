from __future__ import annotations

import asyncio
import logging
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from api.app import create_app
from bot.handlers import business_messages, callbacks, commands, direct_messages, ghost
from bot.middlewares.db_session import DbSessionMiddleware
from config import settings
from workers import deadline_reminder, morning_brief, reminder_worker
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

    api_app = create_app()
    api_app.state.bot = bot

    await broker.startup()
    logger.info("Broker started")

    server_config = uvicorn.Config(
        api_app,
        host="0.0.0.0",
        port=settings.api_port,
        log_level="warning",
    )
    server = uvicorn.Server(server_config)

    logger.info("Starting bot (allowed_updates=%s) and API on port %d", _ALLOWED_UPDATES, settings.api_port)
    await asyncio.gather(
        dp.start_polling(bot, allowed_updates=_ALLOWED_UPDATES),
        deadline_reminder.run_loop(bot),
        morning_brief.run_loop(bot),
        reminder_worker.run_loop(bot),
        server.serve(),
    )


if __name__ == "__main__":
    asyncio.run(main())
