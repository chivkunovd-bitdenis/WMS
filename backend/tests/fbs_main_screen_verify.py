"""Read back physical stock after browser actions; reservation must not consume it."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.db.session import SessionLocal
from app.models.inventory_balance import InventoryBalance


async def main() -> None:
    database = make_url(os.environ.get("DATABASE_URL", ""))
    if (
        os.environ.get("FBS_MAIN_DISPOSABLE") != "1"
        or database.host != "db"
        or database.database != "wms"
    ):
        raise RuntimeError("Verifier accepts the disposable compose database only")
    seed = json.load(sys.stdin)
    actual: dict[str, int] = {}
    async with SessionLocal() as session:
        balances = (
            await session.scalars(
                select(InventoryBalance).where(
                    InventoryBalance.tenant_id == uuid.UUID(seed["tenant_id"])
                )
            )
        ).all()
        for balance in balances:
            key = str(balance.product_id)
            actual[key] = actual.get(key, 0) + balance.quantity
    expected = seed["main"]["stock_by_product"]
    sys.stdout.write(
        json.dumps({"expected": expected, "actual": actual, "unchanged": actual == expected})
    )
    assert actual == expected, (
        "Creating supplies / reserving / adding must not consume physical stock"
    )


if __name__ == "__main__":
    asyncio.run(main())
