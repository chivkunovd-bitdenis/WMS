"""Isolated WMS-351 QA; only loopback network, no marketplace accounts."""

import json
import os
import sys
from pathlib import Path

QA = Path(__file__).resolve().parent
ROOT = QA.parents[1]
DB_NAME = "wms351_browser_6b1"
os.environ["DATABASE_URL"] = (
    f"postgresql+psycopg_async://deniscivkunov@127.0.0.1:5432/{DB_NAME}"
)
os.environ["JWT_SECRET_KEY"] = "synthetic-wms351-local-only-secret-32-chars"
os.environ["WMS_DATA_DIR"] = str(QA / "data")
os.environ["WMS_AUTO_CREATE_SCHEMA"] = "0"
os.environ["WMS_BOOTSTRAP_ADMIN"] = "0"
sys.path.insert(0, str(ROOT / "backend"))


def boundary(event, args):
    if event == "socket.connect":
        address = args[1]
        if isinstance(address, tuple) and address[0] not in (
            "127.0.0.1",
            "::1",
            "localhost",
        ):
            with (QA / "blocked-network.jsonl").open("a") as stream:
                stream.write(json.dumps({"address": list(address)}) + "\n")
            raise RuntimeError("Synthetic QA forbids non-loopback connections")


sys.addaudithook(boundary)
import httpx
from app.services import fbs_autopoll_service as autopoll
from app.services import fbs_stock_sync_service as wb_sync
from app.services import fbs_seller_warehouse_service as warehouses
from app.services import ozon_provider_factory
from app.services import marketplace_account_service
from tests.test_fbs_stock_sync import _MockStocksTransport
from sqlalchemy import select
from app.models.seller import Seller

transport = _MockStocksTransport()
original_client = httpx.AsyncClient

def log(marketplace, operation, payload):
    with (QA / "external.jsonl").open("a") as stream:
        stream.write(json.dumps(dict(marketplace=marketplace, operation=operation, payload=payload)) + "\n")

def handler(request):
    if "/stocks/" in request.url.path:
        log("wb", request.method, json.loads(request.content))
        return transport.handler(request)
    if request.method == "GET" and "warehouses" in request.url.path:
        return httpx.Response(200, json=[dict(id=501001, name="QA351 WB", officeId=1, cargoType=1, deliveryType=1)])
    raise RuntimeError("Unexpected synthetic external request: " + request.url.path)

httpx.AsyncClient = lambda *a, **kw: original_client(*a, **dict(kw, transport=httpx.MockTransport(handler)))
async def token(*_a, **_kw): return "synthetic-local-token"
wb_sync.get_decrypted_marketplace_token = token
warehouses.get_decrypted_marketplace_token = token
async def credentials(*_a, **_kw): return ("synthetic-client", "synthetic-key")
marketplace_account_service.MarketplaceAccountService.stored_credentials = credentials

class Ozon:
    async def publish_stocks(self, **kwargs):
        log("ozon", "publish", kwargs["stocks"])
        return len(kwargs["stocks"])
    async def fetch_warehouses(self, **kwargs):
        return [dict(warehouse_id=501002, name="QA351 Ozon", is_rfbs=False, has_entrusted_acceptance=False)]
ozon_provider_factory.build_ozon_provider = lambda **_kw: Ozon()
warehouses.build_ozon_provider = lambda **_kw: Ozon()
warehouses.ozon_live_api_enabled = lambda: True
autopoll.build_ozon_provider = lambda **_kw: Ozon()
async def targets(session):
    sellers = (await session.scalars(select(Seller))).all()
    return [autopoll.SellerPollTarget(s.tenant_id, s.id, mp) for s in sellers for mp in ("wb", "ozon")]
autopoll.list_marketplace_poll_targets = targets
from app.main import create_app

app = create_app()


@app.middleware("http")
async def capture(request, call_next):
    if request.url.path.startswith("/operations/"):
        with (QA / "requests.jsonl").open("a") as stream:
            stream.write(
                json.dumps({"method": request.method, "path": request.url.path}) + "\n"
            )
    return await call_next(request)
