from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl, unquote

from beartype import beartype
from fastapi import HTTPException, Request

from config import settings


@beartype
def _validate_raw(raw: str) -> dict[str, str]:
    params = dict(parse_qsl(unquote(raw), keep_blank_values=True))
    provided_hash = params.pop("hash", "")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, provided_hash):
        raise HTTPException(status_code=401, detail="Invalid Telegram signature")
    auth_date = int(params.get("auth_date", "0"))
    if abs(time.time() - auth_date) > 3600:
        raise HTTPException(status_code=401, detail="initData expired")
    return params


async def get_owner_id(request: Request) -> int:
    # Dev bypass: set API_DEV_BYPASS=true in .env to skip Telegram auth during local development
    if settings.api_dev_bypass:
        return settings.owner_chat_id

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("tma "):
        raise HTTPException(status_code=401, detail="Missing Telegram auth")
    params = _validate_raw(auth_header[4:])
    user_data = json.loads(params.get("user", "{}"))
    user_id = int(user_data.get("id", 0))
    if user_id != settings.owner_chat_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return user_id
