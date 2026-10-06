"""WMS-650 · общая тестовая среда раскладки после приёмки (контракт тестов).

Среда из раздела «Проверки этапа 2» документа docs/requirements/WMS-650.md:
документ приёмки A в статусе сортировки — короба К1 и К2 с товаром Т1, К3 с Т2,
грузоместо Г1, россыпь Т1 и Т3 с длинным названием, палета П1 (созданная на
экране), ячейки «А 1.1», «А 1.2», «Б 1.1»; документ B того же селлера с тем же
Т1 и документ C другого селлера.

Документы проводятся настоящими сервисами приёмки (как в соседних тестах
сортировки), а действия раскладки и «назад» выполняются только через HTTP-ручки
экрана: проверяемая операция не подменяется.

Ручка «назад» в продукте ещё не существует. Контракт для разработчика:

    POST /warehouses/{warehouse_id}/sorting-objects/undo
    {
      "inbound_request_id": "<документ>",
      "operation_id": "<собственный идентификатор отмены>",
      "target_operation_id": "<operation_id отменяемого действия раскладки>"
    }

200 — отмена выполнена (или это повтор той же отмены с тем же operation_id —
тогда ничего не меняется); 409 — отменить нельзя (объект уже перемещён после
действия, документ уже оприходован этим действием), ничего не меняется. Всё, что
нужно вернуть, сервер берёт из квитанций самого действия (решение Д2).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from httpx import AsyncClient, Response
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.billing import BillingLedgerEntry, BillingRunIssue
from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_order import FbsOrderReservation
from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeBoxLine,
    InboundIntakeCargoPlace,
    InboundIntakeCargoPlaceLine,
    InboundIntakeLine,
    InboundIntakeRequest,
)
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.inventory_reservation import InventoryReservation
from app.models.marketplace_unload_reservation import MarketplaceUnloadReservation
from app.models.pallet import Pallet
from app.models.product import Product
from app.models.user import User
from app.models.warehouse_box import WarehouseBox
from app.services import inbound_intake_box_service as box_svc
from app.services import inbound_intake_service as intake
from app.services import warehouse_map_service as warehouse_map
from app.services.catalog_service import create_location, create_product, create_warehouse
from app.services.fbs_stock_availability_service import fbs_stock_breakdown_by_product
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.tokens import create_access_token, decode_access_token

LONG_T3_NAME = (
    "Термокружка из нержавеющей стали с двойными стенками и герметичной крышкой-поилкой, "
    "450 мл, цвет графитовый матовый"
)
assert len(LONG_T3_NAME) >= 90

# Перемещения внутри фулфилмента. Ничто иное раскладка и «назад» писать не
# должны: приход (inbound_intake), отгрузки, списания, инвентаризация — запрет R14.
RELOCATION_MOVEMENT_TYPES = frozenset(
    {
        "warehouse_map_move",
        "stock_transfer_out",
        "stock_transfer_in",
        "container_reattach",
    }
)

UNDO_PATH = "/warehouses/{warehouse_id}/sorting-objects/undo"


@dataclass
class SortingDoc:
    request_id: uuid.UUID
    boxes: dict[str, uuid.UUID] = field(default_factory=dict)
    cargo_places: dict[str, uuid.UUID] = field(default_factory=dict)
    pallets: dict[str, uuid.UUID] = field(default_factory=dict)
    products: dict[str, uuid.UUID] = field(default_factory=dict)


@dataclass
class World:
    client: AsyncClient
    headers: dict[str, str]
    other_headers: dict[str, str]
    tenant_id: uuid.UUID
    actor_id: uuid.UUID
    other_actor_id: uuid.UUID
    warehouse_id: uuid.UUID
    sorting_id: uuid.UUID
    cells: dict[str, uuid.UUID]
    t1: uuid.UUID
    t2: uuid.UUID
    t3: uuid.UUID
    t4: uuid.UUID
    t1_barcode: str
    t2_barcode: str
    t3_barcode: str
    a: SortingDoc
    b: SortingDoc
    c: SortingDoc

    @property
    def product_ids(self) -> list[uuid.UUID]:
        return [self.t1, self.t2, self.t3, self.t4]


async def _register(client: AsyncClient) -> tuple[dict[str, str], uuid.UUID, uuid.UUID]:
    suffix = f"wms650-{time.time_ns()}-{uuid.uuid4().hex[:6]}"
    response = await client.post(
        "/auth/register",
        json={
            "organization_name": "WMS-650 раскладка",
            "slug": suffix,
            "admin_email": f"{suffix}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    payload = decode_access_token(token)
    return (
        {"Authorization": f"Bearer {token}"},
        uuid.UUID(str(payload["tenant_id"])),
        uuid.UUID(str(payload["sub"])),
    )


async def _receive_document(
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    seller_id: uuid.UUID,
    loose: dict[uuid.UUID, int],
    boxes: list[tuple[str, dict[uuid.UUID, int]]],
    cargo_places: list[tuple[str, dict[uuid.UUID, int]]] = (),  # type: ignore[assignment]
) -> SortingDoc:
    """Провести приёмку настоящими сервисами до статуса «сортировка»."""
    products: set[uuid.UUID] = set(loose)
    for _name, content in [*boxes, *cargo_places]:
        products.update(content)
    async with SessionLocal() as session:
        req = await intake.create_request(
            session, tenant_id, warehouse_id=warehouse_id, seller_id=seller_id
        )
        request_id = req.id
    async with SessionLocal() as session:
        for product_id in sorted(products, key=str):
            total = loose.get(product_id, 0) + sum(
                content.get(product_id, 0) for _n, content in [*boxes, *cargo_places]
            )
            await intake.add_line(
                session, tenant_id, request_id, product_id=product_id, expected_qty=total
            )
        await intake.patch_request_draft(
            session,
            tenant_id,
            request_id,
            planned_box_count=len(boxes),
            planned_box_count_set=True,
        )
        await intake.submit_request(session, tenant_id, request_id)
        await intake.begin_receiving(session, tenant_id, request_id, actor_user_id=actor_id)
    async with SessionLocal() as session:
        loaded = await intake.get_request(session, tenant_id, request_id)
        assert loaded is not None
        for line in loaded.lines:
            await intake.set_line_actual_qty(
                session,
                tenant_id,
                request_id,
                line.id,
                actual_qty=loose.get(line.product_id, 0),
            )
    doc = SortingDoc(request_id=request_id, products={})
    async with SessionLocal() as session:
        loaded = await intake.get_request(session, tenant_id, request_id)
        assert loaded is not None
        if boxes:
            created = await box_svc.create_boxes_for_request(
                session, tenant_id, loaded, box_count=len(boxes)
            )
            for (name, content), box in zip(boxes, created, strict=True):
                doc.boxes[name] = box.id
                for product_id, qty in content.items():
                    session.add(
                        InboundIntakeBoxLine(box_id=box.id, product_id=product_id, quantity=qty)
                    )
            await session.commit()
    if cargo_places:
        async with SessionLocal() as session:
            places = await intake.create_cargo_places(
                session, tenant_id, request_id, quantity=len(cargo_places)
            )
            for (name, content), place in zip(cargo_places, places, strict=True):
                doc.cargo_places[name] = place.id
                for product_id, qty in content.items():
                    session.add(
                        InboundIntakeCargoPlaceLine(
                            tenant_id=tenant_id,
                            cargo_place_id=place.id,
                            product_id=product_id,
                            quantity=qty,
                        )
                    )
            await session.commit()
    async with SessionLocal() as session:
        loaded = await intake.get_request(session, tenant_id, request_id)
        assert loaded is not None
        await intake.sync_request_actuals_from_boxes(session, loaded)
        done = await intake.complete_receiving(
            session, tenant_id, request_id, actor_user_id=actor_id
        )
        assert done.status == intake.STATUS_SORTING, done.status
    return doc


async def seed_world(client: AsyncClient) -> World:
    headers, tenant_id, actor_id = await _register(client)
    suffix = uuid.uuid4().hex[:8]
    async with SessionLocal() as session:
        warehouse = await create_warehouse(
            session, tenant_id, name="Склад WMS-650", code=f"wms650-{suffix}"
        )
        warehouse_id = warehouse.id
        cells: dict[str, uuid.UUID] = {}
        for code in ("А 1.1", "А 1.2", "Б 1.1"):
            cells[code] = (await create_location(session, tenant_id, warehouse_id, code=code)).id
    async with SessionLocal() as session:
        from app.models.seller import Seller

        seller = Seller(tenant_id=tenant_id, name="ИП Раскладка")
        other_seller = Seller(tenant_id=tenant_id, name="ООО Чужой селлер")
        session.add_all([seller, other_seller])
        await session.commit()
        seller_id, other_seller_id = seller.id, other_seller.id
    barcodes = {key: f"WMS650-{key}-{suffix}" for key in ("T1", "T2", "T3", "T4")}
    names = {
        "T1": "Носки спортивные, 3 пары",
        "T2": "Ремень кожаный, 110 см",
        "T3": LONG_T3_NAME,
        "T4": "Товар другого селлера",
    }
    product_ids: dict[str, uuid.UUID] = {}
    async with SessionLocal() as session:
        for key in ("T1", "T2", "T3", "T4"):
            product = await create_product(
                session,
                tenant_id,
                name=names[key],
                sku_code=f"SKU-{key}-{suffix}",
                length_mm=100,
                width_mm=100,
                height_mm=100,
                seller_id=other_seller_id if key == "T4" else seller_id,
                wb_barcode=barcodes[key],
            )
            product_ids[key] = product.id
        # Лимит оператора по Т1 — величина, которую раскладка трогать не должна.
        t1_product = await session.get(Product, product_ids["T1"])
        assert t1_product is not None
        t1_product.fbs_stock_limit = 4
        other = User(
            tenant_id=tenant_id,
            email=f"wms650-other-{suffix}@example.com",
            full_name="Другой сотрудник WMS-650",
            password_hash="test-no-login",
            role="fulfillment_admin",
        )
        session.add(other)
        await session.commit()
        other_actor_id = other.id
    other_headers = {
        "Authorization": "Bearer "
        + create_access_token(user_id=other_actor_id, tenant_id=tenant_id, role="fulfillment_admin")
    }
    t1, t2, t3, t4 = (product_ids[key] for key in ("T1", "T2", "T3", "T4"))
    a = await _receive_document(
        tenant_id=tenant_id,
        actor_id=actor_id,
        warehouse_id=warehouse_id,
        seller_id=seller_id,
        loose={t1: 2, t3: 10},
        boxes=[("К1", {t1: 3}), ("К2", {t1: 2}), ("К3", {t2: 4})],
        cargo_places=[("Г1", {t2: 2})],
    )
    a.products = {"T1": t1, "T2": t2, "T3": t3}
    async with SessionLocal() as session:
        pallet = await warehouse_map.create_sorting_object(
            session, tenant_id, warehouse_id, kind="pallet", inbound_request_id=a.request_id
        )
        a.pallets["П1"] = uuid.UUID(str(pallet["id"]))
    b = await _receive_document(
        tenant_id=tenant_id,
        actor_id=actor_id,
        warehouse_id=warehouse_id,
        seller_id=seller_id,
        loose={t1: 3},
        boxes=[("КБ1", {t1: 2})],
    )
    b.products = {"T1": t1}
    c = await _receive_document(
        tenant_id=tenant_id,
        actor_id=actor_id,
        warehouse_id=warehouse_id,
        seller_id=other_seller_id,
        loose={},
        boxes=[("КЦ1", {t4: 2})],
    )
    c.products = {"T4": t4}
    async with SessionLocal() as session:
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
        sorting_id = sorting.id
        await session.commit()
    return World(
        client=client,
        headers=headers,
        other_headers=other_headers,
        tenant_id=tenant_id,
        actor_id=actor_id,
        other_actor_id=other_actor_id,
        warehouse_id=warehouse_id,
        sorting_id=sorting_id,
        cells=cells,
        t1=t1,
        t2=t2,
        t3=t3,
        t4=t4,
        t1_barcode=barcodes["T1"],
        t2_barcode=barcodes["T2"],
        t3_barcode=barcodes["T3"],
        a=a,
        b=b,
        c=c,
    )


# ── HTTP-действия экрана ────────────────────────────────────────────────────


def _doc(world: World, doc: SortingDoc | None) -> SortingDoc:
    return world.a if doc is None else doc


async def place(
    world: World,
    *,
    kind: str,
    object_id: uuid.UUID,
    cell: str | None = None,
    to_id: uuid.UUID | None = None,
    qty: int | None = None,
    op: uuid.UUID | None = None,
    doc: SortingDoc | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    """«+»/перетаскивание/скан тары/«Снять»/«Вынуть» — та же ручка, что у экрана."""
    body: dict[str, Any] = {
        "kind": kind,
        "id": str(object_id),
        "inbound_request_id": str(_doc(world, doc).request_id),
        "operation_id": str(op or uuid.uuid4()),
        "cell_id": str(world.cells[cell]) if cell else None,
        "to_id": str(to_id) if to_id else None,
    }
    if qty is not None:
        body["qty"] = qty
    return await world.client.post(
        f"/warehouses/{world.warehouse_id}/sorting-objects/place",
        headers=headers or world.headers,
        json=body,
    )


async def scan(
    world: World,
    *,
    barcode: str,
    cell: str,
    to_id: uuid.UUID | None = None,
    op: uuid.UUID | None = None,
    doc: SortingDoc | None = None,
) -> Response:
    return await world.client.post(
        f"/warehouses/{world.warehouse_id}/sorting-objects/scan",
        headers=world.headers,
        json={
            "inbound_request_id": str(_doc(world, doc).request_id),
            "operation_id": str(op or uuid.uuid4()),
            "barcode": barcode,
            "cell_id": str(world.cells[cell]),
            "to_id": str(to_id) if to_id else None,
        },
    )


async def undo(
    world: World,
    target_op: uuid.UUID,
    *,
    op: uuid.UUID | None = None,
    doc: SortingDoc | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    return await world.client.post(
        UNDO_PATH.format(warehouse_id=world.warehouse_id),
        headers=headers or world.headers,
        json={
            "inbound_request_id": str(_doc(world, doc).request_id),
            "operation_id": str(op or uuid.uuid4()),
            "target_operation_id": str(target_op),
        },
    )


async def map_move(
    world: World,
    *,
    kind: str,
    object_id: uuid.UUID,
    to_kind: str,
    to_id: uuid.UUID | None = None,
    qty: int | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    """Перенос в разделе «Ячейки» — общий путь, не ручка экрана раскладки."""
    body: dict[str, Any] = {"kind": kind, "id": str(object_id), "to_kind": to_kind}
    if to_id is not None:
        body["to_id"] = str(to_id)
    if qty is not None:
        body["qty"] = qty
    return await world.client.post(
        f"/warehouses/{world.warehouse_id}/map/move",
        headers=headers or world.headers,
        json=body,
    )


def ok(response: Response, what: str) -> dict[str, Any]:
    assert response.status_code == 200, f"{what}: {response.status_code} {response.text}"
    body = response.json()
    assert isinstance(body, dict)
    return body


async def view(world: World, doc: SortingDoc | None = None) -> dict[str, Any]:
    response = await world.client.get(
        f"/warehouses/{world.warehouse_id}/sorting-objects",
        headers=world.headers,
        params={"inbound_request_id": str(_doc(world, doc).request_id)},
    )
    return ok(response, "GET sorting-objects")


def normalized_view(data: dict[str, Any]) -> dict[str, Any]:
    """Экранный состав без технических id строк остатка: что, где и сколько."""
    objects = sorted((row["id"], row["kind"], row["holder"] or "") for row in data["objects"])
    lines: dict[tuple[str, str], int] = {}
    for row in data["lines"]:
        key = (row["productId"], row["holder"] or "")
        lines[key] = lines.get(key, 0) + int(row["qty"])
    return {
        "objects": objects,
        "lines": sorted((k[0], k[1], v) for k, v in lines.items() if v),
    }


def unplaced_object_ids(data: dict[str, Any]) -> set[str]:
    """Тара в основном списке экрана: держатель — не ячейка (через цепочку)."""
    by_id = {row["id"]: row for row in data["objects"]}

    def on_cell(holder: str | None) -> bool:
        seen = 0
        while holder and holder.startswith("obj:") and seen < 20:
            parent = by_id.get(holder[4:])
            holder = parent["holder"] if parent else None
            seen += 1
        return bool(holder and holder.startswith("cell:"))

    return {row["id"] for row in data["objects"] if not on_cell(row["holder"])}


def holder_of(data: dict[str, Any], object_id: uuid.UUID) -> str | None:
    for row in data["objects"]:
        if row["id"] == str(object_id):
            holder = row["holder"]
            return None if holder is None else str(holder)
    raise AssertionError(f"объект {object_id} не виден в составе документа")


def cell_ids_holding(data: dict[str, Any], object_id: uuid.UUID) -> list[str]:
    return [
        cell["id"]
        for cell in data["cells"]
        if any(row["id"] == str(object_id) for row in cell["objects"])
    ]


# ── Снимки состояния ────────────────────────────────────────────────────────


async def balance_id(
    world: World,
    *,
    product_id: uuid.UUID,
    location_id: uuid.UUID,
    container_id: uuid.UUID | None,
) -> uuid.UUID:
    async with SessionLocal() as session:
        row = await session.scalar(
            select(InventoryBalance.id).where(
                InventoryBalance.tenant_id == world.tenant_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.storage_location_id == location_id,
                InventoryBalance.container_id.is_(None)
                if container_id is None
                else InventoryBalance.container_id == container_id,
                InventoryBalance.quantity > 0,
            )
        )
    assert row is not None, (product_id, location_id, container_id)
    return row


async def posted(world: World, doc: SortingDoc | None = None) -> dict[uuid.UUID, int]:
    async with SessionLocal() as session:
        rows = await session.execute(
            select(InboundIntakeLine.product_id, InboundIntakeLine.posted_qty).where(
                InboundIntakeLine.request_id == _doc(world, doc).request_id
            )
        )
        return {product_id: int(qty) for product_id, qty in rows}


async def accepted(world: World, doc: SortingDoc | None = None) -> dict[uuid.UUID, int]:
    async with SessionLocal() as session:
        rows = await session.execute(
            select(InboundIntakeLine.product_id, InboundIntakeLine.actual_qty).where(
                InboundIntakeLine.request_id == _doc(world, doc).request_id
            )
        )
        return {product_id: int(qty or 0) for product_id, qty in rows}


async def remaining_total(world: World, doc: SortingDoc | None = None) -> int:
    got_posted = await posted(world, doc)
    got_accepted = await accepted(world, doc)
    return sum(max(0, got_accepted[key] - got_posted.get(key, 0)) for key in got_accepted)


async def request_status(world: World, doc: SortingDoc | None = None) -> str:
    async with SessionLocal() as session:
        req = await session.get(InboundIntakeRequest, _doc(world, doc).request_id)
        assert req is not None
        return str(req.status)


async def document_state(world: World, doc: SortingDoc | None = None) -> dict[str, Any]:
    """«Разложено» документа, его тары и где стоит каждая тара."""
    the_doc = _doc(world, doc)
    async with SessionLocal() as session:
        box_lines = await session.execute(
            select(InboundIntakeBoxLine.box_id, InboundIntakeBoxLine.product_id,
                   InboundIntakeBoxLine.posted_qty)
            .join(InboundIntakeBox, InboundIntakeBox.id == InboundIntakeBoxLine.box_id)
            .where(InboundIntakeBox.request_id == the_doc.request_id)
        )
        cargo_lines = await session.execute(
            select(InboundIntakeCargoPlaceLine.cargo_place_id,
                   InboundIntakeCargoPlaceLine.product_id,
                   InboundIntakeCargoPlaceLine.posted_qty)
            .join(InboundIntakeCargoPlace,
                  InboundIntakeCargoPlace.id == InboundIntakeCargoPlaceLine.cargo_place_id)
            .where(InboundIntakeCargoPlace.request_id == the_doc.request_id)
        )
        boxes = await session.execute(
            select(InboundIntakeBox.id, InboundIntakeBox.storage_location_id,
                   InboundIntakeBox.pallet_id)
            .where(InboundIntakeBox.request_id == the_doc.request_id)
        )
        cargos = await session.execute(
            select(InboundIntakeCargoPlace.id, InboundIntakeCargoPlace.storage_location_id,
                   InboundIntakeCargoPlace.pallet_id)
            .where(InboundIntakeCargoPlace.request_id == the_doc.request_id)
        )
        pallets = await session.execute(
            select(Pallet.id, Pallet.storage_location_id)
            .where(Pallet.inbound_request_id == the_doc.request_id)
        )
        generic = await session.execute(
            select(WarehouseBox.id, WarehouseBox.storage_location_id, WarehouseBox.pallet_id)
            .where(WarehouseBox.inbound_request_id == the_doc.request_id)
        )
        req = await session.get(InboundIntakeRequest, the_doc.request_id)
        assert req is not None
        status = req.status
    return {
        "status": status,
        "posted": sorted((str(k), v) for k, v in (await posted(world, the_doc)).items()),
        "box_posted": sorted((str(a), str(b), int(c)) for a, b, c in box_lines),
        "cargo_posted": sorted((str(a), str(b), int(c)) for a, b, c in cargo_lines),
        "boxes": sorted((str(a), str(b), str(c)) for a, b, c in boxes),
        "cargo_places": sorted((str(a), str(b), str(c)) for a, b, c in cargos),
        "pallets": sorted((str(a), str(b)) for a, b in pallets),
        "generic": sorted((str(a), str(b), str(c)) for a, b, c in generic),
    }


async def placement(world: World) -> dict[tuple[str, str, str, str], int]:
    """Расположение каждой штуки: (место, вид тары, тара, товар) → штук."""
    async with SessionLocal() as session:
        rows = await session.execute(
            select(
                InventoryBalance.storage_location_id,
                InventoryBalance.container_kind,
                InventoryBalance.container_id,
                InventoryBalance.product_id,
                func.sum(InventoryBalance.quantity),
            )
            .where(InventoryBalance.tenant_id == world.tenant_id)
            .group_by(
                InventoryBalance.storage_location_id,
                InventoryBalance.container_kind,
                InventoryBalance.container_id,
                InventoryBalance.product_id,
            )
        )
        return {
            (str(loc), str(kind), str(cid), str(pid)): int(qty)
            for loc, kind, cid, pid, qty in rows
            if qty
        }


async def full_snapshot(world: World) -> dict[str, Any]:
    """Снимок для «назад»: расположение, прогресс и состав всех трёх документов."""
    return {
        "placement": await placement(world),
        "a": await document_state(world, world.a),
        "b": await document_state(world, world.b),
        "c": await document_state(world, world.c),
        "view_a": normalized_view(await view(world, world.a)),
        "view_b": normalized_view(await view(world, world.b)),
        "view_c": normalized_view(await view(world, world.c)),
    }


async def movement_count(world: World) -> int:
    async with SessionLocal() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(InventoryMovement)
                .where(InventoryMovement.tenant_id == world.tenant_id)
            )
            or 0
        )


async def movement_ids(world: World) -> set[uuid.UUID]:
    async with SessionLocal() as session:
        return set(
            (
                await session.scalars(
                    select(InventoryMovement.id).where(
                        InventoryMovement.tenant_id == world.tenant_id
                    )
                )
            ).all()
        )


async def movements_except(world: World, before: set[uuid.UUID]) -> list[InventoryMovement]:
    async with SessionLocal() as session:
        rows = list(
            (
                await session.scalars(
                    select(InventoryMovement).where(
                        InventoryMovement.tenant_id == world.tenant_id
                    )
                )
            ).all()
        )
    return [row for row in rows if row.id not in before]


async def stock_snapshot(world: World) -> dict[str, Any]:
    """Остаток и всё, что от него зависит (R14). Расположение сюда не входит."""
    async with SessionLocal() as session:
        totals = {
            str(pid): int(qty)
            for pid, qty in await session.execute(
                select(InventoryBalance.product_id, func.sum(InventoryBalance.quantity))
                .where(InventoryBalance.tenant_id == world.tenant_id)
                .group_by(InventoryBalance.product_id)
            )
        }
        fbs_reserved = {
            str(pid): int(qty)
            for pid, qty in await session.execute(
                select(FbsOrderReservation.product_id, func.sum(FbsOrderReservation.quantity))
                .group_by(FbsOrderReservation.product_id)
                .where(FbsOrderReservation.product_id.in_(world.product_ids))
            )
        }
        outbound_reserved = {
            str(pid): int(qty)
            for pid, qty in await session.execute(
                select(InventoryReservation.product_id, func.sum(InventoryReservation.quantity))
                .where(InventoryReservation.tenant_id == world.tenant_id)
                .group_by(InventoryReservation.product_id)
            )
        }
        fbo_reserved = {
            str(pid): int(qty)
            for pid, qty in await session.execute(
                select(
                    MarketplaceUnloadReservation.product_id,
                    func.sum(MarketplaceUnloadReservation.quantity),
                )
                .where(MarketplaceUnloadReservation.tenant_id == world.tenant_id)
                .group_by(MarketplaceUnloadReservation.product_id)
            )
        }
        breakdown = await fbs_stock_breakdown_by_product(
            session, world.tenant_id, world.warehouse_id, world.product_ids
        )
        pools = sorted(
            (str(pid), int(qty))
            for pid, qty in await session.execute(
                select(FbsBindingStockPool.product_id, FbsBindingStockPool.quantity).where(
                    FbsBindingStockPool.tenant_id == world.tenant_id
                )
            )
        )
        limits = {
            str(pid): limit
            for pid, limit in await session.execute(
                select(Product.id, Product.fbs_stock_limit).where(
                    Product.id.in_(world.product_ids)
                )
            )
        }
    return {
        "total": totals,
        "fbs_reserved": fbs_reserved,
        "outbound_reserved": outbound_reserved,
        "fbo_reserved": fbo_reserved,
        "fbs_breakdown": {
            str(pid): (row.on_hand, row.reserved, row.free) for pid, row in breakdown.items()
        },
        "pools": pools,
        "limits": limits,
    }


def assert_only_relocations(moves: list[InventoryMovement], rule: str) -> None:
    """R14: только перемещения, сумма по каждому товару — ноль."""
    kinds = {row.movement_type for row in moves}
    assert kinds <= RELOCATION_MOVEMENT_TYPES, (
        f"{rule}: появились движения не-перемещения {sorted(kinds - RELOCATION_MOVEMENT_TYPES)}"
    )
    net: dict[uuid.UUID, int] = {}
    for row in moves:
        net[row.product_id] = net.get(row.product_id, 0) + int(row.quantity_delta)
    assert all(value == 0 for value in net.values()), f"{rule}: перемещения не сходятся {net}"


async def billing_snapshot(world: World, doc: SortingDoc | None = None) -> dict[str, Any]:
    """Начисление за приёмку (или запись о невозможности начислить) по документу."""
    async with SessionLocal() as session:
        entries = await session.execute(
            select(BillingLedgerEntry.id, BillingLedgerEntry.entry_type,
                   BillingLedgerEntry.quantity).where(
                BillingLedgerEntry.tenant_id == world.tenant_id,
                BillingLedgerEntry.source_id == _doc(world, doc).request_id,
            )
        )
        issues = await session.scalar(
            select(func.count()).select_from(BillingRunIssue).where(
                BillingRunIssue.tenant_id == world.tenant_id
            )
        )
        return {
            "entries": sorted((str(a), str(b), str(c)) for a, b, c in entries),
            "issues": int(issues or 0),
        }


# ── Виды действий раскладки (C12 а-ж, C18) ──────────────────────────────────
#
# Каждый вид — подготовка (что уже сделано до действия) и само действие с
# идентификатором операции, как его отправляет экран.


async def put_k1_on_a12(world: World) -> None:
    ok(await place(world, kind="box", object_id=world.a.boxes["К1"], cell="А 1.2"), "К1 → А 1.2")


async def put_k2_on_a11(world: World) -> None:
    ok(await place(world, kind="box", object_id=world.a.boxes["К2"], cell="А 1.1"), "К2 → А 1.1")


async def _no_setup(world: World) -> None:
    return None


async def _setup_k1_k2_on_cells(world: World) -> None:
    await put_k1_on_a12(world)
    await put_k2_on_a11(world)


async def _act_place_k2_by_scan(world: World, op: uuid.UUID) -> Response:
    # Скан тары при открытой ячейке: экран шлёт постановку с operation_id скана.
    return await place(world, kind="box", object_id=world.a.boxes["К2"], cell="А 1.1", op=op)


async def _act_scan_t1_into_k2(world: World, op: uuid.UUID) -> Response:
    return await scan(world, barcode=world.t1_barcode, cell="А 1.1",
                      to_id=world.a.boxes["К2"], op=op)


async def _act_plus_t3_five(world: World, op: uuid.UUID) -> Response:
    source = await balance_id(world, product_id=world.t3, location_id=world.sorting_id,
                              container_id=None)
    return await place(world, kind="product", object_id=source, cell="А 1.1", qty=5, op=op)


async def _act_plus_g1_on_p1(world: World, op: uuid.UUID) -> Response:
    return await place(world, kind="cargo_place", object_id=world.a.cargo_places["Г1"],
                       to_id=world.a.pallets["П1"], op=op)


async def _act_take_k1_off_cell(world: World, op: uuid.UUID) -> Response:
    # «Снять с ячейки»: та же ручка без ячейки и тары назначения.
    return await place(world, kind="box", object_id=world.a.boxes["К1"], op=op)


async def _act_take_t1_out_of_k2(world: World, op: uuid.UUID) -> Response:
    # «Вынуть из короба»: окно с выбранной «Россыпью», всё количество строки.
    source = await balance_id(world, product_id=world.t1, location_id=world.cells["А 1.1"],
                              container_id=world.a.boxes["К2"])
    return await place(world, kind="product", object_id=source, qty=2, op=op)


async def _act_transfer_k1_to_b11(world: World, op: uuid.UUID) -> Response:
    # Явный перенос: открыта Б 1.1, отсканирован К1, стоящий на А 1.2.
    return await place(world, kind="box", object_id=world.a.boxes["К1"], cell="Б 1.1", op=op)


@dataclass(frozen=True)
class ActionKind:
    key: str
    title: str
    setup: Any
    act: Any


ACTION_KINDS: tuple[ActionKind, ...] = (
    ActionKind("a", "(а) постановка К2 сканом", _no_setup, _act_place_k2_by_scan),
    ActionKind("b", "(б) скан Т1 в открытый К2", _setup_k1_k2_on_cells, _act_scan_t1_into_k2),
    ActionKind("v", "(в) «+» Т3, 5 шт на А 1.1", _no_setup, _act_plus_t3_five),
    ActionKind("g", "(г) «+» Г1 на П1", _no_setup, _act_plus_g1_on_p1),
    ActionKind("d", "(д) «Снять с ячейки» К1", put_k1_on_a12, _act_take_k1_off_cell),
    ActionKind("e", "(е) «Вынуть из короба» Т1 из К2 на ячейке", put_k2_on_a11,
               _act_take_t1_out_of_k2),
    ActionKind("zh", "(ж) явный перенос К1 с А 1.2 на Б 1.1", put_k1_on_a12,
               _act_transfer_k1_to_b11),
)
