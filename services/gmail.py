from __future__ import annotations

import base64
import logging
import re
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from beartype import beartype
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Patterns that indicate automated/non-human senders
_AUTOMATED_PATTERNS = [
    "no-reply", "noreply", "do-not-reply", "donotreply",
    "mailer-daemon", "postmaster", "bounce@", "bounce+",
    "notifications@", "newsletter@", "automated@", "auto@",
    "system@", "digest@", "mail@mailchimp", "sendgrid",
]


def _is_automated_sender(from_: str) -> bool:
    low = from_.lower()
    return any(p in low for p in _AUTOMATED_PATTERNS)


def _extract_body(payload: dict[str, Any]) -> str:
    """Recursively extract plain-text body from a Gmail message payload."""
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    if mime.startswith("multipart/"):
        for part in payload.get("parts", []):
            text = _extract_body(part)
            if text:
                return text
    # Fallback: html → strip tags
    if mime == "text/html":
        data = payload.get("body", {}).get("data", "")
        if data:
            html = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            return re.sub(r"<[^>]+>", "", html).strip()
    return ""


def _collect_attachments(payload: dict[str, Any], result: list[dict[str, str]]) -> None:
    filename = payload.get("filename", "")
    att_id = payload.get("body", {}).get("attachmentId", "")
    if filename and att_id:
        result.append({
            "filename": filename,
            "attachment_id": att_id,
            "mime_type": payload.get("mimeType", "application/octet-stream"),
            "size": str(payload.get("body", {}).get("size", 0)),
        })
    for part in payload.get("parts", []):
        _collect_attachments(part, result)

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


def _extract_message_meta(msg: dict[str, Any], is_reply: bool = False) -> dict[str, Any]:
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    return {
        "id": msg.get("id", ""),
        "subject": headers.get("Subject") or "(без темы)",
        "from_": headers.get("From") or "",
        "to": headers.get("To") or "",
        "date": headers.get("Date") or "",
        "snippet": msg.get("snippet", ""),
        "is_reply": is_reply or bool(headers.get("In-Reply-To")),
    }


@beartype
async def list_threads(service: Any, max_results: int = 20) -> list[dict[str, Any]]:
    """List recent sent and received messages, excluding automated senders."""
    messages: list[dict[str, Any]] = []
    fetch_fields = ["Subject", "To", "From", "Date", "In-Reply-To"]

    for query in ("in:sent", "in:inbox"):
        try:
            result: dict[str, Any] = service.users().messages().list(
                userId="me", q=query, maxResults=max_results * 3
            ).execute()
            for msg_ref in result.get("messages", []):
                details: dict[str, Any] = service.users().messages().get(
                    userId="me",
                    id=msg_ref["id"],
                    format="metadata",
                    metadataHeaders=fetch_fields,
                ).execute()
                is_reply = query == "in:inbox"
                meta = _extract_message_meta(details, is_reply=is_reply)
                # Skip automated senders for inbox messages
                if is_reply and _is_automated_sender(meta.get("from_", "")):
                    continue
                messages.append(meta)
        except Exception as exc:
            logger.warning("Gmail list_threads error (query=%s): %s", query, exc)

    messages.sort(key=lambda m: m.get("date", ""), reverse=True)
    return messages[:max_results]


@beartype
async def get_message_full(service: Any, msg_id: str) -> dict[str, Any]:
    """Fetch full message with decoded body and attachment list."""
    msg: dict[str, Any] = service.users().messages().get(
        userId="me", id=msg_id, format="full"
    ).execute()
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    body_text = _extract_body(msg.get("payload", {}))
    attachments: list[dict[str, str]] = []
    _collect_attachments(msg.get("payload", {}), attachments)
    return {
        "id": msg.get("id", ""),
        "thread_id": msg.get("threadId", ""),
        "subject": headers.get("Subject") or "(без темы)",
        "from_": headers.get("From") or "",
        "to": headers.get("To") or "",
        "date": headers.get("Date") or "",
        "body": body_text,
        "snippet": msg.get("snippet", ""),
        "attachments": attachments,
        "is_reply": bool(headers.get("In-Reply-To")),
        "message_id_header": headers.get("Message-ID") or "",
    }


@beartype
async def send_reply(
    service: Any,
    to: list[str],
    subject: str,
    body: str,
    thread_id: str | None = None,
    in_reply_to: str | None = None,
) -> str:
    """Send an email, optionally as a reply to an existing thread."""
    msg: MIMEText = MIMEText(body, "plain", "utf-8")
    msg["to"] = ", ".join(to)
    msg["subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to

    body_dict: dict[str, str] = {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}
    if thread_id:
        body_dict["threadId"] = thread_id

    result: dict[str, Any] = service.users().messages().send(
        userId="me", body=body_dict
    ).execute()
    return str(result.get("id", ""))


# Gmail label IDs that indicate automated/bulk/non-human messages
_SKIP_LABELS = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_UPDATES", "SPAM", "TRASH"}


@beartype
async def get_history_since(service: Any, start_history_id: str) -> list[dict[str, Any]]:
    """Return new human inbox messages since the given Gmail historyId."""
    try:
        resp: dict[str, Any] = service.users().history().list(
            userId="me",
            startHistoryId=start_history_id,
            historyTypes=["messageAdded"],
            labelId="INBOX",
        ).execute()
    except Exception as exc:
        logger.warning("Gmail get_history_since failed: %s", exc)
        return []

    messages: list[dict[str, Any]] = []
    for record in resp.get("history", []):
        for added in record.get("messagesAdded", []):
            raw_msg = added.get("message", {})
            msg_id = raw_msg.get("id")
            if not msg_id:
                continue
            # Quick label check — skip promo/social/updates/spam without a full fetch
            label_ids: set[str] = set(raw_msg.get("labelIds", []))
            if label_ids & _SKIP_LABELS:
                continue
            try:
                details: dict[str, Any] = service.users().messages().get(
                    userId="me",
                    id=msg_id,
                    format="metadata",
                    metadataHeaders=["Subject", "From", "Date", "In-Reply-To"],
                ).execute()
                # Double-check labels from full metadata response
                detail_labels: set[str] = set(details.get("labelIds", []))
                if detail_labels & _SKIP_LABELS:
                    continue
                meta = _extract_message_meta(details, is_reply=True)
                # Skip automated senders
                if _is_automated_sender(meta.get("from_", "")):
                    continue
                messages.append(meta)
            except Exception as exc:
                logger.warning("Gmail get_message detail failed for %s: %s", msg_id, exc)
    return messages


@beartype
async def get_gmail_address(owner_id: int, session: AsyncSession) -> str | None:
    """Return the authenticated Gmail address for this owner, or None."""
    from db.repositories import oauth as oauth_repo

    token_row = await oauth_repo.get_token(session, owner_id, "gmail")
    return token_row.email if token_row else None
