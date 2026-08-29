from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeCargoPlace,
    InboundIntakeLine,
    InboundIntakeRequest,
)
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import (
    MOVEMENT_TYPE_INBOUND_INTAKE,
    MOVEMENT_TYPE_OUTBOUND_SHIPMENT,
)
from app.models.pallet import Pallet
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.models.warehouse_box import WarehouseBox
from app.services import (
    inbound_cargo_place_service,
    inbound_intake_box_service,
    inbound_intake_note_service,
    inventory_service,
    pallet_service,
)
from app.services.pallet_service import PalletServiceError
from app.services.sorting_location_service import SORTING_LOCATION_CODE


async def _seed_tenant(
    session: AsyncSession,
    label: str,
) -> tuple[Tenant, Warehouse, StorageLocation, Product]:
    suffix = uuid.uuid4().hex[:10]
    tenant = Tenant(name=f"Арендатор {label}", slug=f"wave1-{label}-{suffix}")
    session.add(tenant)
    await session.flush()
    warehouse = Warehouse(
        tenant_id=tenant.id,
        name=f"Склад {label}",
        code=f"wh-{label}-{suffix}",
        barcode=f"WH-WAVE1-{label}-{suffix}",
    )
    session.add(warehouse)
    await session.flush()
    location = StorageLocation(
        tenant_id=tenant.id,
        warehouse_id=warehouse.id,
        code="A 1.1",
        barcode=f"LOC-WAVE1-{label}-{suffix}",
    )
    product = Product(
        tenant_id=tenant.id,
        name=f"Товар {label}",
        sku_code=f"SKU-{label}-{suffix}",
    )
    session.add_all([location, product])
    await session.flush()
    return tenant, warehouse, location, product


async def _seed_inbound_containers(
    session: AsyncSession,
    tenant: Tenant,
    warehouse: Warehouse,
    product: Product,
    label: str,
) -> tuple[InboundIntakeRequest, InboundIntakeBox, InboundIntakeCargoPlace]:
    request = InboundIntakeRequest(
        tenant_id=tenant.id,
        warehouse_id=warehouse.id,
        status="receiving",
    )
    session.add(request)
    await session.flush()
    session.add(
        InboundIntakeLine(
            request_id=request.id,
            product_id=product.id,
            expected_qty=100,
        )
    )
    box = InboundIntakeBox(
        tenant_id=tenant.id,
        request_id=request.id,
        box_number=1,
        internal_barcode=f"INB-WAVE1-{label}-{uuid.uuid4().hex[:8]}",
    )
    cargo_place = InboundIntakeCargoPlace(
        tenant_id=tenant.id,
        request_id=request.id,
        place_number=1,
        internal_barcode=f"ICG-WAVE1-{label}-{uuid.uuid4().hex[:8]}",
    )
    session.add_all([box, cargo_place])
    await session.flush()
    return request, box, cargo_place


@pytest.mark.asyncio
async def test_tenant_b_cannot_add_product_to_tenant_a_pallet_or_list_it(
    async_client: AsyncClient,
) -> None:
    del async_client
    async with SessionLocal() as session:
        tenant_a, warehouse_a, location_a, _product_a = await _seed_tenant(
            session, "a"
        )
        tenant_b, warehouse_b, _location_b, product_b = await _seed_tenant(
            session, "b"
        )
        _request_b, box_b, _cargo_b = await _seed_inbound_containers(
            session, tenant_b, warehouse_b, product_b, "b"
        )
        await session.commit()
        pallet_a = await pallet_service.create_pallet(
            session,
            tenant_a.id,
            warehouse_id=warehouse_a.id,
            storage_location_id=location_a.id,
        )
        tenant_b_id = tenant_b.id

        with pytest.raises(ValueError, match="container not found"):
            await inventory_service.record_movement_and_adjust_balance(
                session,
                tenant_id=tenant_b.id,
                product_id=product_b.id,
                storage_location_id=_location_b.id,
                quantity_delta=1,
                movement_type=MOVEMENT_TYPE_OUTBOUND_SHIPMENT,
                container_kind="pallet",
                container_id=pallet_a.id,
                actor_user_id=None,
            )

        with pytest.raises(PalletServiceError, match="pallet_not_found"):
            await pallet_service.combine_into_pallet(
                session,
                tenant_b.id,
                pallet_a.id,
                inbound_box_ids=[box_b.id],
            )
        await session.rollback()
        assert await pallet_service.list_pallets(session, tenant_b_id) == []


@pytest.mark.asyncio
async def test_parallel_pallet_creation_reserves_distinct_codes(
    async_client: AsyncClient,
) -> None:
    # TC-NEW-PALLET-CONCURRENT-CODE-001
    # Дано один склад. Когда две транзакции одновременно создают палеты, тогда
    # обе операции успешны, коды различаются и обе строки остаются в базе.
    del async_client
    async with SessionLocal() as seed_session:
        tenant, warehouse, _location, _product = await _seed_tenant(
            seed_session, "parallel-pallet"
        )
        await seed_session.commit()
        tenant_id = tenant.id
        warehouse_id = warehouse.id

    async def create_one() -> tuple[uuid.UUID, str]:
        async with SessionLocal() as session:
            pallet = await pallet_service.create_pallet(
                session,
                tenant_id,
                warehouse_id=warehouse_id,
            )
            return pallet.id, pallet.code

    created = await asyncio.gather(create_one(), create_one())

    ids = {pallet_id for pallet_id, _code in created}
    codes = {code for _pallet_id, code in created}
    assert len(ids) == 2
    assert len(codes) == 2
    async with SessionLocal() as verify_session:
        persisted = await pallet_service.list_pallets(
            verify_session,
            tenant_id,
            warehouse_id=warehouse_id,
        )
    assert {pallet.id for pallet in persisted} == ids
    assert {pallet.code for pallet in persisted} == codes


@pytest.mark.asyncio
async def test_pallet_counter_continues_after_existing_legacy_code(
    async_client: AsyncClient,
) -> None:
    # TC-NEW-PALLET-CONCURRENT-CODE-002
    # Ограничение: включение атомарного счётчика не переиспользует старые номера.
    del async_client
    async with SessionLocal() as session:
        tenant, warehouse, _location, _product = await _seed_tenant(
            session, "legacy-pallet"
        )
        session.add(
            Pallet(
                tenant_id=tenant.id,
                warehouse_id=warehouse.id,
                code="П-000005",
                barcode=f"PLT-LEGACY-{uuid.uuid4().hex[:8]}",
            )
        )
        await session.commit()

        created = await pallet_service.create_pallet(
            session,
            tenant.id,
            warehouse_id=warehouse.id,
        )

    assert created.code == "П-000006"


@pytest.mark.asyncio
async def test_same_product_same_cell_in_two_boxes_keeps_both_balance_rows(
    async_client: AsyncClient,
) -> None:
    del async_client
    async with SessionLocal() as session:
        tenant, warehouse, location, product = await _seed_tenant(session, "boxes")
        _request, box_one, cargo = await _seed_inbound_containers(
            session, tenant, warehouse, product, "boxes"
        )
        box_two = InboundIntakeBox(
            tenant_id=tenant.id,
            request_id=box_one.request_id,
            box_number=2,
            internal_barcode=f"INB-WAVE1-BOX2-{uuid.uuid4().hex[:8]}",
        )
        session.add(box_two)
        await session.flush()
        session.add_all(
            [
                InventoryBalance(
                    tenant_id=tenant.id,
                    storage_location_id=location.id,
                    product_id=product.id,
                    container_kind="box",
                    container_id=box_one.id,
                    quantity=5,
                    quantity_unpacked=5,
                    quantity_packed=0,
                ),
                InventoryBalance(
                    tenant_id=tenant.id,
                    storage_location_id=location.id,
                    product_id=product.id,
                    container_kind="box",
                    container_id=box_two.id,
                    quantity=7,
                    quantity_unpacked=3,
                    quantity_packed=4,
                ),
            ]
        )
        await session.commit()
        del cargo

        rows = list(
            (
                await session.execute(
                    select(InventoryBalance).where(
                        InventoryBalance.tenant_id == tenant.id,
                        InventoryBalance.product_id == product.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert {(row.container_id, row.quantity) for row in rows} == {
            (box_one.id, 5),
            (box_two.id, 7),
        }


@pytest.mark.asyncio
async def test_duplicate_loose_product_balance_in_one_cell_is_rejected(
    async_client: AsyncClient,
) -> None:
    del async_client
    async with SessionLocal() as session:
        tenant, _warehouse, location, product = await _seed_tenant(session, "loose")
        session.add(
            InventoryBalance(
                tenant_id=tenant.id,
                storage_location_id=location.id,
                product_id=product.id,
                quantity=4,
                quantity_unpacked=4,
                quantity_packed=0,
            )
        )
        await session.commit()
        tenant_id = tenant.id
        product_id = product.id
        location_id = location.id
        session.add(
            InventoryBalance(
                tenant_id=tenant.id,
                storage_location_id=location.id,
                product_id=product.id,
                quantity=6,
                quantity_unpacked=6,
                quantity_packed=0,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
        count = await session.scalar(
            select(func.count(InventoryBalance.id)).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.storage_location_id == location_id,
            )
        )
        assert count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("container_kind", "container_id"),
    [("box", None), (None, uuid.uuid4())],
)
async def test_container_reference_requires_kind_and_id_together(
    async_client: AsyncClient,
    container_kind: str | None,
    container_id: uuid.UUID | None,
) -> None:
    del async_client
    async with SessionLocal() as session:
        tenant, _warehouse, location, product = await _seed_tenant(session, "pair")
        session.add(
            InventoryBalance(
                tenant_id=tenant.id,
                storage_location_id=location.id,
                product_id=product.id,
                container_kind=container_kind,
                container_id=container_id,
                quantity=1,
                quantity_unpacked=1,
                quantity_packed=0,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_service_refuses_to_take_stock_below_zero(async_client: AsyncClient) -> None:
    """Обычное списание в минус не пускает.

    Запрет переехал из базы в сервис по решению владельца: проверка в базе не
    умеет спрашивать, кто её вызвал, а ровно одному пути минус нужен — см.
    соседний тест про подтверждённую доставку FBS. Здесь проверяется, что для
    всех остальных путей защита осталась.
    """
    del async_client
    async with SessionLocal() as session:
        tenant, _warehouse, location, product = await _seed_tenant(session, "negative")
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant.id,
            product_id=product.id,
            storage_location_id=location.id,
            quantity_delta=5,
            movement_type=MOVEMENT_TYPE_INBOUND_INTAKE,
            actor_user_id=None,
        )
        await session.commit()
        with pytest.raises(ValueError, match="insufficient stock"):
            await inventory_service.record_movement_and_adjust_balance(
                session,
                tenant_id=tenant.id,
                product_id=product.id,
                storage_location_id=location.id,
                quantity_delta=-6,
                movement_type=MOVEMENT_TYPE_OUTBOUND_SHIPMENT,
                actor_user_id=None,
            )


@pytest.mark.asyncio
async def test_confirmed_fbs_delivery_is_allowed_to_go_negative(
    async_client: AsyncClient,
) -> None:
    """Подтверждённая доставка FBS списывает даже то, чего по учёту нет.

    Маркетплейс сказал, что товар уехал — значит на складе его нет, что бы ни
    думал учёт. Отказ подвесил бы поставку навсегда и оставил призрачный
    остаток; минус здесь — видимый след расхождения.
    """
    del async_client
    async with SessionLocal() as session:
        tenant, _warehouse, location, product = await _seed_tenant(session, "fbs-negative")
        await inventory_service.apply_fbs_supply_write_off(
            session,
            tenant_id=tenant.id,
            product_id=product.id,
            storage_location_id=location.id,
            quantity=3,
            actor_user_id=None,
        )
        await session.commit()
        balance = (
            await session.execute(
                select(InventoryBalance).where(
                    InventoryBalance.tenant_id == tenant.id,
                    InventoryBalance.product_id == product.id,
                    InventoryBalance.storage_location_id == location.id,
                )
            )
        ).scalar_one()
        assert balance.quantity == -3


@pytest.mark.asyncio
async def test_two_concurrent_deductions_of_30_from_40_write_off_only_30(
    async_client: AsyncClient,
) -> None:
    del async_client
    async with SessionLocal() as seed_session:
        tenant, _warehouse, location, product = await _seed_tenant(
            seed_session, "concurrent"
        )
        seed_session.add(
            InventoryBalance(
                tenant_id=tenant.id,
                storage_location_id=location.id,
                product_id=product.id,
                quantity=40,
                quantity_unpacked=40,
                quantity_packed=0,
            )
        )
        await seed_session.commit()
        tenant_id = tenant.id
        location_id = location.id
        product_id = product.id

    start = asyncio.Event()
    ready = 0
    ready_lock = asyncio.Lock()

    async def deduct() -> str:
        nonlocal ready
        async with SessionLocal() as session:
            async with ready_lock:
                ready += 1
                if ready == 2:
                    start.set()
            await start.wait()
            try:
                await inventory_service.record_movement_and_adjust_balance(
                    session,
                    tenant_id=tenant_id,
                    product_id=product_id,
                    storage_location_id=location_id,
                    quantity_delta=-30,
                    movement_type=MOVEMENT_TYPE_OUTBOUND_SHIPMENT,
                    actor_user_id=None,
                )
                await session.commit()
            except ValueError as exc:
                await session.rollback()
                return str(exc)
            return "ok"

    results = await asyncio.gather(deduct(), deduct())
    assert sorted(results) == ["insufficient stock", "ok"]
    async with SessionLocal() as verify_session:
        balance = (
            await verify_session.execute(
                select(InventoryBalance).where(
                    InventoryBalance.tenant_id == tenant_id,
                    InventoryBalance.product_id == product_id,
                    InventoryBalance.storage_location_id == location_id,
                )
            )
        ).scalar_one()
        assert balance.quantity == 10
        assert balance.quantity_unpacked == 10


@pytest.mark.asyncio
async def test_combine_and_disband_pallet_moves_contents_to_sorting_without_loss(
    async_client: AsyncClient,
) -> None:
    del async_client
    async with SessionLocal() as session:
        tenant, warehouse, location, product = await _seed_tenant(session, "pallet")
        _request, box, cargo = await _seed_inbound_containers(
            session, tenant, warehouse, product, "pallet"
        )
        session.add_all(
            [
                InventoryBalance(
                    tenant_id=tenant.id,
                    storage_location_id=location.id,
                    product_id=product.id,
                    container_kind="box",
                    container_id=box.id,
                    quantity=11,
                    quantity_unpacked=7,
                    quantity_packed=4,
                ),
                InventoryBalance(
                    tenant_id=tenant.id,
                    storage_location_id=location.id,
                    product_id=product.id,
                    container_kind="cargo_place",
                    container_id=cargo.id,
                    quantity=13,
                    quantity_unpacked=13,
                    quantity_packed=0,
                ),
            ]
        )
        await session.commit()
        pallet = await pallet_service.create_pallet(
            session,
            tenant.id,
            warehouse_id=warehouse.id,
            storage_location_id=location.id,
        )
        await pallet_service.combine_into_pallet(
            session,
            tenant.id,
            pallet.id,
            inbound_box_ids=[box.id],
            cargo_place_ids=[cargo.id],
        )
        await session.refresh(box)
        await session.refresh(cargo)
        assert box.pallet_id == cargo.pallet_id == pallet.id

        disbanded = await pallet_service.disband_pallet(session, tenant.id, pallet.id)
        await session.refresh(box)
        await session.refresh(cargo)
        assert disbanded.disbanded_at is not None
        assert disbanded.storage_location_id is None
        assert box.pallet_id is None
        assert cargo.pallet_id is None
        sorting_id = await session.scalar(
            select(StorageLocation.id).where(
                StorageLocation.tenant_id == tenant.id,
                StorageLocation.warehouse_id == warehouse.id,
                StorageLocation.code == SORTING_LOCATION_CODE,
            )
        )
        balances = list(
            (
                await session.execute(
                    select(InventoryBalance).where(
                        InventoryBalance.tenant_id == tenant.id,
                        InventoryBalance.product_id == product.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert sorting_id is not None
        assert {row.storage_location_id for row in balances} == {sorting_id}
        assert sum(row.quantity for row in balances) == 24
        assert sum(row.quantity_unpacked for row in balances) == 20
        assert sum(row.quantity_packed for row in balances) == 4


@pytest.mark.asyncio
async def test_warehouse_cargo_place_is_not_accepted_as_warehouse_box(
    async_client: AsyncClient,
) -> None:
    del async_client
    async with SessionLocal() as session:
        tenant, warehouse, location, _product = await _seed_tenant(
            session, "warehouse-cargo-kind"
        )
        cargo_place = WarehouseBox(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            internal_barcode=f"WHB-CARGO-{uuid.uuid4().hex[:8]}",
            container_kind="cargo_place",
        )
        session.add(cargo_place)
        await session.commit()
        pallet = await pallet_service.create_pallet(
            session,
            tenant.id,
            warehouse_id=warehouse.id,
            storage_location_id=location.id,
        )

        # Негатив: warehouse_box_ids — старый коробочный вход. Грузоместо в
        # палету кладётся отдельным типизированным путём, а не маскируется коробом.
        with pytest.raises(PalletServiceError, match="box_not_found"):
            await pallet_service.combine_into_pallet(
                session,
                tenant.id,
                pallet.id,
                warehouse_box_ids=[cargo_place.id],
            )


async def _register_admin(async_client: AsyncClient) -> tuple[dict[str, str], uuid.UUID]:
    suffix = uuid.uuid4().hex[:12]
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Cargo place {suffix}",
            "slug": f"cargo-place-{suffix}",
            "admin_email": f"cargo-place-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    me = await async_client.get("/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    return headers, uuid.UUID(me.json()["tenant_id"])


@pytest.mark.asyncio
async def test_cargo_place_accepts_products_and_returns_its_composition(
    async_client: AsyncClient,
) -> None:
    headers, tenant_id = await _register_admin(async_client)
    async with SessionLocal() as session:
        tenant = await session.get(Tenant, tenant_id)
        assert tenant is not None
        warehouse = Warehouse(
            tenant_id=tenant_id,
            name="Склад грузоместа",
            code=f"cargo-{uuid.uuid4().hex[:8]}",
            barcode=f"WH-CARGO-{uuid.uuid4().hex[:8]}",
        )
        product = Product(
            tenant_id=tenant_id,
            name="Товар в грузоместе",
            sku_code=f"CARGO-SKU-{uuid.uuid4().hex[:8]}",
        )
        session.add_all([warehouse, product])
        await session.flush()
        request, _box, cargo = await _seed_inbound_containers(
            session, tenant, warehouse, product, "api"
        )
        await session.commit()
        request_id = request.id
        cargo_id = cargo.id
        product_id = product.id
        updated = await inbound_cargo_place_service.set_line_quantity(
            session,
            tenant_id,
            request_id,
            cargo_id,
            product_id,
            quantity=17,
        )
        assert len(updated.lines) == 1
        assert updated.lines[0].product_id == product_id
        assert updated.lines[0].quantity == 17

    catalog_response = await async_client.get(
        "/operations/inbound-packages", headers=headers
    )
    assert catalog_response.status_code == 200, catalog_response.text
    catalog_place = next(
        row for row in catalog_response.json() if row["id"] == str(cargo_id)
    )
    assert catalog_place["composition_tracked"] is True
    assert catalog_place["remaining_qty"] == 17
    assert catalog_place["lines"][0]["remaining_qty"] == 17


@pytest.mark.asyncio
async def test_inbound_document_and_container_free_text_are_persisted(
    async_client: AsyncClient,
) -> None:
    del async_client
    async with SessionLocal() as session:
        tenant, warehouse, _location, product = await _seed_tenant(session, "notes")
        request, box, cargo = await _seed_inbound_containers(
            session, tenant, warehouse, product, "notes"
        )
        await session.commit()

        updated_request = await inbound_intake_note_service.update_comment(
            session,
            tenant.id,
            request.id,
            comment="  Общий комментарий документа  ",
        )
        updated_box = await inbound_intake_box_service.update_box_free_text(
            session,
            tenant.id,
            request.id,
            box.id,
            free_text="  Хрупкое  ",
        )
        updated_cargo = await inbound_cargo_place_service.update_free_text(
            session,
            tenant.id,
            request.id,
            cargo.id,
            free_text="  Мешок  ",
        )

        assert updated_request.comment == "Общий комментарий документа"
        assert updated_box.free_text == "Хрупкое"
        assert updated_cargo.free_text == "Мешок"
