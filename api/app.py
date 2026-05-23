from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from api.auth import get_owner_id
from api.routers import bot, contacts, ghost, integrations, reminders, settings, tasks
from config import settings as app_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="NeuroSave API", version="1.0.0", lifespan=lifespan)

    # In dev bypass mode allow any origin — the dev is running locally anyway.
    if app_settings.api_dev_bypass:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )
    else:
        origins = [app_settings.miniapp_url, "http://localhost:3000"]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    app.include_router(bot.router, prefix="/api/bot", tags=["bot"])
    app.include_router(integrations.router, prefix="/api/integrations", tags=["integrations"])
    app.include_router(reminders.router, prefix="/api/reminders", tags=["reminders"])
    app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
    app.include_router(ghost.router, prefix="/api/ghost", tags=["ghost"])
    app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
    app.include_router(contacts.router, prefix="/api/contacts", tags=["contacts"])

    @app.get("/api/me")
    async def me(user_id: int = Depends(get_owner_id)) -> dict[str, int]:
        return {"user_id": user_id}

    @app.get("/api/debug-auth")
    async def debug_auth(request: Request) -> dict[str, str]:
        auth = request.headers.get("Authorization", "MISSING")
        return {"authorization": auth, "starts_with_tma": str(auth.startswith("tma "))}

    return app
