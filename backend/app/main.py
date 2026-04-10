from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.inbound_intake import router as inbound_intake_router
from app.api.products import router as products_router
from app.api.warehouses import router as warehouses_router
from app.db.session import engine
from app.models import Base

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _ = app
    if os.environ.get("WMS_AUTO_CREATE_SCHEMA") == "1":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.warning("WMS_AUTO_CREATE_SCHEMA=1: tables created (dev/e2e only).")
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="WMS API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:15173",
            "http://127.0.0.1:15173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(warehouses_router)
    app.include_router(products_router)
    app.include_router(inbound_intake_router)
    return app


app = create_app()
