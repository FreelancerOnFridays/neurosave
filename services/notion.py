from __future__ import annotations

import logging
import re
from typing import Any

from beartype import beartype
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

NOTION_ROOT_KEY = "notion_root_page_id"
NOTION_SECTIONS: dict[str, tuple[str, str]] = {
    "capture": ("📝", "Заметки"),
    "task": ("✅", "Задачи"),
    "meeting_notes": ("🤝", "Встречи"),
}


@beartype
async def get_notion_token(owner_id: int, session: AsyncSession) -> str | None:
    from db.repositories import oauth as oauth_repo

    row = await oauth_repo.get_token(session, owner_id, "notion")
    return row.access_token if row else None


def _make_rich_text(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"content": text[:2000]}}]


def _make_paragraph(text: str) -> dict[str, Any]:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _make_rich_text(text)}}


def _make_heading(text: str, level: int) -> dict[str, Any]:
    key = f"heading_{level}"
    return {"object": "block", "type": key, key: {"rich_text": _make_rich_text(text)}}


def _make_bullet(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _make_rich_text(text)},
    }


def _make_numbered(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "numbered_list_item",
        "numbered_list_item": {"rich_text": _make_rich_text(text)},
    }


def _make_todo(text: str, checked: bool) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "to_do",
        "to_do": {"rich_text": _make_rich_text(text), "checked": checked},
    }


def _make_callout(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": _make_rich_text(text),
            "icon": {"type": "emoji", "emoji": "📅"},
        },
    }


def _parse_blocks(text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for line in text.split("\n"):
        line = line.rstrip()
        if not line:
            continue
        if line.startswith("### "):
            blocks.append(_make_heading(line[4:], 3))
        elif line.startswith("## "):
            blocks.append(_make_heading(line[3:], 2))
        elif line.startswith("# "):
            blocks.append(_make_heading(line[2:], 1))
        elif line.startswith(("- ", "• ")):
            blocks.append(_make_bullet(line[2:]))
        elif re.match(r"^\d+\. ", line):
            blocks.append(_make_numbered(re.sub(r"^\d+\. ", "", line)))
        elif line.lower().startswith("[x] "):
            blocks.append(_make_todo(line[4:], checked=True))
        elif line.startswith("[] ") or line.startswith("[ ] "):
            offset = 3 if line.startswith("[] ") else 4
            blocks.append(_make_todo(line[offset:], checked=False))
        else:
            blocks.append(_make_paragraph(line))
    return blocks or [_make_paragraph(text)]


@beartype
async def ensure_root_page(token: str, owner_id: int, session: AsyncSession) -> str:
    from db.repositories import integration_configs as cfg_repo
    from notion_client import AsyncClient

    existing = await cfg_repo.get_config(session, owner_id, NOTION_ROOT_KEY)
    if existing:
        return existing

    notion = AsyncClient(auth=token)
    try:
        response: dict[str, Any] = await notion.pages.create(  # type: ignore[assignment]
            parent={"workspace": True},
            properties={"title": {"title": _make_rich_text("NeuroSave")}},
            icon={"type": "emoji", "emoji": "🧠"},
        )
    finally:
        await notion.aclose()

    root_id = str(response["id"])
    await cfg_repo.set_config(session, owner_id, NOTION_ROOT_KEY, root_id)
    return root_id


@beartype
async def ensure_section_page(token: str, owner_id: int, action: str, session: AsyncSession) -> str:
    from db.repositories import integration_configs as cfg_repo
    from notion_client import AsyncClient

    key = f"notion_section_{action}"
    existing = await cfg_repo.get_config(session, owner_id, key)
    if existing:
        return existing

    root_id = await ensure_root_page(token, owner_id, session)
    emoji_default, name_default = NOTION_SECTIONS.get(action, ("📄", action))
    custom_name = await cfg_repo.get_config(session, owner_id, f"notion_section_label_{action}")
    emoji, name = emoji_default, custom_name or name_default

    notion = AsyncClient(auth=token)
    try:
        response: dict[str, Any] = await notion.pages.create(  # type: ignore[assignment]
            parent={"page_id": root_id},
            properties={"title": {"title": _make_rich_text(name)}},
            icon={"type": "emoji", "emoji": emoji},
        )
    finally:
        await notion.aclose()

    section_id = str(response["id"])
    await cfg_repo.set_config(session, owner_id, key, section_id)
    return section_id


@beartype
async def create_page(
    token: str,
    parent_page_id: str,
    title: str,
    content: str,
) -> tuple[str, str]:
    from notion_client import AsyncClient

    notion = AsyncClient(auth=token)
    try:
        response: dict[str, Any] = await notion.pages.create(  # type: ignore[assignment]
            parent={"page_id": parent_page_id},
            properties={"title": {"title": _make_rich_text(title[:255])}},
            children=_parse_blocks(content) if content.strip() else [],
        )
    finally:
        await notion.aclose()

    return str(response.get("id", "")), str(response.get("url", ""))


@beartype
async def create_task_page(
    token: str,
    parent_page_id: str,
    title: str,
    due_date_iso: str | None = None,
) -> tuple[str, str]:
    from notion_client import AsyncClient

    notion = AsyncClient(auth=token)
    children: list[dict[str, Any]] = []
    if due_date_iso:
        children.append(_make_callout(f"Срок: {due_date_iso[:10]}"))

    try:
        response: dict[str, Any] = await notion.pages.create(  # type: ignore[assignment]
            parent={"page_id": parent_page_id},
            properties={"title": {"title": _make_rich_text(title[:255])}},
            children=children,
        )
    finally:
        await notion.aclose()

    return str(response.get("id", "")), str(response.get("url", ""))


@beartype
async def list_section_pages(
    token: str,
    section_id: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    from notion_client import AsyncClient

    notion = AsyncClient(auth=token)
    try:
        resp: dict[str, Any] = await notion.blocks.children.list(  # type: ignore[assignment]
            block_id=section_id,
            page_size=limit,
        )
    finally:
        await notion.aclose()

    pages: list[dict[str, Any]] = []
    for block in resp.get("results", []):
        if block.get("type") == "child_page":
            raw_id: str = block["id"]
            pages.append({
                "id": raw_id,
                "title": block["child_page"]["title"],
                "url": f"https://www.notion.so/{raw_id.replace('-', '')}",
                "created_time": block.get("created_time", ""),
            })
    return pages


@beartype
async def list_all_recent_pages(
    token: str,
    owner_id: int,
    session: AsyncSession,
) -> list[dict[str, Any]]:
    from db.repositories import integration_configs as cfg_repo

    actions = ["capture", "task", "meeting_notes"]
    all_pages: list[dict[str, Any]] = []
    for action in actions:
        key = f"notion_section_{action}"
        section_id = await cfg_repo.get_config(session, owner_id, key)
        if section_id:
            pages = await list_section_pages(token, section_id)
            for p in pages:
                p["section"] = action
            all_pages.extend(pages)

    all_pages.sort(key=lambda p: p.get("created_time", ""), reverse=True)
    return all_pages[:15]
