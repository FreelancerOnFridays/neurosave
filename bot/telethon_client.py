from __future__ import annotations

import logging

from telethon import TelegramClient
from telethon.errors import (
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession

from config import settings

logger = logging.getLogger(__name__)

# Per-user client pool (user_id → TelegramClient)
_clients: dict[int, TelegramClient] = {}

# Per-user auth state machine
# "awaiting_phone" | "awaiting_code:{phone}:{phone_code_hash}" | "awaiting_password"
_pending_auth: dict[int, str] = {}


def is_configured() -> bool:
    return settings.telegram_api_id is not None and settings.telegram_api_hash is not None


async def _make_client(session_str: str) -> TelegramClient:
    api_id: int = settings.telegram_api_id  # type: ignore[assignment]
    api_hash: str = settings.telegram_api_hash  # type: ignore[assignment]
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.connect()
    return client


async def get_client(user_id: int, session_str: str | None = None) -> TelegramClient | None:
    """Return connected Telethon client for user_id, creating it if needed."""
    if not is_configured():
        return None
    if user_id not in _clients:
        _clients[user_id] = await _make_client(session_str or "")
    else:
        client = _clients[user_id]
        if not client.is_connected():
            await client.connect()
    return _clients[user_id]


async def is_authorized(user_id: int, session_str: str | None = None) -> bool:
    client = await get_client(user_id, session_str)
    if client is None:
        return False
    return await client.is_user_authorized()


def is_awaiting_auth(user_id: int) -> bool:
    return user_id in _pending_auth


async def start_auth(user_id: int) -> str:
    """Begin auth flow with a fresh empty-session client. Returns prompt to send to user."""
    if not is_configured():
        return (
            "❌ Telethon не настроен. Добавьте TELEGRAM_API_ID и TELEGRAM_API_HASH в .env\n"
            "Получите их на https://my.telegram.org"
        )
    old = _clients.pop(user_id, None)
    if old and old.is_connected():
        try:
            await old.disconnect()
        except Exception:
            pass
    _clients[user_id] = await _make_client("")
    _pending_auth[user_id] = "awaiting_phone"
    return "📱 Введите ваш номер телефона в формате +79001234567:"


async def handle_auth_input(user_id: int, text: str) -> tuple[str, str | None]:
    """Process one step of the auth flow.

    Returns (reply_text, session_str_or_None).
    session_str is set only when auth completes — caller must save it to DB.
    """
    state = _pending_auth.get(user_id, "")

    # ── Step 1: phone number ─────────────────────────────────────────────────
    if state == "awaiting_phone":
        phone = text.strip()
        client = _clients.get(user_id)
        if client is None:
            _pending_auth.pop(user_id, None)
            return ("❌ Сессия потеряна. Отправьте /sync_contacts снова.", None)
        try:
            sent = await client.send_code_request(phone)
            _pending_auth[user_id] = f"awaiting_code:{phone}"
            # Tell the user WHERE Telegram sent the code
            code_type = type(sent.type).__name__
            if "App" in code_type:
                hint = (
                    "📲 Код отправлен в ваш Telegram.\n"
                    "Откройте Telegram на любом устройстве — там будет сообщение от Telegram "
                    "с 5-значным кодом.\n"
                    "⚠️ Не нажимайте кнопку «Войти» в уведомлении — просто скопируйте цифры кода."
                )
            else:
                hint = "📱 Код отправлен по SMS на ваш номер."
            return (f"{hint}\n\nВведите только цифры кода:", None)
        except Exception as e:
            _pending_auth.pop(user_id, None)
            logger.exception("send_code_request failed for user %d", user_id)
            return (f"❌ Ошибка запроса кода: {type(e).__name__}: {e}\nПопробуйте /sync_contacts снова.", None)

    # ── Step 2: verification code ────────────────────────────────────────────
    if state.startswith("awaiting_code:"):
        phone = state[len("awaiting_code:"):]
        # Extract only digits — works even if user pastes the full "Login code: 12345" message
        code = "".join(c for c in text if c.isdigit())
        if not code:
            return ("❌ Введите только цифры кода (например: 12345):", None)
        client = _clients.get(user_id)
        if client is None:
            _pending_auth.pop(user_id, None)
            return ("❌ Сессия потеряна. Отправьте /sync_contacts снова.", None)
        try:
            await client.sign_in(phone, code)
            session_str = client.session.save()
            _pending_auth.pop(user_id, None)
            return ("✅ Авторизация успешна! Отправьте /sync_contacts чтобы синхронизировать контакты.", session_str)
        except PhoneCodeExpiredError:
            # Resend automatically instead of aborting
            try:
                sent = await client.send_code_request(phone)
                code_type = type(sent.type).__name__
                if "App" in code_type:
                    hint = "Проверьте Telegram-приложение (⚠️ не нажимайте кнопку «Войти», только скопируйте цифры)."
                else:
                    hint = "Проверьте SMS."
                return (
                    f"⏱ Код устарел — автоматически запросили новый.\n{hint}\n\nВведите новый код:",
                    None,
                )
            except Exception as resend_err:
                _pending_auth.pop(user_id, None)
                return (f"❌ Код устарел и не удалось запросить новый: {resend_err}\nОтправьте /sync_contacts снова.", None)
        except PhoneCodeInvalidError:
            return ("❌ Неверный код. Введите только 5 цифр из сообщения Telegram:", None)
        except SessionPasswordNeededError:
            _pending_auth[user_id] = "awaiting_password"
            return ("🔑 На аккаунте включена двухфакторная аутентификация.\nВведите пароль 2FA (облачный пароль):", None)
        except Exception as e:
            _pending_auth.pop(user_id, None)
            logger.exception("sign_in failed for user %d", user_id)
            return (
                f"❌ Ошибка входа: {type(e).__name__}: {e}\n"
                "Отправьте /sync_contacts снова.",
                None,
            )

    # ── Step 3: 2FA password ─────────────────────────────────────────────────
    if state == "awaiting_password":
        password = text.strip()
        client = _clients.get(user_id)
        if client is None:
            _pending_auth.pop(user_id, None)
            return ("❌ Сессия потеряна. Отправьте /sync_contacts снова.", None)
        try:
            await client.sign_in(password=password)
            session_str = client.session.save()
            _pending_auth.pop(user_id, None)
            return ("✅ Авторизация успешна! Отправьте /sync_contacts чтобы синхронизировать контакты.", session_str)
        except PasswordHashInvalidError:
            # Wrong password — keep state so user can retry without restarting
            return ("❌ Неверный пароль. Попробуйте ещё раз:", None)
        except Exception as e:
            _pending_auth.pop(user_id, None)
            logger.exception("2FA sign_in failed for user %d", user_id)
            return (
                f"❌ Ошибка при входе: {type(e).__name__}: {e}\n"
                "Отправьте /sync_contacts снова.",
                None,
            )

    _pending_auth.pop(user_id, None)
    return ("❌ Неизвестное состояние. Попробуйте /sync_contacts снова.", None)


async def reset_session(user_id: int) -> None:
    """Disconnect and remove client for user — forces full re-auth on next /sync_contacts."""
    client = _clients.pop(user_id, None)
    if client and client.is_connected():
        try:
            await client.disconnect()
        except Exception:
            pass
    _pending_auth.pop(user_id, None)


async def disconnect_all() -> None:
    for client in _clients.values():
        if client.is_connected():
            try:
                await client.disconnect()
            except Exception:
                pass
    _clients.clear()
    _pending_auth.clear()
