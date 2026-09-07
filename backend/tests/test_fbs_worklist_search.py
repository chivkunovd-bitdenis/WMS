"""WMS-390: server search preserves worklist scope and counts before pagination."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.product import Product
from tests.test_fbs_worklist_query_count import _setup_ff_admin_with_stock


@pytest.mark.asyncio
async def test_search_finds_order_after_500_and_counts_before_cursor(
    async_client: AsyncClient,
) -> None:
    headers, seller_id, _, _, _, ids = await _setup_ff_admin_with_stock(
        async_client, order_count=502
    )
    params = {"status_group": "new", "seller_id": str(seller_id), "limit": 500}
    first = await async_client.get(
        "/operations/fbs-orders/worklist", headers=headers, params=params
    )
    assert first.status_code == 200, first.text
    assert str(ids[-1]) not in {row["id"] for row in first.json()["items"]}
    found = await async_client.get(
        "/operations/fbs-orders/worklist", headers=headers, params={**params, "search": " 800501 "}
    )
    assert found.status_code == 200, found.text
    assert [row["id"] for row in found.json()["items"]] == [str(ids[-1])]
    assert found.json()["total"] == 1
    assert found.json()["warehouse_options"] == first.json()["warehouse_options"]
    page = await async_client.get(
        "/operations/fbs-orders/worklist",
        headers=headers,
        params={**params, "search": "FBS product"},
    )
    assert page.json()["total"] == 502
    tail = await async_client.get(
        "/operations/fbs-orders/worklist",
        headers=headers,
        params={**params, "search": "FBS product", "cursor": page.json()["next_cursor"]},
    )
    assert tail.json()["total"] == 502
    assert [row["id"] for row in tail.json()["items"]] == list(map(str, ids[-2:]))
    for change in (
        {"marketplace": "ozon"},
        {"wb_warehouse_id": 99999},
        {"status_group": "done"},
        {"search": "%"},
        {"search": "9" * 40},
    ):
        empty = await async_client.get(
            "/operations/fbs-orders/worklist",
            headers=headers,
            params={**params, "search": "800501", **change},
        )
        assert empty.status_code == 200, empty.text
        assert empty.json()["items"] == []
        assert empty.json()["total"] == 0


@pytest.mark.asyncio
async def test_supply_search_numbers_members_duplicates_and_scope(
    async_client: AsyncClient,
) -> None:
    headers, seller_id, warehouse_id, product_id, _, order_ids = await _setup_ff_admin_with_stock(
        async_client, order_count=3
    )
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product
        supplies = []
        for idx in range(3):
            supply = FbsSupply(
                tenant_id=product.tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                wb_supply_id=f"WB-GI-SEARCH-{idx}",
                name="Repeated name",
                display_number=f"LOCAL-390-{idx}",
                status="assembling",
                delivery_type="warehouse_sc",
            )
            session.add(supply)
            await session.flush()
            order = await session.get(FbsOrder, order_ids[idx])
            assert order
            order.supply_id = supply.id
            order.wb_supply_id = supply.wb_supply_id
            order.status = "assembling"
            if idx == 2:
                supply.marketplace = order.marketplace = "ozon"
                order.external_order_id = "390-123456-1"
            supplies.append(supply.id)
        await session.commit()
    base = {"status_group": "active", "seller_id": str(seller_id), "limit": 1}
    for term in ("WB-GI-SEARCH-0", "local-390-0", "800000"):
        found = await async_client.get(
            "/operations/fbs-supplies/worklist", headers=headers, params={**base, "search": term}
        )
        assert found.status_code == 200, found.text
        assert [row["id"] for row in found.json()["items"]] == [str(supplies[0])]
        assert found.json()["total"] == 1
    found = await async_client.get(
        "/operations/fbs-orders/worklist", headers=headers, params={**base, "search": "LOCAL-390-0"}
    )
    assert [row["id"] for row in found.json()["items"]] == [str(order_ids[0])]
    for term in ("Repeated name", "FBS product"):
        found = await async_client.get(
            "/operations/fbs-supplies/worklist",
            headers=headers,
            params={**base, "search": term, "marketplace": "wb"},
        )
        assert found.status_code == 200, found.text
        assert len(found.json()["items"]) == 1
        assert found.json()["total"] == 2
    for endpoint in ("fbs-orders", "fbs-supplies"):
        found = await async_client.get(
            f"/operations/{endpoint}/worklist",
            headers=headers,
            params={**base, "search": "390-123456-1", "marketplace": "ozon"},
        )
        assert found.status_code == 200, found.text
        assert found.json()["total"] == 1
        excluded = await async_client.get(
            f"/operations/{endpoint}/worklist",
            headers=headers,
            params={**base, "search": "390-123456-1", "marketplace": "wb"},
        )
        assert excluded.json()["total"] == 0
    other_headers, *_ = await _setup_ff_admin_with_stock(async_client)
    for endpoint in ("fbs-orders", "fbs-supplies"):
        isolated = await async_client.get(
            f"/operations/{endpoint}/worklist",
            headers=other_headers,
            params={"status_group": "active", "search": "WB-GI-SEARCH"},
        )
        assert isolated.status_code == 200, isolated.text
        assert isolated.json()["items"] == []
        assert isolated.json()["total"] == 0
