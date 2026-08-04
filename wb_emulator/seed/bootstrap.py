"""Idempotent emulator bootstrap: three sellers, stocks, 13+ scenario orders."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from wb_emulator.services import orders_store
from wb_emulator.services.stocks_store import StockItem, upsert_stocks

_SEED_DIR = Path(__file__).resolve().parent
_CATALOG_PATH = _SEED_DIR / "catalog.json"
_ORDERS_PATH = _SEED_DIR / "orders.json"
_TOKENS_PATH = _SEED_DIR / "tokens.json"


@dataclass(frozen=True)
class SeedResult:
    sellers: int
    stocks_upserted: int
    orders_created: int
    orders_skipped: int
    orders_total: int


def load_tokens_map() -> dict[str, str]:
    raw = json.loads(_TOKENS_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("tokens.json must be a JSON object")
    return {str(token): str(seller_key) for token, seller_key in raw.items()}


def load_catalog() -> dict[str, Any]:
    return json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))


def load_order_scenarios() -> list[dict[str, Any]]:
    raw = json.loads(_ORDERS_PATH.read_text(encoding="utf-8"))
    scenarios = raw.get("orders", [])
    if not isinstance(scenarios, list):
        raise ValueError("orders.json: orders must be a list")
    return scenarios


def _resolve_created_at(spec: dict[str, Any]) -> str:
    if spec.get("createdAt"):
        return str(spec["createdAt"])
    hours_ago = int(spec.get("createdHoursAgo", 24))
    ts = datetime.now(tz=UTC) - timedelta(hours=hours_ago)
    return ts.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _build_order_payload(spec: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    seller_key = str(spec["seller_key"])
    seller_products = {
        p["chrtId"]: p
        for block in catalog.get("sellers", [])
        if block.get("seller_key") == seller_key
        for p in block.get("products", [])
    }
    chrt_id = int(spec["chrtId"])
    product = seller_products.get(chrt_id)
    if product is None:
        raise ValueError(f"no product for seller={seller_key} chrtId={chrt_id}")

    warehouse_id = int(spec.get("warehouseId", catalog.get("sharedWarehouseId", 501001)))
    office_id = int(spec.get("officeId", 601001))
    payload: dict[str, Any] = {
        "id": int(spec["id"]),
        "rid": str(spec.get("rid", f"emu-seed-{spec['id']}")),
        "createdAt": _resolve_created_at(spec),
        "nmId": int(product["nmId"]),
        "chrtId": chrt_id,
        "article": str(product["article"]),
        "skus": list(product["skus"]),
        "price": int(product.get("price", 100000)),
        "cargoType": int(spec.get("cargoType", 1)),
        "warehouseId": warehouse_id,
        "officeId": office_id,
        "isLegal": bool(spec.get("isLegal", False)),
        "options": dict(spec.get("options", {"isB2B": False})),
        "supplierStatus": str(spec.get("supplierStatus", "new")),
        "wbStatus": str(spec.get("wbStatus", "waiting")),
        "cancelled": bool(spec.get("cancelled", False)),
    }
    if "canPvz" in spec:
        payload["canPvz"] = bool(spec["canPvz"])
    if "isPvz" in spec:
        payload["isPvz"] = bool(spec["isPvz"])
    if "requiredMeta" in spec:
        payload["requiredMeta"] = list(spec["requiredMeta"])
    if "optionalMeta" in spec:
        payload["optionalMeta"] = list(spec["optionalMeta"])
    return payload


def seed_emulator_data(session: Session, *, idempotent: bool = True) -> SeedResult:
    """Seed stocks and predefined orders for all catalog sellers."""
    catalog = load_catalog()
    scenarios = load_order_scenarios()
    shared_wh = int(catalog.get("sharedWarehouseId", orders_store.DEFAULT_EMULATOR_WAREHOUSE_ID))

    stocks_upserted = 0
    for seller_block in catalog.get("sellers", []):
        seller_key = str(seller_block["seller_key"])
        stocks = [
            StockItem(chrt_id=int(row["chrtId"]), amount=int(row["amount"]))
            for row in seller_block.get("stocks", [])
        ]
        if stocks:
            upsert_stocks(session, seller_key=seller_key, warehouse_id=shared_wh, stocks=stocks)
            stocks_upserted += len(stocks)

    orders_created = 0
    orders_skipped = 0
    for spec in scenarios:
        payload = _build_order_payload(spec, catalog)
        seller_key = str(spec["seller_key"])
        wb_order_id = int(payload["id"])
        existing = orders_store.get_order(session, seller_key, wb_order_id)
        if existing is not None and idempotent:
            orders_skipped += 1
            continue
        orders_store.upsert_order(session, seller_key, payload)
        orders_created += 1

    seller_count = len(catalog.get("sellers", []))
    return SeedResult(
        sellers=seller_count,
        stocks_upserted=stocks_upserted,
        orders_created=orders_created,
        orders_skipped=orders_skipped,
        orders_total=len(scenarios),
    )


def main() -> None:
    from wb_emulator.db import get_session_factory, init_db

    init_db()
    session = get_session_factory()()
    try:
        result = seed_emulator_data(session)
        print(
            f"seed ok: sellers={result.sellers} stocks={result.stocks_upserted} "
            f"orders_created={result.orders_created} skipped={result.orders_skipped} "
            f"total_scenarios={result.orders_total}"
        )
    finally:
        session.close()


if __name__ == "__main__":
    main()
