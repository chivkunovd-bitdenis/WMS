"""FastAPI application entrypoint for WB Marketplace API emulator."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import APIRouter, FastAPI

from wb_emulator.auth import AuthMiddleware
from wb_emulator.db import init_db
from wb_emulator.routes.admin import admin_router, orders_read_router

# Routers for later lanes (EMU-030+).
supplies_router = APIRouter(tags=["supplies"])
media_meta_router = APIRouter(tags=["media-meta"])
warehouses_router = APIRouter(tags=["warehouses"])


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

    app.include_router(orders_read_router, prefix="/api/v3/orders")
    app.include_router(supplies_router, prefix="/api/v3/supplies")
    app.include_router(media_meta_router, prefix="/api/v3")
    app.include_router(warehouses_router, prefix="/api/v3")
    app.include_router(admin_router)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
