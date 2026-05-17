from __future__ import annotations

import logging
from typing import Any

from beartype import beartype
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@beartype
def _sheet_slug(name: str) -> str:
    return name.lower().strip().replace(" ", "_")[:64]


@beartype
async def find_sheet_id(owner_id: int, slug: str, session: AsyncSession) -> str | None:
    from db.repositories import integration_configs as cfg_repo

    return await cfg_repo.get_config(session, owner_id, f"gdocs_sheet:{slug}")


@beartype
async def create_spreadsheet(creds: Any, folder_id: str, title: str) -> tuple[str, str]:
    from googleapiclient.discovery import build

    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    spreadsheet: dict[str, Any] = sheets.spreadsheets().create(
        body={"properties": {"title": title}},
        fields="spreadsheetId",
    ).execute()
    sheet_id: str = spreadsheet["spreadsheetId"]
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"

    drive.files().update(
        fileId=sheet_id,
        addParents=folder_id,
        removeParents="root",
        fields="id, parents",
    ).execute()

    return sheet_id, url


def _first_sheet_title(sheets: Any, sheet_id: str) -> str:
    """Return the title of the first tab; falls back to 'Sheet1'."""
    try:
        meta: dict[str, Any] = sheets.spreadsheets().get(
            spreadsheetId=sheet_id,
            fields="sheets.properties.title",
        ).execute()
        tabs: list[dict[str, Any]] = meta.get("sheets", [])
        if tabs:
            return str(tabs[0].get("properties", {}).get("title", "Sheet1"))
    except Exception as e:
        logger.warning("Could not fetch sheet metadata for %s: %s", sheet_id, e)
    return "Sheet1"


@beartype
async def append_row(creds: Any, sheet_id: str, values: list[str]) -> str:
    from googleapiclient.discovery import build

    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
    tab = _first_sheet_title(sheets, sheet_id)
    sheets.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=tab,
        valueInputOption="USER_ENTERED",
        body={"values": [values]},
    ).execute()
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"


@beartype
async def get_recent_rows(creds: Any, sheet_id: str, n: int = 5) -> list[list[str]]:
    from googleapiclient.discovery import build

    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
    tab = _first_sheet_title(sheets, sheet_id)
    try:
        result: dict[str, Any] = sheets.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=tab,
        ).execute()
        rows: list[list[str]] = result.get("values", [])
        return rows[-n:] if len(rows) > n else rows
    except Exception as e:
        logger.warning("get_recent_rows failed for sheet %s: %s", sheet_id, e)
        return []


@beartype
async def read_full_sheet(creds: Any, sheet_id: str) -> list[list[str]]:
    """Return all rows from the first tab of a spreadsheet."""
    from googleapiclient.discovery import build

    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
    tab = _first_sheet_title(sheets, sheet_id)
    try:
        result: dict[str, Any] = sheets.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=tab,
        ).execute()
        raw: list[list[Any]] = result.get("values", [])
        return [[str(c) for c in row] for row in raw]
    except Exception as e:
        logger.warning("read_full_sheet failed for %s: %s", sheet_id, e)
        return []


@beartype
async def find_or_create_sheet(
    creds: Any,
    owner_id: int,
    name: str,
    session: AsyncSession,
) -> tuple[str, str]:
    from services.google_docs import ensure_drive_folder
    from db.repositories import integration_configs as cfg_repo

    slug = _sheet_slug(name)
    sheet_id = await find_sheet_id(owner_id, slug, session)

    if sheet_id:
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
        return sheet_id, url

    folder_id = await ensure_drive_folder(creds, owner_id, session)
    sheet_id, url = await create_spreadsheet(creds, folder_id, name)
    await cfg_repo.set_config(session, owner_id, f"gdocs_sheet:{slug}", sheet_id)
    return sheet_id, url
