from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.auth import router as auth_router
from app.api.background_jobs import router as background_jobs_router
from app.api.discrepancy_acts import router as discrepancy_acts_router
from app.api.health import router as health_router
from app.api.inbound_intake import router as inbound_intake_router
from app.api.inventory_balances import router as inventory_balances_router
from app.api.inventory_movements import router as inventory_movements_router
from app.api.marketplace_unload_requests import router as marketplace_unload_requests_router
from app.api.outbound_shipment import router as outbound_shipment_router
from app.api.products import router as products_router
from app.api.sellers import router as sellers_router
from app.api.stock_transfer import router as stock_transfer_router
from app.api.warehouses import router as warehouses_router
from app.api.wb_mp_warehouses import router as wb_mp_warehouses_router
from app.api.wildberries_integration import router as wildberries_integration_router
from app.core.roles import FULFILLMENT_ADMIN
from app.db.session import SessionLocal, engine
from app.models import Base
from app.models.tenant import Tenant
from app.models.user import User
from app.services.passwords import hash_password

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _ = app
    if os.environ.get("WMS_AUTO_CREATE_SCHEMA") == "1":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.warning("WMS_AUTO_CREATE_SCHEMA=1: tables created (dev/e2e only).")

    if os.environ.get("WMS_BOOTSTRAP_ADMIN") == "1":
        email = os.environ.get("WMS_BOOTSTRAP_ADMIN_EMAIL", "admin@test.local").strip().lower()
        password = os.environ.get("WMS_BOOTSTRAP_ADMIN_PASSWORD", "password123").strip()
        org = os.environ.get("WMS_BOOTSTRAP_ORG_NAME", "WMS Test").strip()
        slug = os.environ.get("WMS_BOOTSTRAP_ORG_SLUG", "wms-test").strip().lower()

        async with SessionLocal() as session:
            tenant_res = await session.execute(select(Tenant).where(Tenant.slug == slug))
            tenant = tenant_res.scalar_one_or_none()
            if tenant is None:
                tenant = Tenant(name=org, slug=slug)
                session.add(tenant)
                await session.commit()
                await session.refresh(tenant)

            user_res = await session.execute(select(User).where(User.email == email))
            user = user_res.scalar_one_or_none()
            if user is None:
                user = User(
                    tenant_id=tenant.id,
                    email=email,
                    password_hash=hash_password(password),
                    must_set_password=False,
                    role=FULFILLMENT_ADMIN,
                    seller_id=None,
                )
                session.add(user)
                await session.commit()
                logger.warning("Bootstrapped test admin user: %s", email)
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
    app.include_router(sellers_router)
    app.include_router(warehouses_router)
    app.include_router(products_router)
    app.include_router(inbound_intake_router)
    app.include_router(inventory_balances_router)
    app.include_router(inventory_movements_router)
    app.include_router(stock_transfer_router)
    app.include_router(outbound_shipment_router)
    app.include_router(marketplace_unload_requests_router)
    app.include_router(wb_mp_warehouses_router)
    app.include_router(discrepancy_acts_router)
    app.include_router(background_jobs_router)
    app.include_router(wildberries_integration_router)
    return app


app = create_app()
