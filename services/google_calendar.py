from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from beartype import beartype
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "openid",
    "email",
]


@beartype
def _build_credentials(
    access_token: str,
    refresh_token: str | None,
    token_expiry: datetime | None,
    scopes: str | None,
) -> Any:
    # google.oauth2.credentials.Credentials has no type stubs; Any is necessary
    from google.oauth2.credentials import Credentials
    from config import settings

    return Credentials(  # type: ignore[no-untyped-call]
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=(scopes or "").split() if scopes else SCOPES,
        expiry=token_expiry.replace(tzinfo=None) if token_expiry else None,
    )


@beartype
async def get_calendar_service(owner_id: int, session: AsyncSession) -> Any:
    # Returns googleapiclient Resource — no stubs available
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    from db.repositories import oauth as oauth_repo

    token_row = await oauth_repo.get_token(session, owner_id, "google")
    if token_row is None:
        return None

    creds = _build_credentials(
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
                "google",
                access_token=creds.token or "",
                refresh_token=creds.refresh_token,
                token_expiry=creds.expiry.replace(tzinfo=timezone.utc) if creds.expiry else None,
                scopes=" ".join(creds.scopes or []),
            )
        except Exception as e:
            logger.warning("Failed to refresh Google token for owner %d: %s", owner_id, e)
            return None

    return build("calendar", "v3", credentials=creds, cache_discovery=False)


@beartype
async def create_calendar_event(
    service: Any,
    title: str,
    start_dt: datetime,
    end_dt: datetime | None = None,
    description: str = "",
    calendar_id: str = "primary",
) -> str:
    if end_dt is None:
        end_dt = start_dt + timedelta(hours=1)

    body = {
        "summary": title,
        "description": description,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "UTC"},
    }

    try:
        event: dict[str, Any] = service.events().insert(calendarId=calendar_id, body=body).execute()
        return str(event.get("id", ""))
    except Exception as e:
        logger.error("Google Calendar API error: %s", e)
        raise


@beartype
async def sync_task_deadline(
    owner_id: int,
    description: str,
    deadline: datetime,
    session: AsyncSession,
) -> str | None:
    service = await get_calendar_service(owner_id, session)
    if service is None:
        return None
    try:
        event_id = await create_calendar_event(service, description, deadline)
        logger.info("Created calendar event %s for owner %d", event_id, owner_id)
        return event_id
    except Exception as e:
        logger.warning("Calendar sync failed for owner %d: %s", owner_id, e)
        return None
