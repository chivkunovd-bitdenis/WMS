"""FastAPI application entrypoint for WB Marketplace API emulator."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from wb_emulator.auth import AuthMiddleware
from wb_emulator.db import init_db
from wb_emulator.routes.admin import admin_router
from wb_emulator.routes.orders import router as orders_router
from wb_emulator.routes import supplies as supplies_routes
from wb_emulator.routes.media_meta import router as media_meta_router
from wb_emulator.routes.warehouses import router as warehouses_router
from wb_emulator.services import supplies_store  # noqa: F401 — register ORM tables

supplies_router = supplies_routes.router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="WB Marketplace API Emulator",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(AuthMiddleware)

    app.include_router(orders_router, prefix="/api/v3/orders")
    app.include_router(supplies_router, prefix="/api/v3/supplies")
    app.include_router(media_meta_router, prefix="/api/v3")
    app.include_router(warehouses_router, prefix="/api/v3")
    app.include_router(admin_router)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
