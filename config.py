from __future__ import annotations

from beartype import beartype
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bot_token: str
    openai_api_key: str

    database_url: str
    redis_url: str

    owner_chat_id: int
    owner_timezone: str = "Europe/Moscow"
    api_port: int = 8000
    miniapp_url: str = "http://localhost:3000"
    api_dev_bypass: bool = False

    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None

    google_client_id: str | None = None
    google_client_secret: str | None = None
    api_base_url: str = "http://localhost:8000"

    notion_client_id: str | None = None
    notion_client_secret: str | None = None


@beartype
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
