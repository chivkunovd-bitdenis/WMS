"""WMS-580: лист подбора и лента QR идут в одном порядке (регрессия).

`tape_order_index` (fbs_workspace_service.get_supply_workspace) и порядок
заказов, которые сервер печати ленты (fbs_order_tape_print_service) отдаёт
для «Печать всего», должны считаться одним и тем же ключом —
picking_list_order_key (fbs_picking_order_service). Эти тесты ловят
регрессию, если один из потребителей начнёт считать порядок независимо
(её уже чинили трижды за один день 23.08.2026, коммиты
443638a1 → 30237f3b → 5fb9a6fc — см. docs/requirements/WMS-580.md, Д6).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_ASSEMBLING,
    FBS_ORDER_STATUS_CANCELLED,
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
)
from app.models.fbs_supply import FBS_DELIVERY_TYPE_WAREHOUSE_SC, FbsSupply
from app.models.product import Product
from app.services import fbs_order_tape_print_service as tape_svc
from app.services.tokens import decode_access_token

pytestmark = pytest.mark.asyncio

# Без блока "cz" ни один заказ не требует Честного знака при печати — сервер
# не ходит в WB за пулом кодов и стикерами. Это позволяет проверить именно
# порядок заказов в ленте, не поднимая маркировку и внешние вызовы.
_LABEL_ONLY_LAYOUT = {"units": [{"block": "label", "copies": 1}]}


@dataclass(frozen=True)
class _Seed:
    headers: dict[str, str]
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    seller_id: uuid.UUID
    warehouse_id: uuid.UUID
    supply_id: uuid.UUID
    product_a: uuid.UUID
    article_a: str
    ids: dict[str, uuid.UUID]


async def _register_ff_admin(
    async_client: AsyncClient,
) -> tuple[dict[str, str], str, uuid.UUID, uuid.UUID]:
    suffix = str(time.time_ns())
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"WMS-580 {suffix}",
            "slug": f"wms580-{suffix}",
            "admin_email": f"wms580-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    claims = decode_access_token(token)
    return (
        {"Authorization": f"Bearer {token}"},
        suffix,
        uuid.UUID(claims["tenant_id"]),
        uuid.UUID(claims["sub"]),
    )


async def _seller_and_warehouse(
    async_client: AsyncClient, headers: dict[str, str], suffix: str
) -> tuple[uuid.UUID, uuid.UUID]:
    seller = await async_client.post("/sellers", headers=headers, json={"name": f"Seller {suffix}"})
    assert seller.status_code in (200, 201), seller.text
    warehouse = await async_client.post(
        "/warehouses", headers=headers, json={"name": "WH", "code": f"wh-{suffix[-8:]}"},
    )
    assert warehouse.status_code in (200, 201), warehouse.text
    return uuid.UUID(seller.json()["id"]), uuid.UUID(warehouse.json()["id"])


async def _create_supply(
    *, tenant_id: uuid.UUID, seller_id: uuid.UUID, warehouse_id: uuid.UUID, suffix: str,
) -> uuid.UUID:
    async with SessionLocal() as session:
        supply = FbsSupply(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            wb_supply_id=f"WB-580-{suffix}",
            name=f"WMS-580 supply {suffix}",
            delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        )
        session.add(supply)
        await session.commit()
        return supply.id


async def _create_product(
    *, tenant_id: uuid.UUID, seller_id: uuid.UUID, suffix: str, article: str,
) -> uuid.UUID:
    async with SessionLocal() as session:
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name=f"Товар {article} {suffix}",
            sku_code=f"SKU-{article}-{suffix}",
            wb_vendor_code=article,
        )
        session.add(product)
        await session.commit()
        return product.id


async def _create_order_row(
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    supply_id: uuid.UUID,
    product_id: uuid.UUID,
    wb_article: str,
    wb_order_id: int,
    status: str = FBS_ORDER_STATUS_ASSEMBLING,
) -> uuid.UUID:
    now = datetime.now(tz=UTC)
    async with SessionLocal() as session:
        order = FbsOrder(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            wb_order_id=wb_order_id,
            wb_rid=f"rid-{wb_order_id}",
            wb_nm_id=wb_order_id + 1_000_000,
            wb_chrt_id=wb_order_id + 2_000_000,
            wb_article=wb_article,
            wb_barcode=None,
            price=1000,
            is_legal=False,
            cargo_type="mgt",
            wb_office_id=42,
            wb_warehouse_id=99,
            can_pvz=False,
            supply_id=supply_id,
            sticker_code=None,
            status=status,
            created_at_wb=now,
            deadline_at=now + timedelta(days=1),
            mapping_status=MAPPING_STATUS_MAPPED,
            reserve_status=RESERVE_STATUS_RESERVED,
        )
        session.add(order)
        await session.commit()
        return order.id


async def _seed_two_products_four_orders(async_client: AsyncClient) -> _Seed:
    """Товар A (артикул сортируется раньше) — 3 заказа не по порядку номеров WB,
    товар B (артикул сортируется позже) — 1 заказ. Ожидаемый порядок листа —
    A-100, A-200, A-300, B-150 (сначала товар, потом номер заказа WB)."""
    headers, suffix, tenant_id, user_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _seller_and_warehouse(async_client, headers, suffix)
    supply_id = await _create_supply(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id, suffix=suffix,
    )
    article_a = f"WMS580-A-{suffix}"
    article_b = f"WMS580-B-{suffix}"
    product_a = await _create_product(
        tenant_id=tenant_id, seller_id=seller_id, suffix=suffix, article=article_a,
    )
    product_b = await _create_product(
        tenant_id=tenant_id, seller_id=seller_id, suffix=suffix, article=article_b,
    )
    ids: dict[str, uuid.UUID] = {}
    # Создаём заказы товара A НЕ по возрастанию номера WB — порядок листа должен
    # выправить это тай-брейком, а не полагаться на порядок создания в базе.
    for label, wb_order_id in (("a300", 300), ("a100", 100), ("a200", 200)):
        ids[label] = await _create_order_row(
            tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            supply_id=supply_id, product_id=product_a,
            wb_article=article_a, wb_order_id=wb_order_id,
        )
    ids["b150"] = await _create_order_row(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        supply_id=supply_id, product_id=product_b,
        wb_article=article_b, wb_order_id=150,
    )
    return _Seed(
        headers=headers,
        tenant_id=tenant_id,
        user_id=user_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        supply_id=supply_id,
        product_a=product_a,
        article_a=article_a,
        ids=ids,
    )


async def test_workspace_tape_order_index_matches_picking_list_order(
    async_client: AsyncClient,
) -> None:
    """R1: tape_order_index (числа для листа подбора на фронте) идёт в порядке
    «товар по артикулу, затем номер заказа WB» — том же, что и лента."""
    seed = await _seed_two_products_four_orders(async_client)
    response = await async_client.get(
        f"/operations/fbs-supplies/{seed.supply_id}/workspace", headers=seed.headers,
    )
    assert response.status_code == 200, response.text
    orders = response.json()["orders"]
    by_id = {str(seed.ids[key]): key for key in seed.ids}
    ordered_labels = [
        by_id[item["id"]]
        for item in sorted(orders, key=lambda item: item["tape_order_index"])
    ]
    assert ordered_labels == ["a100", "a200", "a300", "b150"]


async def test_full_tape_print_matches_picking_list_order(async_client: AsyncClient) -> None:
    """R1: «Печать всего» — сервер пересчитывает порядок тем же ключом, что и
    tape_order_index, даже если клиент прислал заказы вперемешку."""
    seed = await _seed_two_products_four_orders(async_client)
    shuffled_order_ids = [seed.ids["a300"], seed.ids["b150"], seed.ids["a100"], seed.ids["a200"]]
    async with SessionLocal() as session, httpx.AsyncClient() as http_client:
        result = await tape_svc.print_fbs_order_tape(
            session,
            seed.tenant_id,
            seed.supply_id,
            order_ids=shuffled_order_ids,
            layout=_LABEL_ONLY_LAYOUT,
            allow_partial=True,
            include_order_qr=False,
            reprint=False,
            actor_user_id=seed.user_id,
            http_client=http_client,
        )
    assert not result.order_errors, result.order_errors
    printed_ids = [row.order_id for row in result.orders]
    assert printed_ids == [seed.ids["a100"], seed.ids["a200"], seed.ids["a300"], seed.ids["b150"]]


async def test_partial_tape_print_preserves_caller_order(async_client: AsyncClient) -> None:
    """R3: «Печать выбранного» — сервер доверяет присланному порядку подмножества
    и не пересчитывает его заново (в отличие от полного набора). Фронт обязан
    прислать подмножество уже в порядке листа (fullTapeOrders.filter) — здесь
    проверяется, что сервер это не портит и не подменяет своей сортировкой."""
    seed = await _seed_two_products_four_orders(async_client)
    # Тот же относительный порядок, что и в полном листе (a200 раньше a300).
    async with SessionLocal() as session, httpx.AsyncClient() as http_client:
        result = await tape_svc.print_fbs_order_tape(
            session,
            seed.tenant_id,
            seed.supply_id,
            order_ids=[seed.ids["a200"], seed.ids["a300"]],
            layout=_LABEL_ONLY_LAYOUT,
            allow_partial=True,
            include_order_qr=False,
            reprint=False,
            actor_user_id=seed.user_id,
            http_client=http_client,
        )
    assert not result.order_errors, result.order_errors
    assert [row.order_id for row in result.orders] == [seed.ids["a200"], seed.ids["a300"]]


async def test_cancelled_order_does_not_shift_remaining_tape_order(
    async_client: AsyncClient,
) -> None:
    """R4/C4: отменённый заказ выпадает из напечатанной ленты (существующее
    поведение — не про порядок), но не сдвигает порядок остальных заказов."""
    seed = await _seed_two_products_four_orders(async_client)
    cancelled_id = await _create_order_row(
        tenant_id=seed.tenant_id,
        seller_id=seed.seller_id,
        warehouse_id=seed.warehouse_id,
        supply_id=seed.supply_id,
        product_id=seed.product_a,
        wb_article=seed.article_a,
        wb_order_id=250,
        status=FBS_ORDER_STATUS_CANCELLED,
    )
    all_ids = [seed.ids["a300"], seed.ids["b150"], seed.ids["a100"], cancelled_id, seed.ids["a200"]]
    async with SessionLocal() as session, httpx.AsyncClient() as http_client:
        result = await tape_svc.print_fbs_order_tape(
            session,
            seed.tenant_id,
            seed.supply_id,
            order_ids=all_ids,
            layout=_LABEL_ONLY_LAYOUT,
            allow_partial=True,
            include_order_qr=False,
            reprint=False,
            actor_user_id=seed.user_id,
            http_client=http_client,
        )
    printed_ids = [row.order_id for row in result.orders]
    assert cancelled_id not in printed_ids
    assert printed_ids == [seed.ids["a100"], seed.ids["a200"], seed.ids["a300"], seed.ids["b150"]]
    assert any(
        err.order_id == cancelled_id and err.code == "order_cancelled"
        for err in result.order_errors
    )
