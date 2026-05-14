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


@beartype
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
