from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_owner_id
from api.dependencies import get_db
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Allow Google to return full scope URLs instead of short aliases (e.g. "email" → userinfo.email)
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
# Allow OAuth over HTTP in dev (no-op in prod behind HTTPS reverse proxy)
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

# In-memory state store: state_token → (owner_id, expires_at, code_verifier_or_none)
_oauth_states: dict[str, tuple[int, float, str | None]] = {}

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "openid",
    "email",
]

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "openid",
    "email",
]

GDOCS_SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "openid",
    "email",
]


class IntegrationStatus(BaseModel):
    provider: str
    connected: bool
    email: str | None = None
    scopes: list[str] = []


class IntegrationsStatusOut(BaseModel):
    google_calendar: IntegrationStatus
    gmail: IntegrationStatus
    google_docs: IntegrationStatus


class AuthUrlOut(BaseModel):
    url: str


def _gc_states() -> None:
    now = time.time()
    expired = [k for k, (_, exp, _v) in _oauth_states.items() if exp < now]
    for k in expired:
        del _oauth_states[k]


def _generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge_S256)."""
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


def _make_state(owner_id: int) -> str:
    """Create state token without PKCE (used for Notion)."""
    _gc_states()
    token = secrets.token_urlsafe(32)
    _oauth_states[token] = (owner_id, time.time() + 600, None)
    return token


def _make_state_pkce(owner_id: int) -> tuple[str, str, str]:
    """Create state token with PKCE. Returns (state, code_verifier, code_challenge)."""
    _gc_states()
    token = secrets.token_urlsafe(32)
    verifier, challenge = _generate_pkce_pair()
    _oauth_states[token] = (owner_id, time.time() + 600, verifier)
    return token, verifier, challenge


def _consume_state(state: str) -> tuple[int, str | None] | tuple[None, None]:
    _gc_states()
    entry = _oauth_states.pop(state, None)
    if entry is None:
        return None, None
    owner_id, expires_at, verifier = entry
    if time.time() > expires_at:
        return None, None
    return owner_id, verifier


@router.get("/status", response_model=IntegrationsStatusOut)
async def integrations_status(
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> IntegrationsStatusOut:
    from db.repositories import oauth as oauth_repo

    google_row = await oauth_repo.get_token(session, owner_id, "google")
    google_status = IntegrationStatus(
        provider="google",
        connected=google_row is not None,
        email=google_row.email if google_row else None,
        scopes=(google_row.scopes or "").split() if google_row else [],
    )
    gmail_row = await oauth_repo.get_token(session, owner_id, "gmail")
    gmail_status = IntegrationStatus(
        provider="gmail",
        connected=gmail_row is not None,
        email=gmail_row.email if gmail_row else None,
        scopes=(gmail_row.scopes or "").split() if gmail_row else [],
    )
    gdocs_row = await oauth_repo.get_token(session, owner_id, "google_docs")
    gdocs_status = IntegrationStatus(
        provider="google_docs",
        connected=gdocs_row is not None,
        email=gdocs_row.email if gdocs_row else None,
        scopes=(gdocs_row.scopes or "").split() if gdocs_row else [],
    )
    return IntegrationsStatusOut(
        google_calendar=google_status,
        gmail=gmail_status,
        google_docs=gdocs_status,
    )


@router.get("/google/auth-url", response_model=AuthUrlOut)
async def google_auth_url(
    owner_id: int = Depends(get_owner_id),
) -> AuthUrlOut:
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    from google_auth_oauthlib.flow import Flow

    redirect_uri = f"{settings.api_base_url}/api/integrations/google/callback"
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=GOOGLE_SCOPES,
        redirect_uri=redirect_uri,
    )
    state, _verifier, challenge = _make_state_pkce(owner_id)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
        include_granted_scopes="true",
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    return AuthUrlOut(url=auth_url)


_SUCCESS_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Google Calendar подключён</title>
  <style>
    body {{ font-family: system-ui, sans-serif; display: flex; flex-direction: column;
           align-items: center; justify-content: center; min-height: 100vh;
           margin: 0; background: #f0fdf4; color: #166534; }}
    h1 {{ font-size: 1.5rem; margin-bottom: .5rem; }}
    p {{ color: #15803d; font-size: .95rem; }}
    a {{ display: inline-block; margin-top: 1.5rem; padding: .75rem 1.5rem;
         background: #16a34a; color: #fff; border-radius: 12px;
         text-decoration: none; font-weight: 600; }}
  </style>
</head>
<body>
  <h1>✅ Google Calendar подключён!</h1>
  <p>Вернитесь в Telegram и обновите страницу в мини-приложении.</p>
  <a href="https://t.me/{bot_username}">Открыть NeuroSave</a>
</body>
</html>"""

_ERROR_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Ошибка</title>
  <style>
    body {{ font-family: system-ui, sans-serif; display: flex; flex-direction: column;
           align-items: center; justify-content: center; min-height: 100vh;
           margin: 0; background: #fef2f2; color: #991b1b; }}
    h1 {{ font-size: 1.5rem; margin-bottom: .5rem; }}
    p {{ color: #b91c1c; font-size: .95rem; }}
  </style>
</head>
<body>
  <h1>❌ Ошибка подключения</h1>
  <p>{error}</p>
</body>
</html>"""


@router.get("/google/callback", response_class=HTMLResponse)
async def google_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    if error:
        return HTMLResponse(_ERROR_HTML.format(error=error), status_code=400)
    if not code or not state:
        return HTMLResponse(_ERROR_HTML.format(error="Отсутствуют параметры code/state"), status_code=400)

    owner_id, code_verifier = _consume_state(state)
    if owner_id is None:
        return HTMLResponse(_ERROR_HTML.format(error="Неверный или истёкший state-параметр"), status_code=400)

    try:
        from google_auth_oauthlib.flow import Flow
        from db.repositories import oauth as oauth_repo

        redirect_uri = f"{settings.api_base_url}/api/integrations/google/callback"
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri],
                }
            },
            scopes=GOOGLE_SCOPES,
            redirect_uri=redirect_uri,
        )
        flow.fetch_token(code=code, code_verifier=code_verifier)
        creds = flow.credentials

        # Get user email
        user_email: str | None = None
        try:
            from googleapiclient.discovery import build
            oauth2_service = build("oauth2", "v2", credentials=creds, cache_discovery=False)
            user_info: dict[str, Any] = oauth2_service.userinfo().get().execute()
            user_email = user_info.get("email")
        except Exception:
            pass

        from datetime import timezone as tz
        token_expiry = creds.expiry.replace(tzinfo=tz.utc) if creds.expiry else None

        await oauth_repo.upsert_token(
            session,
            owner_id,
            "google",
            access_token=creds.token or "",
            refresh_token=creds.refresh_token,
            token_expiry=token_expiry,
            scopes=" ".join(creds.scopes or []),
            email=user_email,
        )
        await session.commit()

        bot_username = settings.bot_token.split(":")[0] if settings.bot_token else "neurosave_bot"
        return HTMLResponse(_SUCCESS_HTML.format(bot_username="neurosavebot"), status_code=200)

    except Exception as e:
        logger.exception("Google OAuth callback error for owner %d: %s", owner_id, e)
        return HTMLResponse(_ERROR_HTML.format(error=str(e)), status_code=500)


@router.delete("/google", status_code=204)
async def google_disconnect(
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> None:
    from db.repositories import oauth as oauth_repo
    await oauth_repo.delete_token(session, owner_id, "google")
    await session.commit()


_GMAIL_SUCCESS_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Gmail подключён</title>
  <style>
    body {{ font-family: system-ui, sans-serif; display: flex; flex-direction: column;
           align-items: center; justify-content: center; min-height: 100vh;
           margin: 0; background: #f0fdf4; color: #166534; }}
    h1 {{ font-size: 1.5rem; margin-bottom: .5rem; }}
    p {{ color: #15803d; font-size: .95rem; }}
    a {{ display: inline-block; margin-top: 1.5rem; padding: .75rem 1.5rem;
         background: #16a34a; color: #fff; border-radius: 12px;
         text-decoration: none; font-weight: 600; }}
  </style>
</head>
<body>
  <h1>✅ Gmail подключён!</h1>
  <p>Вернитесь в Telegram. Теперь можно отправлять письма голосом или текстом.</p>
  <a href="https://t.me/neurosavebot">Открыть NeuroSave</a>
</body>
</html>"""


def _make_google_flow(redirect_uri: str, scopes: list[str]) -> Any:
    from google_auth_oauthlib.flow import Flow

    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=scopes,
        redirect_uri=redirect_uri,
    )


@router.get("/gmail/auth-url", response_model=AuthUrlOut)
async def gmail_auth_url(
    owner_id: int = Depends(get_owner_id),
) -> AuthUrlOut:
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    redirect_uri = f"{settings.api_base_url}/api/integrations/gmail/callback"
    flow = _make_google_flow(redirect_uri, GMAIL_SCOPES)
    state, _verifier, challenge = _make_state_pkce(owner_id)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
        include_granted_scopes="true",
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    return AuthUrlOut(url=auth_url)


@router.get("/gmail/callback", response_class=HTMLResponse)
async def gmail_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    if error:
        return HTMLResponse(_ERROR_HTML.format(error=error), status_code=400)
    if not code or not state:
        return HTMLResponse(_ERROR_HTML.format(error="Отсутствуют параметры code/state"), status_code=400)

    owner_id, code_verifier = _consume_state(state)
    if owner_id is None:
        return HTMLResponse(_ERROR_HTML.format(error="Неверный или истёкший state-параметр"), status_code=400)

    try:
        from db.repositories import oauth as oauth_repo

        redirect_uri = f"{settings.api_base_url}/api/integrations/gmail/callback"
        flow = _make_google_flow(redirect_uri, GMAIL_SCOPES)
        flow.fetch_token(code=code, code_verifier=code_verifier)
        creds = flow.credentials

        user_email: str | None = None
        try:
            from googleapiclient.discovery import build
            oauth2_service = build("oauth2", "v2", credentials=creds, cache_discovery=False)
            user_info: dict[str, Any] = oauth2_service.userinfo().get().execute()
            user_email = user_info.get("email")
        except Exception:
            pass

        from datetime import timezone as tz
        token_expiry = creds.expiry.replace(tzinfo=tz.utc) if creds.expiry else None

        await oauth_repo.upsert_token(
            session,
            owner_id,
            "gmail",
            access_token=creds.token or "",
            refresh_token=creds.refresh_token,
            token_expiry=token_expiry,
            scopes=" ".join(creds.scopes or []),
            email=user_email,
        )
        await session.commit()
        return HTMLResponse(_GMAIL_SUCCESS_HTML, status_code=200)

    except Exception as e:
        logger.exception("Gmail OAuth callback error for owner %d: %s", owner_id, e)
        return HTMLResponse(_ERROR_HTML.format(error=str(e)), status_code=500)


@router.delete("/gmail", status_code=204)
async def gmail_disconnect(
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> None:
    from db.repositories import oauth as oauth_repo
    await oauth_repo.delete_token(session, owner_id, "gmail")
    await session.commit()


# ── Notion ────────────────────────────────────────────────────────────────────

# ── Google Docs & Sheets ──────────────────────────────────────────────────────

_GDOCS_SUCCESS_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Google Docs подключён</title>
  <style>
    body {{ font-family: system-ui, sans-serif; display: flex; flex-direction: column;
           align-items: center; justify-content: center; min-height: 100vh;
           margin: 0; background: #f0fdf4; color: #166534; }}
    h1 {{ font-size: 1.5rem; margin-bottom: .5rem; }}
    p {{ color: #15803d; font-size: .95rem; }}
    a {{ display: inline-block; margin-top: 1.5rem; padding: .75rem 1.5rem;
         background: #16a34a; color: #fff; border-radius: 12px;
         text-decoration: none; font-weight: 600; }}
  </style>
</head>
<body>
  <h1>✅ Google Docs & Sheets подключён!</h1>
  <p>Вернитесь в Telegram. Теперь можно создавать документы и таблицы прямо из чата.</p>
  <a href="https://t.me/neurosavebot">Открыть NeuroSave</a>
</body>
</html>"""


@router.get("/google-docs/auth-url", response_model=AuthUrlOut)
async def gdocs_auth_url(
    owner_id: int = Depends(get_owner_id),
) -> AuthUrlOut:
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    redirect_uri = f"{settings.api_base_url}/api/integrations/google-docs/callback"
    flow = _make_google_flow(redirect_uri, GDOCS_SCOPES)
    state, _verifier, challenge = _make_state_pkce(owner_id)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    return AuthUrlOut(url=auth_url)


@router.get("/google-docs/callback", response_class=HTMLResponse)
async def gdocs_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    if error:
        return HTMLResponse(_ERROR_HTML.format(error=error), status_code=400)
    if not code or not state:
        return HTMLResponse(_ERROR_HTML.format(error="Отсутствуют параметры code/state"), status_code=400)

    owner_id, code_verifier = _consume_state(state)
    if owner_id is None:
        return HTMLResponse(_ERROR_HTML.format(error="Неверный или истёкший state-параметр"), status_code=400)

    try:
        from db.repositories import oauth as oauth_repo

        redirect_uri = f"{settings.api_base_url}/api/integrations/google-docs/callback"
        flow = _make_google_flow(redirect_uri, GDOCS_SCOPES)
        flow.fetch_token(code=code, code_verifier=code_verifier)
        creds = flow.credentials

        user_email: str | None = None
        try:
            from googleapiclient.discovery import build
            oauth2_service = build("oauth2", "v2", credentials=creds, cache_discovery=False)
            user_info: dict[str, Any] = oauth2_service.userinfo().get().execute()
            user_email = user_info.get("email")
        except Exception:
            pass

        from datetime import timezone as tz
        token_expiry = creds.expiry.replace(tzinfo=tz.utc) if creds.expiry else None

        await oauth_repo.upsert_token(
            session,
            owner_id,
            "google_docs",
            access_token=creds.token or "",
            refresh_token=creds.refresh_token,
            token_expiry=token_expiry,
            scopes=" ".join(creds.scopes or []),
            email=user_email,
        )
        await session.commit()
        return HTMLResponse(_GDOCS_SUCCESS_HTML, status_code=200)

    except Exception as e:
        logger.exception("Google Docs OAuth callback error for owner %d: %s", owner_id, e)
        return HTMLResponse(_ERROR_HTML.format(error=str(e)), status_code=500)


@router.delete("/google-docs", status_code=204)
async def gdocs_disconnect(
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> None:
    from db.repositories import oauth as oauth_repo
    await oauth_repo.delete_token(session, owner_id, "google_docs")
    await session.commit()


class DriveFileOut(BaseModel):
    id: str
    name: str
    url: str
    type: str
    modified_time: str


@router.get("/google-docs/files", response_model=list[DriveFileOut])
async def gdocs_files(
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> list[DriveFileOut]:
    from services import google_docs as docs_svc
    from db.repositories import integration_configs as cfg_repo

    creds = await docs_svc.get_gdocs_credentials(owner_id, session)
    if not creds:
        raise HTTPException(status_code=400, detail="Google Docs not connected")

    folder_id = await cfg_repo.get_config(session, owner_id, docs_svc.GDOCS_DRIVE_FOLDER_KEY)
    if not folder_id:
        return []

    files = await docs_svc.list_drive_files(creds, folder_id)
    return [DriveFileOut(**f) for f in files]


class CreateDocIn(BaseModel):
    name: str
    type: str = "doc"


@router.post("/google-docs/create", response_model=dict)
async def gdocs_create(
    body: CreateDocIn,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    from services import google_docs as docs_svc, google_sheets as sheets_svc

    creds = await docs_svc.get_gdocs_credentials(owner_id, session)
    if not creds:
        raise HTTPException(status_code=400, detail="Google Docs not connected")

    if body.type == "sheet":
        folder_id = await docs_svc.ensure_drive_folder(creds, owner_id, session)
        file_id, url = await sheets_svc.create_spreadsheet(creds, folder_id, body.name)
        from db.repositories import integration_configs as cfg_repo
        from services.google_sheets import _sheet_slug
        await cfg_repo.set_config(session, owner_id, f"gdocs_sheet:{_sheet_slug(body.name)}", file_id)
    else:
        file_id, url = await docs_svc.find_or_create_doc(creds, owner_id, body.name, "", session)

    await session.commit()
    return {"id": file_id, "url": url}


# ── Google Calendar events ────────────────────────────────────────────────────

class CalendarEventOut(BaseModel):
    id: str
    title: str
    start: str
    end: str | None = None
    url: str | None = None


@router.get("/google-calendar/events", response_model=list[CalendarEventOut])
async def calendar_events(
    days: int = Query(default=7, ge=1, le=30),
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> list[CalendarEventOut]:
    from services import google_calendar as cal_svc

    service = await cal_svc.get_calendar_service(owner_id, session)
    if not service:
        raise HTTPException(status_code=400, detail="Google Calendar not connected")

    items = await cal_svc.list_upcoming_events(service, days)
    result: list[CalendarEventOut] = []
    for item in items:
        start_val = item.get("start", {})
        end_val = item.get("end", {})
        start_str: str = start_val.get("dateTime") or start_val.get("date") or ""
        end_str: str | None = end_val.get("dateTime") or end_val.get("date") or None
        result.append(CalendarEventOut(
            id=str(item.get("id", "")),
            title=str(item.get("summary", "Без названия")),
            start=start_str,
            end=end_str,
            url=item.get("htmlLink"),
        ))
    return result


# ── Gmail threads ─────────────────────────────────────────────────────────────

class GmailThreadOut(BaseModel):
    id: str
    subject: str
    from_: str
    snippet: str
    date: str
    is_reply: bool


@router.get("/gmail/threads", response_model=list[GmailThreadOut])
async def gmail_threads(
    limit: int = Query(default=20, ge=1, le=50),
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> list[GmailThreadOut]:
    from services import gmail as gmail_svc

    service = await gmail_svc.get_gmail_service(owner_id, session)
    if not service:
        raise HTTPException(status_code=400, detail="Gmail not connected")

    items = await gmail_svc.list_threads(service, max_results=limit)
    return [GmailThreadOut(
        id=m["id"],
        subject=m["subject"],
        from_=m["from_"],
        snippet=m["snippet"],
        date=m["date"],
        is_reply=m["is_reply"],
    ) for m in items]


# ── Gmail full message + send ─────────────────────────────────────────────────

class GmailAttachmentOut(BaseModel):
    filename: str
    attachment_id: str
    mime_type: str
    size: str


class GmailMessageOut(BaseModel):
    id: str
    thread_id: str
    subject: str
    from_: str
    to: str
    date: str
    body: str
    snippet: str
    attachments: list[GmailAttachmentOut]
    is_reply: bool
    message_id_header: str


@router.get("/gmail/messages/{message_id}", response_model=GmailMessageOut)
async def gmail_message(
    message_id: str,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> GmailMessageOut:
    from services import gmail as gmail_svc

    service = await gmail_svc.get_gmail_service(owner_id, session)
    if not service:
        raise HTTPException(status_code=400, detail="Gmail not connected")

    msg = await gmail_svc.get_message_full(service, message_id)
    return GmailMessageOut(
        id=msg["id"],
        thread_id=msg["thread_id"],
        subject=msg["subject"],
        from_=msg["from_"],
        to=msg["to"],
        date=msg["date"],
        body=msg["body"],
        snippet=msg["snippet"],
        attachments=[GmailAttachmentOut(**a) for a in msg["attachments"]],
        is_reply=msg["is_reply"],
        message_id_header=msg["message_id_header"],
    )


class GmailSendIn(BaseModel):
    to: str
    subject: str
    body: str
    thread_id: str | None = None
    in_reply_to: str | None = None


@router.post("/gmail/send", response_model=dict[str, str])
async def gmail_send(
    body: GmailSendIn,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    from services import gmail as gmail_svc

    service = await gmail_svc.get_gmail_service(owner_id, session)
    if not service:
        raise HTTPException(status_code=400, detail="Gmail not connected")

    msg_id = await gmail_svc.send_reply(
        service,
        to=[body.to],
        subject=body.subject,
        body=body.body,
        thread_id=body.thread_id,
        in_reply_to=body.in_reply_to,
    )
    return {"id": msg_id}


# ── OAuth redirect URIs ────────────────────────────────────────────────────────

@router.get("/redirect-uris")
async def redirect_uris() -> dict[str, str | list[str]]:
    """Return OAuth redirect URIs that must be registered in Google Cloud Console."""
    base = settings.api_base_url.rstrip("/")
    uris = [
        f"{base}/api/integrations/google/callback",
        f"{base}/api/integrations/gmail/callback",
        f"{base}/api/integrations/google-docs/callback",
    ]
    return {"base_url": base, "redirect_uris": uris}
