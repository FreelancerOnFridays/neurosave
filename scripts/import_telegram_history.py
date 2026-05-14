"""Import Telegram Desktop chat export into the NeuroSave database.

Usage:
    uv run python -m scripts.import_telegram_history <path_to_export_folder>

How to export from Telegram Desktop:
    1. Open Telegram Desktop
    2. Open a chat
    3. Click ⋮ → Export chat history
    4. Uncheck media, select JSON format, set date range
    5. Point this script at the folder that contains result.json files

The script is idempotent — duplicate (chat_id, message_id) pairs are skipped.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from db.engine import get_session
from db.models import Message
from db.repositories import contacts as contact_repo
from db.repositories import messages as msg_repo
from services.ai import embed_text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OWNER_ID: int = 0  # set from .env at runtime
EMBED_BATCH = 20


def _parse_ts(date_str: str) -> datetime:
    """Parse Telegram export date string to UTC datetime."""
    dt = datetime.fromisoformat(date_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _extract_text(text_field: object) -> str:
    """Telegram text fields can be a string or a list of mixed str/dict parts."""
    if isinstance(text_field, str):
        return text_field
    if isinstance(text_field, list):
        parts: list[str] = []
        for part in text_field:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(part.get("text", ""))
        return "".join(parts)
    return ""


async def import_file(path: Path, owner_id: int) -> tuple[int, int]:
    """Import one result.json file. Returns (imported, skipped)."""
    data = json.loads(path.read_text(encoding="utf-8"))

    chat_name: str = data.get("name", "")
    chat_id_raw: int | str = data.get("id", 0)
    try:
        chat_id = int(str(chat_id_raw).lstrip("user").lstrip("channel"))
    except ValueError:
        logger.warning("Could not parse chat_id from %s, skipping", path)
        return 0, 0

    messages: list[dict[object, object]] = data.get("messages", [])
    logger.info("Chat '%s' (id=%d): %d messages", chat_name, chat_id, len(messages))

    # Fetch existing message_ids to skip duplicates
    async with get_session() as session:
        result = await session.execute(
            select(Message.message_id).where(
                Message.owner_id == owner_id,
                Message.chat_id == chat_id,
            )
        )
        existing_ids: set[int] = {row[0] for row in result.all()}

    imported = skipped = 0
    pending_embed: list[tuple[int, str]] = []  # (db_id, embed_text)

    async with get_session() as session:
        # Build name map for alias resolution
        name_map = await contact_repo.get_name_map(session, owner_id)

    for raw in messages:
        if not isinstance(raw, dict):
            continue
        if raw.get("type") != "message":
            continue
        text = _extract_text(raw.get("text", ""))
        if not text.strip():
            skipped += 1
            continue

        msg_id = int(raw.get("id", 0))  # type: ignore[arg-type]
        if msg_id in existing_ids:
            skipped += 1
            continue

        date_str = raw.get("date", "")
        try:
            ts = _parse_ts(str(date_str))
        except Exception:
            skipped += 1
            continue

        from_id_raw = raw.get("from_id", "")
        try:
            sender_id: int | None = int(str(from_id_raw).lstrip("user").lstrip("channel"))
        except (ValueError, AttributeError):
            sender_id = None

        sender_name: str | None = raw.get("from") or None  # type: ignore[assignment]
        if isinstance(sender_name, str) and not sender_name:
            sender_name = None

        async with get_session() as session:
            try:
                saved = await msg_repo.save_message(
                    session,
                    owner_id=owner_id,
                    chat_id=chat_id,
                    message_id=msg_id,
                    sender_id=sender_id,
                    sender_name=sender_name,
                    text=text,
                    timestamp=ts,
                )
                existing_ids.add(msg_id)
                # Resolve alias for embedding
                display = (name_map.get(sender_id) if sender_id else None) or sender_name
                embed_str = f"{display}: {text}" if display else text
                pending_embed.append((saved.id, embed_str))
                imported += 1
            except IntegrityError:
                skipped += 1

    # Embed in batches
    logger.info("Embedding %d new messages…", len(pending_embed))
    for i in range(0, len(pending_embed), EMBED_BATCH):
        batch = pending_embed[i : i + EMBED_BATCH]
        embeddings = await asyncio.gather(
            *[embed_text(t) for _, t in batch], return_exceptions=True
        )
        async with get_session() as session:
            for (db_id, _), emb in zip(batch, embeddings):
                if isinstance(emb, Exception):
                    logger.warning("Embed failed for message db_id=%d: %s", db_id, emb)
                    continue
                await msg_repo.set_embedding(session, db_id, emb)
        logger.info("  embedded batch %d–%d", i + 1, i + len(batch))

    return imported, skipped


async def main(export_dir: str) -> None:
    from config import settings
    owner_id = settings.owner_chat_id

    root = Path(export_dir)
    json_files = sorted(root.rglob("result.json"))
    if not json_files:
        logger.error("No result.json files found in %s", export_dir)
        return

    total_imported = total_skipped = 0
    for f in json_files:
        imp, skip = await import_file(f, owner_id)
        total_imported += imp
        total_skipped += skip
        logger.info("  → imported %d, skipped %d", imp, skip)

    logger.info("Done. Total imported: %d, skipped: %d", total_imported, total_skipped)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.import_telegram_history <export_folder>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
