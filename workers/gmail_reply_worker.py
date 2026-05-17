from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from beartype import beartype

from db.engine import session_factory
from db.repositories import integration_configs as cfg_repo
from db.repositories import oauth as oauth_repo
from db.repositories import user_settings as us_repo

logger = logging.getLogger(__name__)

_CHECK_INTERVAL = 300  # every 5 minutes

_KEY = "gmail_history_id"


def _sender_name(from_: str) -> str:
    import re
    match = re.match(r'^"?([^"<]+)"?\s*<', from_)
    return match.group(1).strip() if match else from_.replace("<.*>", "").strip() or from_


def _format_reply(msg: dict) -> str:
    sender = _sender_name(msg.get("from_", ""))
    subject = msg.get("subject") or "(без темы)"
    snippet = msg.get("snippet") or ""
    lines = [f"📨 <b>Ответ на письмо</b>", f"<b>От:</b> {sender}", f"<b>Тема:</b> {subject}"]
    if snippet:
        lines.append(f"<i>{snippet}</i>")
    return "\n".join(lines)


@beartype
async def _init_history_id(service: object, session: object, owner_id: int) -> str | None:
    from db.engine import session_factory as sf  # avoid shadowing
    try:
        profile: dict = service.users().getProfile(userId="me").execute()  # type: ignore[attr-defined]
        history_id = str(profile.get("historyId", ""))
        if history_id:
            async with sf() as sess:
                async with sess.begin():
                    await cfg_repo.set_config(sess, owner_id, _KEY, history_id)
            return history_id
    except Exception as exc:
        logger.warning("gmail_reply_worker: failed to get historyId for %d: %s", owner_id, exc)
    return None


@beartype
async def check_gmail_replies(bot: Bot) -> None:
    from services.gmail import get_gmail_service, get_history_since

    async with session_factory() as session:
        owner_ids = await us_repo.get_all_owner_ids(session)

    for owner_id in owner_ids:
        try:
            async with session_factory() as session:
                token_row = await oauth_repo.get_token(session, owner_id, "gmail")
                if token_row is None:
                    continue

                service = await get_gmail_service(owner_id, session)
                if service is None:
                    continue

                history_id = await cfg_repo.get_config(session, owner_id, _KEY)

            if not history_id:
                # First run — store current historyId, nothing to forward yet
                async with session_factory() as session:
                    await _init_history_id(service, session, owner_id)
                continue

            messages = await get_history_since(service, history_id)

            # Advance historyId even on empty result to stay current
            try:
                profile: dict = service.users().getProfile(userId="me").execute()  # type: ignore[attr-defined]
                new_history_id = str(profile.get("historyId", ""))
            except Exception:
                new_history_id = ""

            for msg in messages:
                # Only forward inbox replies (messages that have In-Reply-To or are_reply)
                if not msg.get("is_reply"):
                    continue
                try:
                    await bot.send_message(
                        chat_id=owner_id,
                        text=_format_reply(msg),
                        parse_mode="HTML",
                    )
                except Exception as exc:
                    logger.warning("gmail_reply_worker: send DM failed for %d: %s", owner_id, exc)

            if new_history_id:
                async with session_factory() as session:
                    async with session.begin():
                        await cfg_repo.set_config(session, owner_id, _KEY, new_history_id)

        except Exception:
            logger.exception("gmail_reply_worker iteration failed for owner %d", owner_id)


@beartype
async def run_loop(bot: Bot) -> None:
    while True:
        await asyncio.sleep(_CHECK_INTERVAL)
        try:
            await check_gmail_replies(bot)
        except Exception:
            logger.exception("gmail_reply_worker run_loop error")
