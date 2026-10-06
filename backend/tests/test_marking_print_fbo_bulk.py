"""WMS-618: атомарная + идемпотентная общая печать ЧЗ по всей FBO-отгрузке."""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from test_packaging_tasks import _inventory_at_location, _register_admin

from app.db.session import SessionLocal
from app.models.marketplace_unload import MarketplaceUnloadRequest
from app.models.packaging_task import PackagingTask


async def _attach_task_to_fbo(task_id: str, seller_id: str, warehouse_id: str) -> str:
    async with SessionLocal() as session:
        task = await session.get(PackagingTask, uuid.UUID(task_id))
        assert task is not None
        request = MarketplaceUnloadRequest(
            tenant_id=task.tenant_id,
            warehouse_id=uuid.UUID(warehouse_id),
            seller_id=uuid.UUID(seller_id),
            marketplace="wb",
            status="collecting",
        )
        session.add(request)
        await session.flush()
        task.marketplace_unload_request_id = request.id
        await session.commit()
        return str(request.id)


async def _create_fbo_task_with_lines(
    async_client: AsyncClient,
    h: dict[str, str],
    *,
    seller_id: str,
    warehouse_id: str,
    lines: list[dict[str, object]],
) -> str:
    task = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={"warehouse_id": warehouse_id, "lines": lines},
    )
    assert task.status_code in (200, 201), task.text
    task_id = task.json()["id"]
    await _attach_task_to_fbo(task_id, seller_id=seller_id, warehouse_id=warehouse_id)
    return task_id


async def _make_cz_product(
    async_client: AsyncClient,
    h: dict[str, str],
    *,
    seller_id: str,
    suffix: str,
) -> tuple[str, str]:
    sku = f"FB-{suffix}-{uuid.uuid4().hex[:4]}"
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": f"CZ item {suffix}",
            "sku_code": sku,
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    pid = pr.json()["id"]
    await async_client.patch(
        f"/products/{pid}/packaging-instructions",
        headers=h,
        json={"requires_honest_sign": True},
    )
    return pid, sku


async def _import_codes(
    async_client: AsyncClient,
    h: dict[str, str],
    *,
    seller_id: str,
    pool_product_id: str,
    serial_prefix: str,
    count: int,
    title: str,
) -> None:
    codes = [f"01{'0' * 10}{idx:04d}21{serial_prefix}{idx:08d}" for idx in range(count)]
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps([{"title": title, "product_ids": [pool_product_id]}]),
        },
        files=[
            (
                "files",
                ("codes.csv", ("cis\n" + "\n".join(codes)).encode(), "text/csv"),
            ),
        ],
    )
    assert imp.status_code == 200, imp.text


@pytest.mark.asyncio
async def test_print_fbo_bulk_rejects_non_fbo_task(async_client: AsyncClient) -> None:
    """R10: endpoint отвечает 422 на обычное (не-FBO) задание упаковки."""
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Non-FBO", "email": f"nf-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    wh = await async_client.post("/warehouses", headers=h, json={"name": "WNF", "code": "w-nf"})
    wh_id = wh.json()["id"]
    pid, _sku = await _make_cz_product(async_client, h, seller_id=seller_id, suffix="n")
    loc_id = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=pid, qty=1, location_code="nf-1",
    )
    task = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "lines": [{"product_id": pid, "storage_location_id": loc_id, "quantity": 1}],
        },
    )
    task_id = task.json()["id"]

    resp = await async_client.post(
        f"/operations/marking-codes/packaging-tasks/{task_id}/print-fbo-bulk",
        headers=h,
        json={"allow_partial": False},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "not_fbo_shipment"


@pytest.mark.asyncio
async def test_old_print_all_still_410_gone(async_client: AsyncClient) -> None:
    """R10: старый /print-all намеренно отвечает 410 Gone даже на FBO."""
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "OEP", "email": f"oep-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    wh = await async_client.post("/warehouses", headers=h, json={"name": "WOEP", "code": "w-oep"})
    wh_id = wh.json()["id"]
    pid, _sku = await _make_cz_product(async_client, h, seller_id=seller_id, suffix="o")
    loc_id = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=pid, qty=1, location_code="oep-1",
    )
    task_id = await _create_fbo_task_with_lines(
        async_client,
        h,
        seller_id=seller_id,
        warehouse_id=wh_id,
        lines=[{"product_id": pid, "storage_location_id": loc_id, "quantity": 1}],
    )
    resp = await async_client.post(
        f"/operations/marking-codes/packaging-tasks/{task_id}/print-all",
        headers=h,
        json={"allow_partial": False},
    )
    assert resp.status_code == 410, resp.text
    assert resp.json()["detail"]["code"] == "endpoint_removed"


@pytest.mark.asyncio
async def test_print_fbo_bulk_includes_non_cz_lines_in_snapshot(
    async_client: AsyncClient,
) -> None:
    """R2+R3: ответ содержит ВСЕ строки задания (ЧЗ и не-ЧЗ) в текущем составе.
    Фронт собирает ленту по этому ответу, без вторых запросов и без вчерашнего
    снимка task.lines."""
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Mix", "email": f"mix-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    wh = await async_client.post("/warehouses", headers=h, json={"name": "WM", "code": "w-m"})
    wh_id = wh.json()["id"]

    cz_pid, cz_sku = await _make_cz_product(async_client, h, seller_id=seller_id, suffix="cz")
    # Non-CZ product: just skip the requires_honest_sign patch
    wb_sku = f"WB-{uuid.uuid4().hex[:4]}"
    wb_resp = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "WB only",
            "sku_code": wb_sku,
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    wb_pid = wb_resp.json()["id"]

    await _import_codes(
        async_client, h, seller_id=seller_id, pool_product_id=cz_pid,
        serial_prefix="SNA", count=5, title="pool-cz",
    )

    cz_loc = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=cz_pid, qty=2, location_code="mix-cz",
    )
    wb_loc = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=wb_pid, qty=3, location_code="mix-wb",
    )
    task_id = await _create_fbo_task_with_lines(
        async_client, h, seller_id=seller_id, warehouse_id=wh_id,
        lines=[
            {"product_id": cz_pid, "storage_location_id": cz_loc, "quantity": 2},
            {"product_id": wb_pid, "storage_location_id": wb_loc, "quantity": 3},
        ],
    )

    resp = await async_client.post(
        f"/operations/marking-codes/packaging-tasks/{task_id}/print-fbo-bulk",
        headers=h,
        json={"allow_partial": False, "layout_json": {"units": [{"block": "cz", "copies": 1}]}},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["shortage"] == 0
    assert len(data["lines"]) == 2
    cz_line = next(ln for ln in data["lines"] if ln["product_id"] == cz_pid)
    wb_line = next(ln for ln in data["lines"] if ln["product_id"] == wb_pid)
    assert cz_line["requires_honest_sign"] is True
    assert cz_line["quantity"] == 2
    assert len(cz_line["printed_codes"]) == 2
    assert wb_line["requires_honest_sign"] is False
    assert wb_line["quantity"] == 3
    assert wb_line["printed_codes"] == []
    assert wb_line["sku_code"] == wb_sku
    assert cz_line["sku_code"] == cz_sku


@pytest.mark.asyncio
async def test_print_fbo_bulk_is_idempotent_on_retry(
    async_client: AsyncClient,
) -> None:
    """R9: повтор запроса возвращает ТЕ ЖЕ коды, не выпускает новые.
    Без идемпотентности при потере ответа оператор нажмёт «Печать» второй раз
    и сожжёт второй набор КМ — Astra отдельно подчеркнула это требование."""
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Idemp", "email": f"idm-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    wh = await async_client.post("/warehouses", headers=h, json={"name": "WI", "code": "w-i"})
    wh_id = wh.json()["id"]
    pid, _sku = await _make_cz_product(async_client, h, seller_id=seller_id, suffix="i")
    await _import_codes(
        async_client, h, seller_id=seller_id, pool_product_id=pid,
        serial_prefix="IDM", count=10, title="pool-i",
    )
    loc = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=pid, qty=3, location_code="idm-1",
    )
    task_id = await _create_fbo_task_with_lines(
        async_client, h, seller_id=seller_id, warehouse_id=wh_id,
        lines=[{"product_id": pid, "storage_location_id": loc, "quantity": 3}],
    )

    first = await async_client.post(
        f"/operations/marking-codes/packaging-tasks/{task_id}/print-fbo-bulk",
        headers=h,
        json={"allow_partial": False, "layout_json": {"units": [{"block": "cz", "copies": 1}]}},
    )
    assert first.status_code == 200, first.text
    first_codes = {
        c["id"] for ln in first.json()["lines"] for c in ln["printed_codes"]
    }
    assert len(first_codes) == 3

    # Retry (as if the client lost the first response and clicked again).
    second = await async_client.post(
        f"/operations/marking-codes/packaging-tasks/{task_id}/print-fbo-bulk",
        headers=h,
        json={"allow_partial": False, "layout_json": {"units": [{"block": "cz", "copies": 1}]}},
    )
    assert second.status_code == 200, second.text
    second_codes = {
        c["id"] for ln in second.json()["lines"] for c in ln["printed_codes"]
    }
    assert second_codes == first_codes
    assert second.json()["shortage"] == 0


@pytest.mark.asyncio
async def test_print_fbo_bulk_partial_recovery_fills_only_missing(
    async_client: AsyncClient,
) -> None:
    """R9: 1 строка из 2 уже напечатана до запроса — bulk довыдаёт только
    недостающие и возвращает полный набор по обеим строкам."""
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Partial", "email": f"prt-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    wh = await async_client.post("/warehouses", headers=h, json={"name": "WP", "code": "w-p"})
    wh_id = wh.json()["id"]
    pid1, _ = await _make_cz_product(async_client, h, seller_id=seller_id, suffix="p1")
    pid2, _ = await _make_cz_product(async_client, h, seller_id=seller_id, suffix="p2")
    await _import_codes(
        async_client, h, seller_id=seller_id, pool_product_id=pid1,
        serial_prefix="P1A", count=5, title="pool-p1",
    )
    await _import_codes(
        async_client, h, seller_id=seller_id, pool_product_id=pid2,
        serial_prefix="P2A", count=5, title="pool-p2",
    )
    loc1 = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=pid1, qty=2, location_code="p-1",
    )
    loc2 = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=pid2, qty=2, location_code="p-2",
    )
    task_id = await _create_fbo_task_with_lines(
        async_client, h, seller_id=seller_id, warehouse_id=wh_id,
        lines=[
            {"product_id": pid1, "storage_location_id": loc1, "quantity": 2},
            {"product_id": pid2, "storage_location_id": loc2, "quantity": 2},
        ],
    )

    # Pre-print the first line per-line (simulate interrupted bulk — the first
    # line is already fully printed when the operator retries the bulk click).
    pre_resp = await async_client.get(
        f"/operations/packaging-tasks/{task_id}",
        headers=h,
    )
    assert pre_resp.status_code == 200, pre_resp.text
    first_line = next(
        ln for ln in pre_resp.json()["lines"] if ln["product_id"] == pid1
    )
    per_line = await async_client.post(
        f"/operations/marking-codes/packaging-lines/{first_line['id']}/print",
        headers=h,
        json={"layout_json": {"units": [{"block": "cz", "copies": 1}]}},
    )
    assert per_line.status_code == 200, per_line.text
    already_cis = {c["id"] for c in per_line.json().get("printed_codes", [])}
    assert len(already_cis) == 2

    # Bulk retry: must issue the SECOND line's missing codes and return BOTH
    # lines' full code set.
    bulk = await async_client.post(
        f"/operations/marking-codes/packaging-tasks/{task_id}/print-fbo-bulk",
        headers=h,
        json={"allow_partial": False, "layout_json": {"units": [{"block": "cz", "copies": 1}]}},
    )
    assert bulk.status_code == 200, bulk.text
    data = bulk.json()
    assert data["shortage"] == 0
    assert len(data["lines"]) == 2
    line_a = next(ln for ln in data["lines"] if ln["product_id"] == pid1)
    line_b = next(ln for ln in data["lines"] if ln["product_id"] == pid2)
    assert len(line_a["printed_codes"]) == 2
    assert len(line_b["printed_codes"]) == 2
    returned_a = {c["id"] for c in line_a["printed_codes"]}
    assert returned_a == already_cis  # same codes, no new issuance for line A
    # Second retry (idempotency across concurrent-safe lock) returns same codes.
    bulk2 = await async_client.post(
        f"/operations/marking-codes/packaging-tasks/{task_id}/print-fbo-bulk",
        headers=h,
        json={"allow_partial": False, "layout_json": {"units": [{"block": "cz", "copies": 1}]}},
    )
    assert bulk2.status_code == 200
    data2 = bulk2.json()
    def _codes(d: dict[str, object]) -> set[str]:
        return {c["id"] for ln in d["lines"] for c in ln["printed_codes"]}  # type: ignore[index]
    assert _codes(data2) == _codes(data)


@pytest.mark.asyncio
async def test_print_fbo_bulk_shortage_no_partial_does_not_issue(
    async_client: AsyncClient,
) -> None:
    """R9: при нехватке КМ и allow_partial=False сервер НИЧЕГО не выдаёт.
    Ответ показывает shortage, чтобы оператор пополнил пул и повторил; но
    ни одна КМ не сжигается."""
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Short", "email": f"sh-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    wh = await async_client.post("/warehouses", headers=h, json={"name": "WS", "code": "w-s"})
    wh_id = wh.json()["id"]
    pid, _ = await _make_cz_product(async_client, h, seller_id=seller_id, suffix="s")
    # Import only ONE code; task needs TWO units.
    await _import_codes(
        async_client, h, seller_id=seller_id, pool_product_id=pid,
        serial_prefix="SHA", count=1, title="pool-s",
    )
    loc = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=pid, qty=2, location_code="s-1",
    )
    task_id = await _create_fbo_task_with_lines(
        async_client, h, seller_id=seller_id, warehouse_id=wh_id,
        lines=[{"product_id": pid, "storage_location_id": loc, "quantity": 2}],
    )

    resp = await async_client.post(
        f"/operations/marking-codes/packaging-tasks/{task_id}/print-fbo-bulk",
        headers=h,
        json={"allow_partial": False, "layout_json": {"units": [{"block": "cz", "copies": 1}]}},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["shortage"] == 1
    # Nothing bound to the line, since we refused to issue when short.
    assert data["lines"][0]["printed_codes"] == []


@pytest.mark.asyncio
async def test_print_fbo_bulk_shortage_allow_partial_issues_available(
    async_client: AsyncClient,
) -> None:
    """R9: `allow_partial=True` выпускает те КМ, что доступны; остальные
    остаются неотпечатанными — повторный клик с allow_partial их добавит."""
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Pap", "email": f"ap-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    wh = await async_client.post("/warehouses", headers=h, json={"name": "WA", "code": "w-a"})
    wh_id = wh.json()["id"]
    pid, _ = await _make_cz_product(async_client, h, seller_id=seller_id, suffix="a")
    await _import_codes(
        async_client, h, seller_id=seller_id, pool_product_id=pid,
        serial_prefix="APA", count=1, title="pool-a",
    )
    loc = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=pid, qty=2, location_code="a-1",
    )
    task_id = await _create_fbo_task_with_lines(
        async_client, h, seller_id=seller_id, warehouse_id=wh_id,
        lines=[{"product_id": pid, "storage_location_id": loc, "quantity": 2}],
    )

    resp = await async_client.post(
        f"/operations/marking-codes/packaging-tasks/{task_id}/print-fbo-bulk",
        headers=h,
        json={"allow_partial": True, "layout_json": {"units": [{"block": "cz", "copies": 1}]}},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    line = data["lines"][0]
    assert len(line["printed_codes"]) == 1
    assert line["shortage"] == 1


@pytest.mark.asyncio
async def test_print_fbo_bulk_only_non_honest_sign_lines(
    async_client: AsyncClient,
) -> None:
    """R3: отгрузка без ЧЗ. Сервер ничего не выдаёт, но возвращает актуальный
    снимок строк — фронт печатает только ШК."""
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "WB-only", "email": f"nh-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    wh = await async_client.post("/warehouses", headers=h, json={"name": "WNH", "code": "w-nh"})
    wh_id = wh.json()["id"]
    sku = f"NH-{uuid.uuid4().hex[:6]}"
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "WB only item",
            "sku_code": sku,
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    pid = pr.json()["id"]
    loc_id = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=pid, qty=3, location_code="nh-1",
    )
    task_id = await _create_fbo_task_with_lines(
        async_client, h, seller_id=seller_id, warehouse_id=wh_id,
        lines=[{"product_id": pid, "storage_location_id": loc_id, "quantity": 3}],
    )

    resp = await async_client.post(
        f"/operations/marking-codes/packaging-tasks/{task_id}/print-fbo-bulk",
        headers=h,
        json={"allow_partial": False},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["shortage"] == 0
    assert len(data["lines"]) == 1
    assert data["lines"][0]["requires_honest_sign"] is False
    assert data["lines"][0]["quantity"] == 3
    assert data["lines"][0]["printed_codes"] == []


@pytest.mark.asyncio
async def test_print_fbo_bulk_isolates_tenant_and_other_shipment(
    async_client: AsyncClient,
) -> None:
    """R9: endpoint не трогает соседнее FBO-задание и не отвечает на чужого
    арендатора — остальные бизнес-защиты уже есть; эта проверка только,
    что идемпотентный путь их не ломает."""
    h = await _register_admin(async_client)
    other_h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Iso", "email": f"iso-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    wh = await async_client.post("/warehouses", headers=h, json={"name": "WIX", "code": "w-ix"})
    wh_id = wh.json()["id"]
    pid, _ = await _make_cz_product(async_client, h, seller_id=seller_id, suffix="x")
    await _import_codes(
        async_client, h, seller_id=seller_id, pool_product_id=pid,
        serial_prefix="IXA", count=3, title="pool-x",
    )
    loc = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=pid, qty=1, location_code="ix-1",
    )
    task_id = await _create_fbo_task_with_lines(
        async_client, h, seller_id=seller_id, warehouse_id=wh_id,
        lines=[{"product_id": pid, "storage_location_id": loc, "quantity": 1}],
    )

    # Other tenant must NOT be able to touch this task via the bulk endpoint.
    other_resp = await async_client.post(
        f"/operations/marking-codes/packaging-tasks/{task_id}/print-fbo-bulk",
        headers=other_h,
        json={"allow_partial": False},
    )
    assert other_resp.status_code in (403, 404), other_resp.text
