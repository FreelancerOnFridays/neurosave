from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from beartype import beartype

from bot.config_store import set_last_contact_sync
from db.engine import session_factory
from db.repositories import user_settings as us_repo

logger = logging.getLogger(__name__)

_CHECK_INTERVAL = 3600  # check every hour, run once per day at 03:00


@beartype
async def run_loop() -> None:
    from zoneinfo import ZoneInfo

    while True:
        await asyncio.sleep(_CHECK_INTERVAL)
        try:
            import bot.telethon_client as tg_client
            from services.contact_sync import sync_all_contacts

            if not tg_client.is_configured():
                continue

            tz = ZoneInfo("Europe/Moscow")
            now_local = datetime.now(tz)
            if now_local.hour != 3:
                continue

            today_str = now_local.strftime("%Y-%m-%d")

            async with session_factory() as sess:
                users = await us_repo.get_all_owner_ids(sess)

            for owner_id in users:
                try:
                    async with session_factory() as sess:
                        us = await us_repo.get_or_create(sess, owner_id)
                        if not us.telethon_session:
                            continue
                        authorized = await tg_client.is_authorized(owner_id, us.telethon_session)
                        if not authorized:
                            continue

                    client = await tg_client.get_client(owner_id, us.telethon_session)
                    if client is None:
                        continue

                    async with session_factory() as sess:
                        async with sess.begin():
                            count = await sync_all_contacts(client, owner_id, sess)

                    set_last_contact_sync(datetime.now(timezone.utc).isoformat())
                    logger.info("Daily contact sync done for user %d: %d contacts", owner_id, count)
                except Exception:
                    logger.exception("contact_sync_worker failed for user %d", owner_id)

        except Exception:
            logger.exception("contact_sync_worker iteration failed")
