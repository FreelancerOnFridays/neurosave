from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from beartype import beartype
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
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
async def get_gmail_service(owner_id: int, session: AsyncSession) -> Any | None:
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    from db.repositories import oauth as oauth_repo

    token_row = await oauth_repo.get_token(session, owner_id, "gmail")
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
                "gmail",
                access_token=creds.token or "",
                refresh_token=creds.refresh_token,
                token_expiry=creds.expiry.replace(tzinfo=timezone.utc) if creds.expiry else None,
                scopes=" ".join(creds.scopes or []),
            )
        except Exception as e:
            logger.warning("Failed to refresh Gmail token for owner %d: %s", owner_id, e)
            return None

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


@beartype
async def send_email(
    service: Any,
    to: list[str],
    subject: str,
    body: str,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> str:
    """Send email via Gmail API. attachments: list of (filename, data, mime_type)."""
    if attachments:
        msg: MIMEMultipart | MIMEText = MIMEMultipart()
        assert isinstance(msg, MIMEMultipart)
        msg.attach(MIMEText(body, "plain", "utf-8"))
        for filename, data, mime_type in attachments:
            main_type, sub_type = (mime_type.split("/", 1) if "/" in mime_type else ("application", "octet-stream"))
            part = MIMEApplication(data, _subtype=sub_type)
            part.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(part)
    else:
        msg = MIMEText(body, "plain", "utf-8")

    msg["to"] = ", ".join(to)
    msg["subject"] = subject

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    result: dict[str, Any] = (
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
    )
    return str(result.get("id", ""))


@beartype
async def get_gmail_address(owner_id: int, session: AsyncSession) -> str | None:
    """Return the authenticated Gmail address for this owner, or None."""
    from db.repositories import oauth as oauth_repo

    token_row = await oauth_repo.get_token(session, owner_id, "gmail")
    return token_row.email if token_row else None
