from __future__ import annotations

import logging
from datetime import timezone
from typing import Any

from beartype import beartype
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

GDOCS_SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "openid",
    "email",
]

GDOCS_DRIVE_FOLDER_KEY = "gdocs_drive_folder"


@beartype
def _build_gdocs_credentials(
    access_token: str,
    refresh_token: str | None,
    token_expiry: Any,
    scopes: str | None,
) -> Any:
    from google.oauth2.credentials import Credentials
    from config import settings

    return Credentials(  # type: ignore[no-untyped-call]
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=(scopes or "").split() if scopes else GDOCS_SCOPES,
        expiry=token_expiry.replace(tzinfo=None) if token_expiry else None,
    )


@beartype
async def get_gdocs_credentials(owner_id: int, session: AsyncSession) -> Any | None:
    from google.auth.transport.requests import Request
    from db.repositories import oauth as oauth_repo

    token_row = await oauth_repo.get_token(session, owner_id, "google_docs")
    if token_row is None:
        return None

    creds = _build_gdocs_credentials(
        token_row.access_token,
        token_row.refresh_token,
        token_row.token_expiry,
        token_row.scopes,
    )

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            await oauth_repo.upsert_token(
                session,
                owner_id,
                "google_docs",
                access_token=creds.token or "",
                refresh_token=creds.refresh_token,
                token_expiry=creds.expiry.replace(tzinfo=timezone.utc) if creds.expiry else None,
                scopes=" ".join(creds.scopes or []),
            )
        except Exception as e:
            logger.warning("Failed to refresh Google Docs token for owner %d: %s", owner_id, e)
            return None

    return creds


@beartype
async def ensure_drive_folder(creds: Any, owner_id: int, session: AsyncSession) -> str:
    from googleapiclient.discovery import build
    from db.repositories import integration_configs as cfg_repo

    existing = await cfg_repo.get_config(session, owner_id, GDOCS_DRIVE_FOLDER_KEY)
    if existing:
        return existing

    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    folder: dict[str, Any] = drive.files().create(
        body={"name": "NeuroSave", "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute()
    folder_id: str = folder["id"]
    await cfg_repo.set_config(session, owner_id, GDOCS_DRIVE_FOLDER_KEY, folder_id)
    return folder_id


@beartype
async def find_doc_id(owner_id: int, slug: str, session: AsyncSession) -> str | None:
    from db.repositories import integration_configs as cfg_repo

    return await cfg_repo.get_config(session, owner_id, f"gdocs_doc:{slug}")


@beartype
def _doc_slug(name: str) -> str:
    return name.lower().strip().replace(" ", "_")[:64]


@beartype
async def create_document(
    creds: Any,
    folder_id: str,
    title: str,
    content: str,
) -> tuple[str, str]:
    from googleapiclient.discovery import build

    docs = build("docs", "v1", credentials=creds, cache_discovery=False)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    doc: dict[str, Any] = docs.documents().create(body={"title": title}).execute()
    doc_id: str = doc["documentId"]
    url = f"https://docs.google.com/document/d/{doc_id}/edit"

    if content.strip():
        docs.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]},
        ).execute()

    drive.files().update(
        fileId=doc_id,
        addParents=folder_id,
        removeParents="root",
        fields="id, parents",
    ).execute()

    return doc_id, url


@beartype
async def append_to_document(creds: Any, doc_id: str, content: str) -> str:
    from googleapiclient.discovery import build

    docs = build("docs", "v1", credentials=creds, cache_discovery=False)
    doc: dict[str, Any] = docs.documents().get(documentId=doc_id).execute()
    end_index: int = doc["body"]["content"][-1]["endIndex"] - 1

    separator = "\n\n---\n\n"
    text = separator + content
    docs.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{"insertText": {"location": {"index": end_index}, "text": text}}]},
    ).execute()
    return f"https://docs.google.com/document/d/{doc_id}/edit"


@beartype
async def find_or_create_doc(
    creds: Any,
    owner_id: int,
    name: str,
    content: str,
    session: AsyncSession,
) -> tuple[str, str]:
    from db.repositories import integration_configs as cfg_repo

    slug = _doc_slug(name)
    doc_id = await find_doc_id(owner_id, slug, session)

    if doc_id:
        if content.strip():
            url = await append_to_document(creds, doc_id, content)
        else:
            url = f"https://docs.google.com/document/d/{doc_id}/edit"
        return doc_id, url

    folder_id = await ensure_drive_folder(creds, owner_id, session)
    doc_id, url = await create_document(creds, folder_id, name, content)
    await cfg_repo.set_config(session, owner_id, f"gdocs_doc:{slug}", doc_id)
    return doc_id, url


@beartype
async def list_drive_files(creds: Any, folder_id: str, limit: int = 10) -> list[dict[str, Any]]:
    from googleapiclient.discovery import build

    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    result: dict[str, Any] = drive.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        orderBy="modifiedTime desc",
        pageSize=limit,
        fields="files(id,name,mimeType,modifiedTime,webViewLink)",
    ).execute()

    files: list[dict[str, Any]] = []
    for f in result.get("files", []):
        mime = f.get("mimeType", "")
        files.append({
            "id": f["id"],
            "name": f["name"],
            "url": f.get("webViewLink", ""),
            "type": "sheet" if "spreadsheet" in mime else "doc",
            "modified_time": f.get("modifiedTime", ""),
        })
    return files
