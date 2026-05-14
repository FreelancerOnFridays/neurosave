from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import ghost, reminders, settings, tasks
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

    app.include_router(reminders.router, prefix="/api/reminders", tags=["reminders"])
    app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
    app.include_router(ghost.router, prefix="/api/ghost", tags=["ghost"])
    app.include_router(settings.router, prefix="/api/settings", tags=["settings"])

    return app
