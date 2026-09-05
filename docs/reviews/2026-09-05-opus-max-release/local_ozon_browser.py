"""WMS-375: isolated, synthetic Ozon browser scenario; never a default app runtime.

Run from the canonical checkout:
  backend/.venv/bin/python docs/reviews/2026-09-05-opus-max-release/local_ozon_browser.py

Creates its own ignored SQLite DB on first start; reuse preserves browser evidence.
API: http://127.0.0.1:18081. Read-only evidence: /__local_ozon_evidence.
Login: ozon-browser@example.com / LocalOzon375!
To replay, stop this process and remove ONLY backend/live-wms375-ozon-browser.db
and output/wms375-ozon-browser (both contain synthetic data only), then restart.
Two positions (2 and 1 units), two boxes; physical stock is 2 and 0. Request box
QR, inspect the two-page PDF, then confirm the negative-stock delivery warning.
Expected: one ship, one carriage/create, one approve; balances 0 and -1.
Uses existing pytest fixture functions, but does not run pytest or its conftest.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "output/wms375-ozon-browser"
DATA.mkdir(parents=True, exist_ok=True)
# Do not load the checkout's .env or inherit integration credentials.
os.environ.clear()
os.environ.update(
    {
        "PATH": "/usr/bin:/bin",
        "APP_ENV": "development",
        "DATABASE_URL": f"sqlite+aiosqlite:///{ROOT}/backend/live-wms375-ozon-browser.db",
        "JWT_SECRET_KEY": "synthetic-local-ozon-browser-only-375",
        "WMS_DATA_DIR": str(DATA / "assets"),
        "WMS_OZON_LIVE_API": "false",
        "WMS_CORS_ORIGINS": "http://127.0.0.1:15176,http://localhost:15176",
    }
)
os.chdir(DATA)
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "backend/tests")]

import fitz
import httpx
from app.services import ozon_provider_factory as factory
from app.services.marketplace_provider import (
    FakeMarketplaceTransport,
    OzonMarketplaceProvider,
)
from sqlalchemy import select


def pdf(text: str) -> str:
    with fitz.open() as doc:
        doc.new_page(width=300, height=160).insert_text((20, 40), text)
        return base64.b64encode(doc.tobytes()).decode("ascii")


class BrowserTransport(FakeMarketplaceTransport):
    def __init__(self):
        super().__init__()
        self.state_path = DATA / "provider-state.json"
        self.state = (
            json.loads(self.state_path.read_text())
            if self.state_path.exists()
            else {
                "shipped": False,
                "approved": False,
                "calls": [],
            }
        )
        self.children = ["LOCAL-OZON-375-1", "LOCAL-OZON-375-2"]

    def record(self, path, payload):
        self.state["calls"].append({"path": path, "payload": dict(payload)})
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2))

    async def call(self, *, client_id, api_key, path, payload):
        from test_fbs_ozon_lane import _ozon_handoff_responses

        self.record(path, payload)
        if path == "/v3/posting/fbs/get":
            return {
                "result": {
                    "posting_number": payload.get("posting_number"),
                    "status": "awaiting_deliver"
                    if self.state["shipped"]
                    else "awaiting_packaging",
                    "substatus": "posting_in_carriage"
                    if self.state["approved"]
                    else "",
                    "related_postings": {
                        "related_posting_numbers": self.children
                        if self.state["shipped"]
                        else []
                    },
                }
            }
        if path == "/v4/posting/fbs/ship":
            self.state["shipped"] = True
            self.state_path.write_text(json.dumps(self.state, indent=2))
            return {"result": self.children}
        if path == "/v1/carriage/get":
            return {
                "carriage_id": 901,
                "status": "sended" if self.state["approved"] else "new",
            }
        if path == "/v1/carriage/approve":
            self.state["approved"] = True
            self.state_path.write_text(json.dumps(self.state, indent=2))
            return {}
        if path == "/v2/posting/fbs/act/get-pdf":
            return {
                "file_content": pdf("LOCAL ONLY - Ozon shipping list 901"),
                "file_name": "local-shipping-list.pdf",
                "content_type": "application/pdf",
            }
        responses = _ozon_handoff_responses()
        if path not in responses:
            raise RuntimeError(f"Local fake has no response for {path}")
        return responses[path]

    async def fetch_order_labels(self, *, client_id, api_key, posting_numbers):
        self.record("fetch_order_labels", {"posting_numbers": list(posting_numbers)})
        return [
            {
                "posting_number": number,
                "content_type": "application/pdf",
                "file": pdf(number),
            }
            for number in posting_numbers
        ]


transport = BrowserTransport()
factory.build_ozon_transport = lambda **kwargs: transport
factory.build_ozon_provider = lambda **kwargs: OzonMarketplaceProvider(
    transport=transport
)
# The application gate is open only in this isolated process; transport is always fake.
factory.ozon_live_api_enabled = lambda: True


async def reject_http(*args, **kwargs):
    raise RuntimeError("Outbound HTTP is disabled in the synthetic browser runtime")


def reject_sync_http(*args, **kwargs):
    raise RuntimeError("Outbound HTTP is disabled in the synthetic browser runtime")


httpx.AsyncClient.send = reject_http
httpx.Client.send = reject_sync_http

from app.core.roles import FULFILLMENT_ADMIN
from app.db.session import SessionLocal, engine
from app.main import create_app
from app.models import Base
from app.models.fbs_order import FbsOrderProduct
from app.models.fbs_supply import FbsSupply
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.user import User
from app.services.passwords import hash_password
from test_fbs_ozon_lane import (
    _seed_ozon_supply_case,
    _seed_physical_ozon_packaging,
)
from test_ozon_box_assembly import seed_boxes


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        if await session.scalar(
            select(User).where(User.email == "ozon-browser@example.com")
        ):
            return
        (
            tenant,
            seller,
            _warehouse,
            product,
            order,
            supply,
        ) = await _seed_ozon_supply_case(session, packed=True)
        assert supply is not None
        tenant.name = "Локальный тест Ozon WMS-375"
        seller.name = "Тестовый селлер Ozon — синтетические данные"
        supply.name = "Ozon: 2 позиции, нехватка 1 шт."
        # Normal Ozon create_supply_from_orders keeps this legacy local placeholder.
        supply.wb_supply_id = f"PENDING-LOCAL-{supply.id}"
        product.name = "Тест Ozon: в наличии 2 шт."
        second = Product(
            tenant_id=tenant.id,
            seller_id=seller.id,
            name="Тест Ozon: нехватка 1 шт.",
            sku_code="LOCAL-OZON-SHORTAGE",
        )
        session.add(second)
        await session.flush()
        order.meta_details_json = {"ozon_requirements": {"kinds": []}}
        for index, (item, quantity) in enumerate([(product, 2), (second, 1)]):
            session.add(
                FbsOrderProduct(
                    order_id=order.id,
                    product_id=item.id,
                    position_index=index,
                    ozon_sku=3001 + index,
                    quantity=quantity,
                    offer_id=item.sku_code,
                    name=item.name,
                )
            )
        session.add(
            User(
                tenant_id=tenant.id,
                email="ozon-browser@example.com",
                password_hash=hash_password("LocalOzon375!"),
                role=FULFILLMENT_ADMIN,
            )
        )
        await session.commit()
        boxes = await seed_boxes(session, order, supply)
        await _seed_physical_ozon_packaging(
            session, order, supply, [(product, 2), (second, 1)]
        )
        balance = await session.scalar(
            select(InventoryBalance).where(InventoryBalance.product_id == second.id)
        )
        balance.quantity = balance.quantity_unpacked = balance.quantity_packed = 0
        await session.commit()
        manifest = {
            "supply_id": str(supply.id),
            "tenant_id": str(tenant.id),
            "order_id": str(order.id),
            "box_ids": [str(b.id) for b in boxes],
            "product_ids": [str(product.id), str(second.id)],
            "api": "http://127.0.0.1:18081",
            "login": "ozon-browser@example.com",
        }
        (DATA / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2)
        )


app = create_app()


@app.get("/__local_ozon_evidence")
async def evidence():
    async with SessionLocal() as session:
        return {
            "manifest": json.loads((DATA / "manifest.json").read_text()),
            "provider": transport.state,
            "supplies": [
                {
                    "id": str(s.id),
                    "status": s.status,
                    "external_supply_id": s.external_supply_id,
                }
                for s in await session.scalars(select(FbsSupply))
            ],
            "balances": [
                {
                    "product_id": str(b.product_id),
                    "quantity": b.quantity,
                    "quantity_packed": b.quantity_packed,
                    "quantity_unpacked": b.quantity_unpacked,
                }
                for b in await session.scalars(select(InventoryBalance))
            ],
            "movements": [
                {
                    "id": str(m.id),
                    "product_id": str(m.product_id),
                    "quantity_delta": m.quantity_delta,
                }
                for m in await session.scalars(select(InventoryMovement))
            ],
        }


if __name__ == "__main__":
    import uvicorn

    asyncio.run(seed())
    print((DATA / "manifest.json").read_text(), flush=True)
    uvicorn.run(app, host="127.0.0.1", port=18081)
