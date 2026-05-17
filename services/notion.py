from __future__ import annotations

import logging
from typing import Any

from beartype import beartype
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

NOTION_DB_KEY = "notion_db_id"


@beartype
async def get_notion_token(owner_id: int, session: AsyncSession) -> str | None:
    from db.repositories import oauth as oauth_repo

    row = await oauth_repo.get_token(session, owner_id, "notion")
    return row.access_token if row else None


@beartype
async def get_notion_db_id(owner_id: int, session: AsyncSession) -> str | None:
    from db.repositories import integration_configs as cfg_repo

    return await cfg_repo.get_config(session, owner_id, NOTION_DB_KEY)


@beartype
async def set_notion_db_id(owner_id: int, db_id: str, session: AsyncSession) -> None:
    from db.repositories import integration_configs as cfg_repo

    await cfg_repo.set_config(session, owner_id, NOTION_DB_KEY, db_id.strip())


def _make_rich_text(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"content": text[:2000]}}]


def _make_paragraph(text: str) -> dict[str, Any]:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _make_rich_text(text)}}


def _split_into_paragraphs(text: str) -> list[dict[str, Any]]:
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    return [_make_paragraph(p) for p in paragraphs] or [_make_paragraph(text)]


@beartype
async def create_page(token: str, db_id: str, title: str, content: str) -> str:
    from notion_client import AsyncClient

    notion = AsyncClient(auth=token)
    response: dict[str, Any] = await notion.pages.create(  # type: ignore[assignment]
        parent={"database_id": db_id},
        properties={"title": {"title": _make_rich_text(title[:255])}},
        children=_split_into_paragraphs(content),
    )
    await notion.aclose()
    return str(response.get("id", ""))


@beartype
async def create_task_page(
    token: str,
    db_id: str,
    title: str,
    due_date_iso: str | None = None,
) -> str:
    from notion_client import AsyncClient

    notion = AsyncClient(auth=token)
    properties: dict[str, Any] = {"title": {"title": _make_rich_text(title[:255])}}
    if due_date_iso:
        properties["Due"] = {"date": {"start": due_date_iso[:10]}}

    response: dict[str, Any] = await notion.pages.create(  # type: ignore[assignment]
        parent={"database_id": db_id},
        properties=properties,
    )
    await notion.aclose()
    return str(response.get("id", ""))


@beartype
async def list_databases(token: str) -> list[tuple[str, str]]:
    from notion_client import AsyncClient

    notion = AsyncClient(auth=token)
    results: list[tuple[str, str]] = []
    try:
        response: dict[str, Any] = await notion.search(  # type: ignore[assignment]
            filter={"property": "object", "value": "database"},
        )
        for db in response.get("results", []):
            db_id: str = db.get("id", "")
            title_parts: list[Any] = db.get("title", [])
            title: str = title_parts[0].get("plain_text", "Untitled") if title_parts else "Untitled"
            results.append((db_id, title))
    finally:
        await notion.aclose()
    return results
