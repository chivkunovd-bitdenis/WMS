# ruff: noqa: E501
"""WMS-706: заказы FBS в работе в разделе «Расчёты» фулфилмента — контракт тестов до кода.

Имена полей, которые тесты фиксируют как контракт для разработки:
- сводка и строка селлера: totals.in_work_items и rows[i].in_work_items — штуки заказов в работе;
- строки раздела документов: in_work = true у строк заказа в работе. У такой строки
  fbs_status_label пуст, billing_ledger_entry_id пуст, ставка и сумма пусты;
- у каждого заказа в работе есть строки услуг fbs_order и packing (галочка выбора по каждой
  услуге отдельно), а его штуки учитываются один раз: сумма item_quantity по его строкам
  равна штукам заказа.

Все проверки — настоящие HTTP-запросы к ручкам отчёта и настоящие записи в базе.
Проверки классов «навсегда» (сохранение поведения) зелёные на текущем коде; их польза
доказана временной порчей продуктового кода, см. отчёт по задаче.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.roles import FULFILLMENT_SELLER
from app.db.session import SessionLocal
from app.models.billing import BillingTariffVersionV2
from app.models.fbs_order import FbsOrder, FbsOrderProduct
from app.models.fbs_supply import FbsSupply
from app.models.product import Product
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services.fbs_order_billing_service import record_fbs_order_confirmed
from app.services.storage_measurement_service import MOSCOW
from app.services.tokens import create_access_token

PERIOD = {"date_from": "2026-08-01", "date_to": "2026-08-31"}
ALL_STATUSES = (
    "new",
    "in_supply",
    "assembling",
    "packed",
    "external_processing",
    "sorted",
    "in_delivery",
    "done",
    "cancelled",
    "defect",
)
IN_WORK_STATUSES = frozenset({"in_supply", "assembling", "packed"})


def msk(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """Московский момент, сохраняемый в базе как UTC: так читают его и SQLite, и PostgreSQL."""
    return datetime(year, month, day, hour, minute, tzinfo=MOSCOW).astimezone(UTC)


AUG_1 = msk(2026, 8, 1)
JUL_1 = msk(2026, 7, 1)


async def _tenant(client) -> tuple[dict[str, str], uuid.UUID]:
    suffix = uuid.uuid4().hex[:12]
    registered = await client.post(
        "/auth/register",
        json={
            "organization_name": "WMS706",
            "slug": f"wms706-{suffix}",
            "admin_email": f"wms706-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    tenant_id = uuid.UUID((await client.get("/auth/me", headers=headers)).json()["tenant_id"])
    return headers, tenant_id


async def _seller(client, headers: dict[str, str], name: str) -> uuid.UUID:
    response = await client.post("/sellers", headers=headers, json={"name": name})
    assert response.status_code in (200, 201), response.text
    return uuid.UUID(response.json()["id"])


async def _warehouse(tenant_id: uuid.UUID) -> uuid.UUID:
    async with SessionLocal() as session:
        warehouse = Warehouse(
            tenant_id=tenant_id, name="WMS706 склад", code=f"WMS706-{uuid.uuid4().hex[:8]}"
        )
        session.add(warehouse)
        await session.commit()
        return warehouse.id


async def _order(
    session,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    number: int,
    marketplace: str = "wb",
    status: str = "packed",
    created: datetime = AUG_1,
    packed: datetime | None = None,
    picked: datetime | None = None,
    quantities: tuple[int, ...] = (1,),
    supply_id: uuid.UUID | None = None,
) -> FbsOrder:
    """Заказ FBS с позициями. У WB одна позиция на одну штуку, у Ozon позиций может быть несколько."""
    order = FbsOrder(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        marketplace=marketplace,
        wb_order_id=number,
        external_order_id=f"{number}-0001-1" if marketplace == "ozon" else None,
        status=status,
        supply_id=supply_id,
        created_at_wb=created,
        deadline_at=created + timedelta(days=3),
        mapping_status="unmapped",
        reserve_status="none",
        packed_at=packed,
        picked_at=picked,
    )
    session.add(order)
    await session.flush()
    for index, quantity in enumerate(quantities):
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name=f"Товар {number}-{index}",
            sku_code=f"SKU-{number}-{index}",
        )
        session.add(product)
        await session.flush()
        if index == 0:
            order.product_id = product.id
        session.add(
            FbsOrderProduct(
                order_id=order.id,
                product_id=product.id,
                quantity=quantity,
                position_index=index,
            )
        )
    await session.flush()
    return order


async def _supply(session, *, tenant_id, seller_id, warehouse_id, number, delivered: datetime) -> FbsSupply:
    supply = FbsSupply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        marketplace="wb",
        name=f"Поставка {number}",
        wb_supply_id=f"WB-706-{number}",
        delivery_type="warehouse_sc",
        delivered_at=delivered,
    )
    session.add(supply)
    await session.flush()
    return supply


def _tariff(tenant_id, seller_id, service_code: str, rate: int, valid_from=JUL_1, valid_to=None):
    return BillingTariffVersionV2(
        tenant_id=tenant_id,
        seller_id=seller_id,
        service_code=service_code,
        unit="item",
        rate=rate,
        enabled=True,
        valid_from_at=valid_from,
        valid_to_at=valid_to,
    )


async def _summary(client, headers, *, seller_id=None, include_finance=True, period=PERIOD):
    params = {**period, "include_finance": str(include_finance).lower()}
    if seller_id is not None:
        params["seller_id"] = str(seller_id)
    response = await client.get("/billing/seller-report/summary", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def _details(client, headers, seller_id, *, include_finance=True, period=PERIOD):
    params = {**period, "include_finance": str(include_finance).lower(), "limit": 500}
    response = await client.get(
        f"/billing/seller-report/sellers/{seller_id}/details", headers=headers, params=params
    )
    assert response.status_code == 200, response.text
    return response.json()


def _rows_of(entries: list[dict], source_id: uuid.UUID) -> list[dict]:
    return [row for row in entries if row["source_id"] == str(source_id)]


def _in_work(entries: list[dict]) -> list[dict]:
    return [row for row in entries if row.get("in_work") is True]


def _without_in_work_total(totals: dict) -> dict:
    return {key: value for key, value in totals.items() if key != "in_work_items"}


@pytest.mark.asyncio
async def test_c1_in_work_is_exactly_the_three_warehouse_statuses(async_client):
    """C1, R1: в работе только in_supply, assembling, packed; остальные статусы — нет."""
    headers, tenant_id = await _tenant(async_client)
    seller_id = await _seller(async_client, headers, "Селлер C1")
    warehouse_id = await _warehouse(tenant_id)
    status_of: dict[str, tuple[str, str]] = {}
    async with SessionLocal() as session:
        number = 706100
        for marketplace in ("wb", "ozon"):
            for status in ALL_STATUSES:
                number += 1
                order = await _order(
                    session,
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    warehouse_id=warehouse_id,
                    number=number,
                    marketplace=marketplace,
                    status=status,
                    packed=msk(2026, 8, 15, 12),
                )
                status_of[str(order.id)] = (marketplace, status)
        await session.commit()
    details = await _details(async_client, headers, seller_id)
    actual = {row["source_id"] for row in _in_work(details["entries"])}
    expected = {key for key, (_, status) in status_of.items() if status in IN_WORK_STATUSES}
    unexpected = sorted(status_of[key] for key in actual - expected)
    missing = sorted(status_of[key] for key in expected - actual)
    assert not unexpected and not missing, (
        f"в работе должны быть заказы только в статусах {sorted(IN_WORK_STATUSES)}. "
        f"Лишние (marketplace, status): {unexpected}. Не попали (marketplace, status): {missing}"
    )


@pytest.mark.asyncio
async def test_c2_in_work_row_is_marked_and_has_no_status_chip(async_client):
    """C2, R2: строка заказа в работе помечена, без плашки «Передан ВБ»; номер ведёт в историю."""
    headers, tenant_id = await _tenant(async_client)
    seller_id = await _seller(async_client, headers, "Селлер C2")
    warehouse_id = await _warehouse(tenant_id)
    async with SessionLocal() as session:
        work = await _order(
            session, tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            number=706200, status="packed", packed=msk(2026, 8, 15, 12),
        )
        supply = await _supply(
            session, tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            number=706201, delivered=msk(2026, 8, 20, 12),
        )
        handed = await _order(
            session, tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            number=706202, status="in_delivery", packed=msk(2026, 8, 10, 12), supply_id=supply.id,
        )
        await session.commit()
        work_id, handed_id = work.id, handed.id
    details = await _details(async_client, headers, seller_id)
    work_rows = _rows_of(details["entries"], work_id)
    assert work_rows, "заказ в работе не попал в раздел документов селлера"
    for row in work_rows:
        assert row.get("in_work") is True, f"строка заказа в работе без пометки in_work: {row}"
        assert not row.get("fbs_status_label"), (
            f"у заказа в работе не должно быть плашки статуса «Передан ВБ»: {row['fbs_status_label']!r}"
        )
        assert row["source_target"] == {"kind": "fbs_order", "source_id": str(work_id)}, (
            "номер заказа в работе должен оставаться ссылкой на историю заказа"
        )
    handed_rows = _rows_of(details["entries"], handed_id)
    assert handed_rows, "переданный заказ пропал из раздела"
    for row in handed_rows:
        assert row.get("in_work") is not True, "переданный заказ не должен быть помечен как в работе"
        assert row.get("fbs_status_label") == "Передан ВБ", (
            f"переданный заказ должен сохранить плашку «Передан ВБ», пришло {row.get('fbs_status_label')!r}"
        )


@pytest.mark.asyncio
async def test_c3_in_work_quantity_is_order_pieces_counted_once(async_client):
    """C3, R3: штуки заказа Ozon с двумя позициями — их сумма, по строкам заказа один раз."""
    headers, tenant_id = await _tenant(async_client)
    seller_id = await _seller(async_client, headers, "Селлер C3")
    warehouse_id = await _warehouse(tenant_id)
    async with SessionLocal() as session:
        wb_order = await _order(
            session, tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            number=706300, status="packed", packed=msk(2026, 8, 15, 12), quantities=(1,),
        )
        ozon_order = await _order(
            session, tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            number=706301, marketplace="ozon", status="assembling", packed=msk(2026, 8, 15, 13),
            quantities=(2, 3),
        )
        await session.commit()
        expected = {wb_order.id: 1, ozon_order.id: 5}
    details = await _details(async_client, headers, seller_id)
    for order_id, pieces in expected.items():
        rows = _rows_of(details["entries"], order_id)
        assert rows, f"заказ {order_id} в работе не виден в разделе"
        total = sum(int(row.get("item_quantity") or 0) for row in rows if row.get("in_work") is True)
        assert total == pieces, (
            f"штуки заказа {order_id} в работе должны считаться один раз: ожидали {pieces}, "
            f"по строкам вышло {total}"
        )


@pytest.mark.asyncio
async def test_c4_plate_sums_in_work_pieces_for_period_and_seller_filter(async_client):
    """C4, R4: плашка «В работе» — сумма штук заказов в работе за период при фильтре селлера."""
    headers, tenant_id = await _tenant(async_client)
    first = await _seller(async_client, headers, "Селлер C4-1")
    second = await _seller(async_client, headers, "Селлер C4-2")
    warehouse_id = await _warehouse(tenant_id)
    async with SessionLocal() as session:
        for number in (706400, 706401):
            await _order(
                session, tenant_id=tenant_id, seller_id=first, warehouse_id=warehouse_id,
                number=number, status="packed", packed=msk(2026, 8, 12, 12),
            )
        await _order(
            session, tenant_id=tenant_id, seller_id=second, warehouse_id=warehouse_id,
            number=706402, marketplace="ozon", status="assembling", packed=msk(2026, 8, 12, 12),
            quantities=(2, 2),
        )
        # За пределами периода: в плашку не попадает.
        await _order(
            session, tenant_id=tenant_id, seller_id=first, warehouse_id=warehouse_id,
            number=706403, status="packed", packed=msk(2026, 9, 2, 12),
        )
        await session.commit()
    everyone = await _summary(async_client, headers)
    assert everyone["totals"].get("in_work_items") == 6, (
        f"плашка «В работе» за период должна быть 6 штук (2 у первого, 4 у второго), "
        f"пришло {everyone['totals'].get('in_work_items')!r}"
    )
    per_seller = {row["seller_id"]: row.get("in_work_items") for row in everyone["rows"]}
    assert per_seller.get(str(first)) == 2 and per_seller.get(str(second)) == 4, per_seller
    only_first = await _summary(async_client, headers, seller_id=first)
    assert only_first["totals"].get("in_work_items") == 2, (
        f"при фильтре селлера плашка должна считать только его: пришло "
        f"{only_first['totals'].get('in_work_items')!r}"
    )


@pytest.mark.asyncio
async def test_c5_period_uses_work_date_with_moscow_boundaries(async_client):
    """C5, R5: период по дате работы (упаковка, потом сборка, потом создание), границы по Москве."""
    headers, tenant_id = await _tenant(async_client)
    seller_id = await _seller(async_client, headers, "Селлер C5")
    warehouse_id = await _warehouse(tenant_id)
    period = {"date_from": "2026-08-15", "date_to": "2026-08-16"}
    created = msk(2026, 8, 1)
    async with SessionLocal() as session:
        cases = {
            # Упаковка в периоде; подбор вне периода не должен это перебить.
            "packed_in": (706501, dict(packed=msk(2026, 8, 15, 23, 30), picked=msk(2026, 8, 10))),
            # Нет упаковки: работает дата подбора.
            "picked_in": (706502, dict(picked=msk(2026, 8, 16, 10))),
            # Нет упаковки и подбора: работает дата создания у маркетплейса.
            "created_in": (706503, dict(created=msk(2026, 8, 16, 1, 30))),
            # Упаковка раньше периода; подбор внутри периода не должен подменить её.
            "packed_before": (706504, dict(packed=msk(2026, 8, 14, 23, 59), picked=msk(2026, 8, 15, 10))),
            # Упаковка после периода.
            "packed_after": (706505, dict(packed=msk(2026, 8, 17, 0, 0))),
            # Конец дня по Москве включительно.
            "packed_last_minute": (706506, dict(packed=msk(2026, 8, 16, 23, 59))),
            # 00:30 по Москве 15 августа — это 14 августа по UTC: по UTC-дате выпал бы.
            "packed_first_minute": (706507, dict(packed=msk(2026, 8, 15, 0, 30))),
        }
        orders = {}
        for name, (number, dates) in cases.items():
            orders[name] = await _order(
                session, tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
                number=number, status="packed", **{"created": created, **dates},
            )
        await session.commit()
        ids = {name: order.id for name, order in orders.items()}
    details = await _details(async_client, headers, seller_id, period=period)
    actual = {row["source_id"] for row in _in_work(details["entries"])}
    expected_names = {"packed_in", "picked_in", "created_in", "packed_last_minute", "packed_first_minute"}
    expected = {str(ids[name]) for name in expected_names}
    assert actual == expected, (
        f"в период 15-16 августа по Москве должны попасть {sorted(expected_names)}; "
        f"лишние: {sorted(name for name, oid in ids.items() if str(oid) in actual - expected)}, "
        f"не попали: {sorted(name for name, oid in ids.items() if str(oid) in expected - actual)}"
    )


@pytest.mark.asyncio
async def test_c6_existing_totals_do_not_change_when_in_work_orders_appear(async_client):
    """C6, R6: «Документов», «Штук», «Отгружено FBS», «Стоимость», «Не тарифицируется», «Нет ставки» — прежние."""
    headers, tenant_id = await _tenant(async_client)
    seller_id = await _seller(async_client, headers, "Селлер C6")
    warehouse_id = await _warehouse(tenant_id)
    async with SessionLocal() as session:
        session.add_all([
            _tariff(tenant_id, seller_id, "fbs_order", 1000),
            _tariff(tenant_id, seller_id, "packing", 1000),
        ])
        supply = await _supply(
            session, tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            number=706600, delivered=msk(2026, 8, 20, 12),
        )
        await _order(
            session, tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            number=706601, status="in_delivery", packed=msk(2026, 8, 10, 12), supply_id=supply.id,
        )
        done = await _order(
            session, tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            number=706602, marketplace="ozon", status="done", packed=msk(2026, 8, 18, 10),
            quantities=(2,),
        )
        await record_fbs_order_confirmed(session, done, occurred_at=msk(2026, 8, 18, 12))
        await session.commit()
    before_summary = {flag: await _summary(async_client, headers, include_finance=flag) for flag in (False, True)}
    before_details = await _details(async_client, headers, seller_id)
    async with SessionLocal() as session:
        for number, marketplace, status, quantities in (
            (706610, "wb", "packed", (1,)),
            (706611, "wb", "packed", (1,)),
            (706612, "ozon", "assembling", (2, 1)),
        ):
            await _order(
                session, tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
                number=number, marketplace=marketplace, status=status,
                packed=msk(2026, 8, 15, 12), quantities=quantities,
            )
        await session.commit()
    after_summary = {flag: await _summary(async_client, headers, include_finance=flag) for flag in (False, True)}
    after_details = await _details(async_client, headers, seller_id)
    for flag in (False, True):
        assert _without_in_work_total(after_summary[flag]["totals"]) == _without_in_work_total(
            before_summary[flag]["totals"]
        ), f"итоги раздела изменились после появления заказов в работе (include_finance={flag})"
        assert [_without_in_work_total(row) for row in after_summary[flag]["rows"]] == [
            _without_in_work_total(row) for row in before_summary[flag]["rows"]
        ], f"строка селлера изменилась после появления заказов в работе (include_finance={flag})"
    assert _without_in_work_total(after_details["totals"]) == _without_in_work_total(before_details["totals"]), (
        "итоги раздела селлера изменились после появления заказов в работе"
    )
    non_work = [row for row in after_details["entries"] if row.get("in_work") is not True]
    assert non_work == before_details["entries"], "обычные строки раздела изменились после появления заказов в работе"


@pytest.mark.asyncio
async def test_c7_in_work_row_has_no_money_even_with_active_tariff(async_client):
    """C7, R6: строка заказа в работе не показывает ставку и сумму, даже когда тариф есть."""
    headers, tenant_id = await _tenant(async_client)
    seller_id = await _seller(async_client, headers, "Селлер C7")
    warehouse_id = await _warehouse(tenant_id)
    async with SessionLocal() as session:
        session.add_all([
            _tariff(tenant_id, seller_id, "fbs_order", 1000),
            _tariff(tenant_id, seller_id, "packing", 1000),
        ])
        order = await _order(
            session, tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            number=706700, status="packed", packed=msk(2026, 8, 15, 12),
        )
        await session.commit()
        order_id = order.id
    details = await _details(async_client, headers, seller_id)
    rows = _in_work(_rows_of(details["entries"], order_id))
    assert rows, "заказ в работе не попал в раздел документов селлера"
    for row in rows:
        assert row.get("rate_kopecks") is None and row.get("amount_kopecks") is None, (
            f"у заказа в работе до счёта не должно быть ни ставки, ни суммы: {row}"
        )
        assert not row.get("billing_ledger_entry_id"), "до счёта у заказа в работе не должно быть начисления"


@pytest.mark.asyncio
async def test_c8_seller_with_only_in_work_orders_is_listed_with_zeros(async_client):
    """C8, R7: селлер только с заказами в работе появляется со своими нулями и раскрывается."""
    headers, tenant_id = await _tenant(async_client)
    only_work = await _seller(async_client, headers, "Селлер C8 только в работе")
    idle = await _seller(async_client, headers, "Селлер C8 без активности")
    warehouse_id = await _warehouse(tenant_id)
    async with SessionLocal() as session:
        session.add_all([
            _tariff(tenant_id, only_work, "fbs_order", 1000),
            _tariff(tenant_id, only_work, "packing", 1000),
        ])
        for number in (706800, 706801):
            await _order(
                session, tenant_id=tenant_id, seller_id=only_work, warehouse_id=warehouse_id,
                number=number, status="packed", packed=msk(2026, 8, 15, 12),
            )
        await session.commit()
    summary = await _summary(async_client, headers)
    rows = {row["seller_id"]: row for row in summary["rows"]}
    assert str(only_work) in rows, "селлер только с заказами в работе не попал в таблицу селлеров"
    assert str(idle) not in rows, "селлер без всякой активности не должен появляться в таблице"
    row = rows[str(only_work)]
    for key in ("operation_count", "item_quantity", "fbs_items", "packing_items", "net_total_kopecks"):
        assert row.get(key) == 0, f"в строке селлера только с заказами в работе колонка {key} должна быть 0"
    assert row.get("in_work_items") == 2, f"штуки заказов в работе в строке селлера: {row.get('in_work_items')!r}"
    details = await _details(async_client, headers, only_work)
    assert len(_in_work(details["entries"])) >= 2, "в разделе селлера должны раскрываться его заказы в работе"


@pytest.mark.asyncio
async def test_c9_in_work_rows_are_selectable_per_service_without_ledger(async_client):
    """C9, R8: строка заказа в работе есть по каждой услуге (сборка и упаковка) и без начисления."""
    headers, tenant_id = await _tenant(async_client)
    seller_id = await _seller(async_client, headers, "Селлер C9")
    warehouse_id = await _warehouse(tenant_id)
    async with SessionLocal() as session:
        order = await _order(
            session, tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            number=706900, status="packed", packed=msk(2026, 8, 15, 12),
        )
        await session.commit()
        order_id = order.id
    details = await _details(async_client, headers, seller_id)
    rows = _rows_of(details["entries"], order_id)
    assert {row["service_code"] for row in rows} == {"fbs_order", "packing"}, (
        f"заказ в работе должен выбираться отдельно по сборке и упаковке, пришли услуги "
        f"{sorted(row['service_code'] for row in rows)}"
    )
    for row in rows:
        assert row.get("in_work") is True, f"строка выбора без пометки in_work: {row}"
        assert not row.get("billing_ledger_entry_id"), "у заказа в работе до счёта нет начисления для галочки"


@pytest.mark.asyncio
async def test_c19_seller_cabinet_never_shows_in_work(async_client):
    """C19, R15: кабинет селлера не получает заказы в работе, ни в итогах, ни в строках."""
    headers, tenant_id = await _tenant(async_client)
    seller_id = await _seller(async_client, headers, "Селлер C19")
    warehouse_id = await _warehouse(tenant_id)
    async with SessionLocal() as session:
        session.add_all([
            _tariff(tenant_id, seller_id, "fbs_order", 1000),
            _tariff(tenant_id, seller_id, "packing", 1000),
        ])
        supply = await _supply(
            session, tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            number=706190, delivered=msk(2026, 8, 20, 12),
        )
        handed = await _order(
            session, tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            number=706191, status="in_delivery", packed=msk(2026, 8, 10, 12), supply_id=supply.id,
        )
        work = await _order(
            session, tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            number=706192, status="packed", packed=msk(2026, 8, 15, 12),
        )
        user = User(
            tenant_id=tenant_id, seller_id=seller_id, email=f"c19-{uuid.uuid4().hex}@merchant.ru",
            password_hash="unused", role=FULFILLMENT_SELLER,
        )
        session.add(user)
        await session.commit()
        handed_id, work_id = handed.id, work.id
        token = create_access_token(
            user_id=user.id, tenant_id=tenant_id, role=FULFILLMENT_SELLER, seller_id=seller_id,
        )
    cabinet = {"Authorization": f"Bearer {token}"}
    summary = await async_client.get(
        "/seller-billing/summary", headers=cabinet, params=PERIOD
    )
    details = await async_client.get("/seller-billing/details", headers=cabinet, params=PERIOD)
    assert summary.status_code == details.status_code == 200, (summary.text, details.text)
    summary_body, details_body = summary.json(), details.json()
    assert "in_work_items" not in summary_body["totals"], "в кабинете селлера не должно быть плашки «В работе»"
    assert all("in_work_items" not in row for row in summary_body["rows"]), "в строке кабинета не должно быть «В работе»"
    ids = {row["source_id"] for row in details_body["entries"]}
    assert str(handed_id) in ids, "контроль: переданный заказ должен быть виден в кабинете"
    assert str(work_id) not in ids, "заказ в работе не должен появляться в кабинете селлера"
    assert not _in_work(details_body["entries"]), "в кабинете селлера не должно быть строк «в работе»"
