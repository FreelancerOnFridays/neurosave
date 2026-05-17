from __future__ import annotations

import logging
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

# In-memory state store: state_token → (owner_id, expires_at)
_oauth_states: dict[str, tuple[int, float]] = {}

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
    notion: IntegrationStatus
    google_docs: IntegrationStatus


class AuthUrlOut(BaseModel):
    url: str


def _gc_states() -> None:
    now = time.time()
    expired = [k for k, (_, exp) in _oauth_states.items() if exp < now]
    for k in expired:
        del _oauth_states[k]


def _make_state(owner_id: int) -> str:
    _gc_states()
    token = secrets.token_urlsafe(32)
    _oauth_states[token] = (owner_id, time.time() + 600)
    return token


def _consume_state(state: str) -> int | None:
    _gc_states()
    entry = _oauth_states.pop(state, None)
    if entry is None:
        return None
    owner_id, expires_at = entry
    if time.time() > expires_at:
        return None
    return owner_id


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
    notion_row = await oauth_repo.get_token(session, owner_id, "notion")
    notion_status = IntegrationStatus(
        provider="notion",
        connected=notion_row is not None,
        email=notion_row.email if notion_row else None,
        scopes=[],
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
        notion=notion_status,
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
    state = _make_state(owner_id)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
        include_granted_scopes="true",
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

    owner_id = _consume_state(state)
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
        import os
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
        flow.fetch_token(code=code)
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
    state = _make_state(owner_id)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
        include_granted_scopes="true",
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

    owner_id = _consume_state(state)
    if owner_id is None:
        return HTMLResponse(_ERROR_HTML.format(error="Неверный или истёкший state-параметр"), status_code=400)

    try:
        import os
        from db.repositories import oauth as oauth_repo

        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
        redirect_uri = f"{settings.api_base_url}/api/integrations/gmail/callback"
        flow = _make_google_flow(redirect_uri, GMAIL_SCOPES)
        flow.fetch_token(code=code)
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

_NOTION_SUCCESS_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Notion подключён</title>
  <style>
    body {{ font-family: system-ui, sans-serif; display: flex; flex-direction: column;
           align-items: center; justify-content: center; min-height: 100vh;
           margin: 0; background: #f0fdf4; color: #166534; }}
    h1 {{ font-size: 1.5rem; margin-bottom: .5rem; }}
    p {{ color: #15803d; font-size: .95rem; max-width: 360px; text-align: center; }}
    a {{ display: inline-block; margin-top: 1.5rem; padding: .75rem 1.5rem;
         background: #16a34a; color: #fff; border-radius: 12px;
         text-decoration: none; font-weight: 600; }}
  </style>
</head>
<body>
  <h1>✅ Notion подключён!</h1>
  <p>Вернитесь в Telegram. Отправьте боту ID базы Notion командой: /notion_db <ID></p>
  <a href="https://t.me/neurosavebot">Открыть NeuroSave</a>
</body>
</html>"""


@router.get("/notion/auth-url", response_model=AuthUrlOut)
async def notion_auth_url(
    owner_id: int = Depends(get_owner_id),
) -> AuthUrlOut:
    if not settings.notion_client_id:
        raise HTTPException(status_code=503, detail="Notion OAuth not configured")

    state = _make_state(owner_id)
    redirect_uri = f"{settings.api_base_url}/api/integrations/notion/callback"
    url = (
        f"https://api.notion.com/v1/oauth/authorize"
        f"?client_id={settings.notion_client_id}"
        f"&response_type=code"
        f"&owner=user"
        f"&redirect_uri={redirect_uri}"
        f"&state={state}"
    )
    return AuthUrlOut(url=url)


@router.get("/notion/callback", response_class=HTMLResponse)
async def notion_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    if error:
        return HTMLResponse(_ERROR_HTML.format(error=error), status_code=400)
    if not code or not state:
        return HTMLResponse(_ERROR_HTML.format(error="Отсутствуют параметры code/state"), status_code=400)

    owner_id = _consume_state(state)
    if owner_id is None:
        return HTMLResponse(_ERROR_HTML.format(error="Неверный или истёкший state-параметр"), status_code=400)

    try:
        import base64
        import httpx
        from db.repositories import oauth as oauth_repo

        redirect_uri = f"{settings.api_base_url}/api/integrations/notion/callback"
        credentials = base64.b64encode(
            f"{settings.notion_client_id}:{settings.notion_client_secret}".encode()
        ).decode()

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.notion.com/v1/oauth/token",
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/json",
                    "Notion-Version": "2022-06-28",
                },
                json={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()

        access_token: str = data["access_token"]
        workspace_name: str = data.get("workspace_name", "")

        await oauth_repo.upsert_token(
            session,
            owner_id,
            "notion",
            access_token=access_token,
            email=workspace_name or None,
        )
        await session.commit()
        return HTMLResponse(_NOTION_SUCCESS_HTML, status_code=200)

    except Exception as e:
        logger.exception("Notion OAuth callback error for owner %d: %s", owner_id, e)
        return HTMLResponse(_ERROR_HTML.format(error=str(e)), status_code=500)


@router.delete("/notion", status_code=204)
async def notion_disconnect(
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> None:
    from db.repositories import oauth as oauth_repo
    from db.repositories import integration_configs as cfg_repo

    await oauth_repo.delete_token(session, owner_id, "notion")
    for key in ["notion_root_page_id", "notion_section_capture", "notion_section_task", "notion_section_meeting_notes"]:
        await cfg_repo.delete_config(session, owner_id, key)
    await session.commit()


class NotionCaptureIn(BaseModel):
    title: str
    content: str = ""
    section: str = "capture"


class NotionCaptureOut(BaseModel):
    page_id: str
    url: str


@router.post("/notion/capture", response_model=NotionCaptureOut)
async def notion_capture(
    body: NotionCaptureIn,
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> NotionCaptureOut:
    from services import notion as notion_svc

    token = await notion_svc.get_notion_token(owner_id, session)
    if not token:
        raise HTTPException(status_code=400, detail="Notion not connected")

    section = body.section if body.section in ("capture", "task", "meeting_notes") else "capture"
    section_id = await notion_svc.ensure_section_page(token, owner_id, section, session)
    await session.commit()

    page_id, url = await notion_svc.create_page(token, section_id, body.title, body.content)
    return NotionCaptureOut(page_id=page_id, url=url)


class NotionPageOut(BaseModel):
    id: str
    title: str
    url: str
    section: str
    created_time: str


@router.get("/notion/pages", response_model=list[NotionPageOut])
async def notion_pages(
    owner_id: int = Depends(get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> list[NotionPageOut]:
    from services import notion as notion_svc

    token = await notion_svc.get_notion_token(owner_id, session)
    if not token:
        raise HTTPException(status_code=400, detail="Notion not connected")

    pages = await notion_svc.list_all_recent_pages(token, owner_id, session)
    return [NotionPageOut(**p) for p in pages]


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
    state = _make_state(owner_id)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
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

    owner_id = _consume_state(state)
    if owner_id is None:
        return HTMLResponse(_ERROR_HTML.format(error="Неверный или истёкший state-параметр"), status_code=400)

    try:
        import os
        from db.repositories import oauth as oauth_repo

        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
        redirect_uri = f"{settings.api_base_url}/api/integrations/google-docs/callback"
        flow = _make_google_flow(redirect_uri, GDOCS_SCOPES)
        flow.fetch_token(code=code)
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
