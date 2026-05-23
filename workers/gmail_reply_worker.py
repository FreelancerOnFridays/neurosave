from __future__ import annotations

import asyncio
import base64
import html
import logging
from typing import Any

from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from beartype import beartype

from db.engine import session_factory
from db.repositories import integration_configs as cfg_repo
from db.repositories import oauth as oauth_repo
from db.repositories import user_settings as us_repo
from services.gmail import strip_quoted_reply

logger = logging.getLogger(__name__)

_CHECK_INTERVAL = 30  # every 30 seconds
_CAPTION_LIMIT = 1024  # Telegram caption character limit

_KEY = "gmail_history_id"

# In-memory store of message metadata for Reply button; keyed by Gmail message ID.
# Lives only for the process lifetime — button won't work after restart (handled gracefully).
_gmail_reply_store: dict[str, dict[str, Any]] = {}


def _sender_name(from_: str) -> str:
    import re
    match = re.match(r'^"?([^"<]+)"?\s*<', from_)
    return match.group(1).strip() if match else from_.replace("<.*>", "").strip() or from_


def _format_reply(msg: dict[str, Any], body: str = "") -> str:
    sender = html.escape(_sender_name(msg.get("from_", "")))
    subject = html.escape(msg.get("subject") or "")

    if body:
        clean = strip_quoted_reply(body)
    else:
        # snippet is already stripped by Gmail — use as-is
        clean = msg.get("snippet") or ""

    # Trim to reasonable length, preserve line breaks up to 3 lines
    clean = clean.strip()
    if len(clean) > 500:
        clean = clean[:500] + "…"
    preview = html.escape(clean)

    lines = [f"📨 <b>{sender}</b>"]
    if subject and subject.lower() not in {"(без темы)", ""}:
        lines.append(f"<b>Тема:</b> {subject}")
    if preview:
        lines.append(f"<blockquote>{preview}</blockquote>")
    return "\n".join(lines)


@beartype
async def _init_history_id(service: object, owner_id: int) -> str | None:
    try:
        profile: dict[str, Any] = service.users().getProfile(userId="me").execute()  # type: ignore[attr-defined]
        history_id = str(profile.get("historyId", ""))
        if history_id:
            async with session_factory() as sess:
                async with sess.begin():
                    await cfg_repo.set_config(sess, owner_id, _KEY, history_id)
            logger.info("gmail_reply_worker: initialized historyId=%s for owner %d", history_id, owner_id)
            return history_id
    except Exception as exc:
        logger.warning("gmail_reply_worker: failed to get historyId for %d: %s", owner_id, exc)
    return None


async def _fetch_attachment_bytes(service: Any, msg_id: str, att_id: str) -> bytes | None:
    try:
        result: dict[str, Any] = service.users().messages().attachments().get(
            userId="me", messageId=msg_id, id=att_id
        ).execute()
        raw_data = result.get("data", "")
        return base64.urlsafe_b64decode(raw_data + "==") if raw_data else None
    except Exception as exc:
        logger.warning("gmail_reply_worker: attachment fetch failed for %s: %s", att_id, exc)
        return None


async def _send_one_attachment(
    bot: Bot,
    owner_id: int,
    service: Any,
    msg_id: str,
    att: dict[str, str],
    caption: str = "",
    keyboard: InlineKeyboardMarkup | None = None,
) -> bool:
    """Download and send a single attachment. Returns True on success."""
    filename = att.get("filename", "attachment")
    att_id = att.get("attachment_id", "")
    if not att_id:
        return False
    file_bytes = await _fetch_attachment_bytes(service, msg_id, att_id)
    if file_bytes is None:
        return False
    try:
        mime = att.get("mime_type", "")
        buf = BufferedInputFile(file_bytes, filename=filename)
        if mime.startswith("video/"):
            await bot.send_video(
                chat_id=owner_id,
                video=buf,
                caption=caption or None,
                parse_mode="HTML" if caption else None,
                reply_markup=keyboard,
            )
        else:
            await bot.send_document(
                chat_id=owner_id,
                document=buf,
                caption=caption or None,
                parse_mode="HTML" if caption else None,
                reply_markup=keyboard,
            )
        return True
    except Exception as exc:
        logger.warning("gmail_reply_worker: failed to send attachment %s: %s", filename, exc)
        return False


async def _download_and_send_attachments(
    bot: Bot,
    owner_id: int,
    service: Any,
    msg_id: str,
    attachments: list[dict[str, str]],
    link_caption: str = "",
) -> None:
    for att in attachments:
        await _send_one_attachment(bot, owner_id, service, msg_id, att, caption=link_caption)


@beartype
async def check_gmail_replies(bot: Bot) -> None:
    from services.gmail import get_gmail_service, get_history_since, get_message_full

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
                await _init_history_id(service, owner_id)
                continue

            try:
                messages = await get_history_since(service, history_id)
            except Exception as exc:
                err_str = str(exc).lower()
                # Only re-initialize for stale/invalid historyId (HTTP 404/410).
                # For network or rate-limit errors keep the existing historyId and retry.
                if "404" in err_str or "410" in err_str or "invalid" in err_str:
                    logger.warning("gmail_reply_worker: invalid historyId for %d, re-initializing: %s", owner_id, exc)
                    await _init_history_id(service, owner_id)
                else:
                    logger.warning("gmail_reply_worker: transient error for %d, will retry: %s", owner_id, exc)
                continue

            # Advance historyId to stay current
            try:
                profile: dict[str, Any] = service.users().getProfile(userId="me").execute()
                new_history_id = str(profile.get("historyId", ""))
            except Exception:
                new_history_id = ""

            # Check if notifications are enabled (default: on)
            async with session_factory() as notif_sess:
                notif_val = await cfg_repo.get_config(notif_sess, owner_id, "gmail_notifications_enabled")

            if notif_val == "0":
                if new_history_id:
                    async with session_factory() as session:
                        async with session.begin():
                            await cfg_repo.set_config(session, owner_id, _KEY, new_history_id)
                continue

            for msg in messages:
                msg_id = msg.get("id", "")

                # Fetch full message for body + attachments + reply metadata
                body = ""
                attachments: list[dict[str, str]] = []
                if msg_id:
                    try:
                        full = await get_message_full(service, msg_id)
                        body = full.get("body", "")
                        attachments = full.get("attachments", [])
                        _gmail_reply_store[msg_id] = {
                            "from_": full.get("from_", msg.get("from_", "")),
                            "thread_id": full.get("thread_id", ""),
                            "message_id_header": full.get("message_id_header", ""),
                            "subject": full.get("subject", msg.get("subject", "")),
                        }
                    except Exception as exc:
                        logger.warning("gmail_reply_worker: full fetch failed for %s: %s", msg_id, exc)

                keyboard: InlineKeyboardMarkup | None = None
                if msg_id:
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(
                            text="📧 Ответить",
                            callback_data=f"gmail_reply:{owner_id}:{msg_id}",
                        ),
                    ]])

                text = _format_reply(msg, body=body)

                # If the first attachment fits as a caption, send it with the
                # notification text embedded — so media visually belongs to the email.
                sent_as_media = False
                if attachments and msg_id and len(text) <= _CAPTION_LIMIT:
                    sent_as_media = await _send_one_attachment(
                        bot, owner_id, service, msg_id, attachments[0],
                        caption=text, keyboard=keyboard,
                    )

                if not sent_as_media:
                    try:
                        await bot.send_message(
                            chat_id=owner_id,
                            text=text,
                            parse_mode="HTML",
                            reply_markup=keyboard,
                        )
                    except Exception as exc:
                        logger.warning("gmail_reply_worker: send DM failed for %d: %s", owner_id, exc)
                        continue

                # Send remaining attachments (or all if we fell back to text-first)
                remaining = attachments[1:] if sent_as_media else attachments
                if remaining and msg_id:
                    await _download_and_send_attachments(
                        bot, owner_id, service, msg_id, remaining,
                        link_caption="📎 ещё вложение к письму выше",
                    )

            if new_history_id:
                async with session_factory() as session:
                    async with session.begin():
                        await cfg_repo.set_config(session, owner_id, _KEY, new_history_id)

        except Exception:
            logger.exception("gmail_reply_worker iteration failed for owner %d", owner_id)


@beartype
async def run_loop(bot: Bot) -> None:
    # Run immediately on startup to initialize historyId without waiting
    try:
        await check_gmail_replies(bot)
    except Exception:
        logger.exception("gmail_reply_worker initial check error")
    while True:
        await asyncio.sleep(_CHECK_INTERVAL)
        try:
            await check_gmail_replies(bot)
        except Exception:
            logger.exception("gmail_reply_worker run_loop error")
