from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from db.engine import get_session
from db.models import Message
from db.repositories import contacts as contact_repo
from db.repositories import messages as msg_repo
from services.ai import embed_text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

BATCH = 20  # concurrent embed calls


async def backfill() -> None:
    async with get_session() as session:
        result = await session.execute(select(Message))
        messages = list(result.scalars().all())
        # Build owner_id -> name_map once for all messages
        owner_ids = {m.owner_id for m in messages}
        name_maps: dict[int, dict[int, str]] = {}
        for owner_id in owner_ids:
            name_maps[owner_id] = await contact_repo.get_name_map(session, owner_id)

    logger.info("Found %d messages to (re-)embed", len(messages))

    def _text(m: Message) -> str:
        nm = name_maps.get(m.owner_id, {})
        who = (nm.get(m.sender_id) if m.sender_id else None) or m.sender_name
        return f"{who}: {m.text}" if who else m.text

    for i in range(0, len(messages), BATCH):
        batch = messages[i : i + BATCH]
        logger.info("Embedding batch %d-%d …", i + 1, i + len(batch))

        embeddings = await asyncio.gather(
            *[embed_text(_text(m)) for m in batch], return_exceptions=True
        )

        async with get_session() as session:
            for msg, emb in zip(batch, embeddings):
                if isinstance(emb, Exception):
                    logger.warning("Failed to embed message %d: %s", msg.id, emb)
                    continue
                await msg_repo.set_embedding(session, msg.id, emb)

    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(backfill())
