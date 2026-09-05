import json
import uuid

import pytest
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_count import InventoryCountCreatedContainer
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.warehouse_box import WarehouseBox
from app.services import inventory_count_service as service
from test_inventory_counts import _balance, _create_all, _product, _tenant


def tree_ids(body):
    def collect(nodes):
        result = set()
        for node in nodes:
            if node["kind"] != "product":
                result.add(node["id"])
                result |= collect(node["children"])
        return result
    return set().union(*(collect(cell["children"]) for cell in body["cells"]))


@pytest.mark.asyncio
async def test_a29_committed_box_survives_failed_document_link_and_retry(
    async_client, monkeypatch,
):
    setup = await _tenant(async_client, "A29synthetic")
    product_id = await _product(async_client, setup, name="Synthetic A29 product")
    await _balance(setup, product_id, 3)
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        product.wb_barcode = "4600000000029"
        await session.commit()
    document = await _create_all(async_client, setup)
    count_id = uuid.UUID(document["id"])
    url = f"/operations/inventory-counts/{count_id}/containers"
    actual_create = service.warehouse_map_service.create_sorting_object
    captured = []

    async def fail_after_box_commit(*args, **kwargs):
        result = await actual_create(*args, **kwargs)
        captured.append(result["id"])
        raise RuntimeError("A29 injected after container commit, before document link")

    monkeypatch.setattr(service.warehouse_map_service, "create_sorting_object", fail_after_box_commit)
    with pytest.raises(RuntimeError, match="A29 injected"):
        await async_client.post(url, headers=setup.headers, json={"kind": "box"})
    first_id = captured[0]
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(WarehouseBox)) == 1
        assert await session.scalar(select(func.count()).select_from(InventoryCountCreatedContainer)) == 0
        assert await session.scalar(select(func.sum(InventoryBalance.quantity))) == 3
        assert await session.scalar(select(func.count()).select_from(InventoryMovement)) == 0
    failed_view = await async_client.get(
        f"/operations/inventory-counts/{count_id}", headers=setup.headers,
    )
    assert failed_view.status_code == 200
    assert first_id not in tree_ids(failed_view.json())
    assert first_id in {item["id"] for item in failed_view.json()["scannable_containers"]}

    monkeypatch.setattr(service.warehouse_map_service, "create_sorting_object", actual_create)
    retry = await async_client.post(url, headers=setup.headers, json={"kind": "box"})
    assert retry.status_code == 200, retry.text
    async with SessionLocal() as session:
        boxes = list((await session.scalars(select(WarehouseBox))).all())
        links = list((await session.scalars(select(InventoryCountCreatedContainer))).all())
        assert len(boxes) == 2 and len(links) == 1
        assert str(links[0].container_id) != first_id
    assert first_id not in tree_ids(retry.json())
    assert str(links[0].container_id) in tree_ids(retry.json())

    recovered = await async_client.post(
        f"/operations/inventory-counts/{count_id}/found", headers=setup.headers,
        json={"barcodes": ["4600000000029"], "container_kind": "box", "container_id": first_id},
    )
    assert recovered.status_code == 200, recovered.text
    assert first_id in tree_ids(recovered.json()["count"])
    async with SessionLocal() as session:
        assert await session.scalar(select(func.sum(InventoryBalance.quantity))) == 3
        assert await session.scalar(select(func.count()).select_from(InventoryMovement)) == 0
    print("A29_RESULT=" + json.dumps({
        "after_failure": {"boxes": 1, "document_links": 0, "tree_visible": False, "scannable": True},
        "after_retry": {"boxes": 2, "document_links": 1, "original_reused": False},
        "after_found_scan": {"original_tree_visible": True, "physical_stock": 3, "movements": 0},
    }))
