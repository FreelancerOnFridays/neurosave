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


class IntegrationStatus(BaseModel):
    provider: str
    connected: bool
    email: str | None = None
    scopes: list[str] = []


class IntegrationsStatusOut(BaseModel):
    google_calendar: IntegrationStatus
    gmail: IntegrationStatus


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
    return IntegrationsStatusOut(google_calendar=google_status, gmail=gmail_status)


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
