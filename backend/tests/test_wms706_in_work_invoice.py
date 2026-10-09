# ruff: noqa: E501
"""WMS-706: счёт по заказу FBS в работе и его связь с передачей — контракт тестов до кода.

Что фиксируют эти тесты:
- счёт по заказу в работе (WB и Ozon) выставляется до передачи; для этого серверу нужна
  дата работы, а не подтверждённая передача;
- счёт создаёт те же начисления, что создало бы завершение: сборка и упаковка отдельно,
  в штуках, по тарифу на дату работы; строки счёта ссылаются на них;
- передача после счёта не создаёт второго начисления; при частичной передаче Ozon
  доначисляются только новые штуки;
- предпросмотр ничего не сохраняет; счёт не меняет остаток, резерв и статус;
- без ставки счёт не создаётся; отмена заказа после счёта не меняет выставленный счёт.

Проверки настоящие: HTTP-ручки счёта, реальные функции начисления и передачи, реальная база.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db.session import SessionLocal, engine
from app.models.billing import (
    BillingInvoiceV2,
    BillingInvoiceV2Line,
    BillingInvoiceV2Source,
    BillingLedgerEntry,
)
from app.models.fbs_order import FbsOrder, FbsOrderProduct, FbsOrderReservation
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.inventory_reservation import InventoryReservation
from app.models.operation_fact import OperationFactCutover
from app.models.user import User
from app.services.billing_invoice_v2_service import BillingInvoiceV2Error, create_invoice_v2
from app.services.fbs_cancellation_service import reverse_fbs_order_billing
from app.services.fbs_order_billing_service import charge_handed_over_orders
from app.services.inventory_service import update_fbs_order_reservation
from app.services.sorting_location_service import get_or_create_sorting_location
from tests.test_wms706_in_work_report import (
    _details,
    _order,
    _rows_of,
    _seller,
    _supply,
    _tariff,
    _tenant,
    _warehouse,
    msk,
)

PERIOD = {"date_from": "2026-08-01", "date_to": "2026-08-31"}
WORK_DAY = msk(2026, 8, 15, 12)
SERVICES = ("fbs_order", "packing")


def _body(seller_id: uuid.UUID, sources: list[dict]) -> dict:
    return {
        "creation_mode": "selected_operations",
        "seller_id": str(seller_id),
        **PERIOD,
        "selected_root_ids": [],
        "selected_sources": sources,
    }


def _sources(order_id: uuid.UUID, services: tuple[str, ...] = SERVICES) -> list[dict]:
    return [
        {"source_type": "fbs_order", "source_id": str(order_id), "service_code": service}
        for service in services
    ]


async def _charges(order_id: uuid.UUID) -> list[dict]:
    """Начисления заказа как плоские строки: их и проверяем, ORM-объекты после выхода из сессии не трогаем."""
    async with SessionLocal() as session:
        entries = await session.scalars(
            select(BillingLedgerEntry).where(
                BillingLedgerEntry.source_type == "fbs_order",
                BillingLedgerEntry.source_id == order_id,
            )
        )
        return [
            {
                "id": entry.id,
                "service_code": entry.service_code,
                "entry_type": entry.entry_type,
                "quantity": Decimal(entry.quantity or 0),
                "amount": entry.amount,
                "occurred_at": entry.occurred_at if entry.occurred_at.tzinfo else entry.occurred_at.replace(tzinfo=UTC),
            }
            for entry in entries
        ]


async def _counts(tenant_id: uuid.UUID) -> dict[str, int]:
    async with SessionLocal() as session:
        return {
            "ledger": await session.scalar(
                select(func.count()).select_from(BillingLedgerEntry).where(BillingLedgerEntry.tenant_id == tenant_id)
            ),
            "invoices": await session.scalar(
                select(func.count()).select_from(BillingInvoiceV2).where(BillingInvoiceV2.tenant_id == tenant_id)
            ),
            "lines": await session.scalar(
                select(func.count()).select_from(BillingInvoiceV2Line).where(BillingInvoiceV2Line.tenant_id == tenant_id)
            ),
            "sources": await session.scalar(
                select(func.count()).select_from(BillingInvoiceV2Source).where(BillingInvoiceV2Source.tenant_id == tenant_id)
            ),
        }


async def _invoice_source_ids(invoice_id: str) -> set[uuid.UUID]:
    async with SessionLocal() as session:
        rows = await session.scalars(
            select(BillingInvoiceV2Source.billing_ledger_entry_id)
            .join(BillingInvoiceV2Line, BillingInvoiceV2Source.invoice_line_id == BillingInvoiceV2Line.id)
            .where(BillingInvoiceV2Line.invoice_id == uuid.UUID(invoice_id))
        )
        return {row for row in rows if row is not None}


async def _seed_tariffs(tenant_id, seller_id, rate: int = 1000) -> None:
    async with SessionLocal() as session:
        for service in SERVICES:
            session.add(_tariff(tenant_id, seller_id, service, rate))
        await session.commit()


async def _in_work_order(
    tenant_id, seller_id, warehouse_id, *, number: int, marketplace: str = "wb",
    quantities: tuple[int, ...] = (1,), packed=WORK_DAY,
) -> uuid.UUID:
    async with SessionLocal() as session:
        order = await _order(
            session, tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            number=number, marketplace=marketplace, status="packed", packed=packed, quantities=quantities,
        )
        await session.commit()
        return order.id


async def _create(client, headers, body, key: str):
    return await client.post("/billing/invoices-v2", headers={**headers, "Idempotency-Key": key}, json=body)


@pytest.mark.asyncio
@pytest.mark.parametrize(("marketplace", "quantities"), [("wb", (1,)), ("ozon", (2, 1))])
async def test_c10_invoice_creates_the_same_charges_as_completion(async_client, marketplace, quantities):
    """C10, R9: счёт по заказу в работе создаёт сборку и упаковку в штуках по тарифу на дату работы."""
    headers, tenant_id = await _tenant(async_client)
    seller_id = await _seller(async_client, headers, "Селлер C10")
    warehouse_id = await _warehouse(tenant_id)
    async with SessionLocal() as session:
        for service in SERVICES:
            session.add_all([
                # Работа 15 августа: действует старая ставка 1000. Новая 2000 с 16 августа — не для неё.
                _tariff(tenant_id, seller_id, service, 1000, valid_from=msk(2026, 7, 1), valid_to=msk(2026, 8, 16)),
                _tariff(tenant_id, seller_id, service, 2000, valid_from=msk(2026, 8, 16)),
            ])
        await session.commit()
    order_id = await _in_work_order(tenant_id, seller_id, warehouse_id, number=707001, marketplace=marketplace, quantities=quantities)
    pieces = sum(quantities)
    created = await _create(async_client, headers, _body(seller_id, _sources(order_id)), "c10")
    assert created.status_code == 201, f"счёт по заказу в работе должен выставляться до передачи: {created.text}"
    charges = {row["service_code"]: row for row in await _charges(order_id) if row["entry_type"] == "charge"}
    assert set(charges) == set(SERVICES), f"нужны начисления сборки и упаковки, есть: {sorted(charges)}"
    for service in SERVICES:
        row = charges[service]
        assert row["quantity"] == pieces, f"{service}: штуки {row['quantity']} вместо {pieces}"
        assert row["amount"] == 1000 * pieces, f"{service}: сумма {row['amount']} — ждали ставку на дату работы 1000"
        assert row["occurred_at"] == msk(2026, 8, 15, 12), f"{service}: дата начисления должна быть датой работы"
    assert await _invoice_source_ids(created.json()["id"]) == {row["id"] for row in charges.values()}, (
        "строки счёта должны ссылаться на начисления заказа"
    )
    assert created.json()["total_amount_kopecks"] == 2 * 1000 * pieces


@pytest.mark.asyncio
@pytest.mark.parametrize("transition", ["wb-confirmed", "ozon-sorted", "ozon-in_delivery", "ozon-done"])
async def test_c11_handover_after_in_work_invoice_does_not_charge_twice(async_client, transition):
    """C11, R10: заказ выставлен в счёт в работе, потом передан — второго начисления нет."""
    headers, tenant_id = await _tenant(async_client)
    seller_id = await _seller(async_client, headers, "Селлер C11")
    warehouse_id = await _warehouse(tenant_id)
    await _seed_tariffs(tenant_id, seller_id)
    marketplace = "wb" if transition.startswith("wb") else "ozon"
    order_id = await _in_work_order(tenant_id, seller_id, warehouse_id, number=707101, marketplace=marketplace)
    created = await _create(async_client, headers, _body(seller_id, _sources(order_id)), "c11")
    assert created.status_code == 201, created.text
    before = {row["service_code"]: row for row in await _charges(order_id)}
    handover = msk(2026, 8, 20, 12)
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        if marketplace == "wb":
            supply = await _supply(
                session, tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
                number=707102, delivered=handover,
            )
            order.supply_id = supply.id
            order.status = "in_delivery"
        else:
            order.status = transition.split("-", 1)[1]
        await charge_handed_over_orders(session, [order], occurred_at=handover)
        await session.commit()
    after = await _charges(order_id)
    charges_after = [row for row in after if row["entry_type"] == "charge"]
    assert len(charges_after) == 2, (
        f"после передачи должно остаться по одному начислению на услугу, сейчас {len(charges_after)}"
    )
    for row in charges_after:
        old = before[row["service_code"]]
        assert row["id"] == old["id"] and row["amount"] == old["amount"], (
            f"{row['service_code']}: начисление из счёта не должно меняться при передаче"
        )
        assert row["occurred_at"] == msk(2026, 8, 15, 12), "дата начисления остаётся датой работы"
    details = await _details(async_client, headers, seller_id)
    rows = _rows_of(details["entries"], order_id)
    for service in SERVICES:
        service_rows = [row for row in rows if row["service_code"] == service]
        assert len(service_rows) == 1, f"в отчёте заказ по услуге {service} должен быть один раз: {len(service_rows)}"
        row = service_rows[0]
        assert row.get("in_work") is not True, "после передачи заказ уже не в работе"
        assert row["amount_kopecks"] == before[service]["amount"], "сумма строки берётся из начисления счёта"
        assert row["invoice_history"] == {"state": "known", "count": 1}, (
            f"отметка «Счёт выставлялся» должна стоять: {row['invoice_history']}"
        )


@pytest.mark.asyncio
async def test_c12_repeat_selection_and_double_submit_make_one_invoice(async_client):
    """C12, R10: повторный выбор отклоняется, повтор с тем же ключом даёт тот же счёт."""
    headers, tenant_id = await _tenant(async_client)
    seller_id = await _seller(async_client, headers, "Селлер C12")
    warehouse_id = await _warehouse(tenant_id)
    await _seed_tariffs(tenant_id, seller_id)
    order_id = await _in_work_order(tenant_id, seller_id, warehouse_id, number=707201)
    body = _body(seller_id, _sources(order_id))
    first = await _create(async_client, headers, body, "c12-first")
    assert first.status_code == 201, first.text
    double_click = await _create(async_client, headers, body, "c12-first")
    assert double_click.status_code == 201 and double_click.json()["id"] == first.json()["id"], (
        "повтор с тем же ключом должен вернуть тот же счёт, а не создать второй"
    )
    again = await _create(async_client, headers, body, "c12-second")
    assert again.status_code == 422 and again.json()["detail"] == "selected_source_already_invoiced", again.text
    preview = await async_client.post("/billing/invoices-v2/preview", headers=headers, json=body)
    assert preview.status_code == 422 and preview.json()["detail"] == "selected_source_already_invoiced", preview.text
    charges = [row for row in await _charges(order_id) if row["entry_type"] == "charge"]
    assert len(charges) == 2, f"по заказу должно остаться два начисления (сборка и упаковка), есть {len(charges)}"


@pytest.mark.asyncio
@pytest.mark.parametrize("same_key", [False, True], ids=["other-key", "same-key"])
async def test_c13_simultaneous_invoices_for_one_in_work_order(async_client, same_key):
    """C13, R10: два одновременных счёта по одному заказу — проходит один, второй получает отказ.

    Проверяется только на PostgreSQL: блокировка строки селлера в транзакции есть только там.
    На SQLite тест пропускается и на этом проверку не засчитывает.
    """
    if engine.dialect.name != "postgresql":
        pytest.skip("одновременное выставление проверяется на PostgreSQL (WMS_TEST_DATABASE_URL)")
    headers, tenant_id = await _tenant(async_client)
    seller_id = await _seller(async_client, headers, "Селлер C13")
    warehouse_id = await _warehouse(tenant_id)
    await _seed_tariffs(tenant_id, seller_id)
    order_id = await _in_work_order(tenant_id, seller_id, warehouse_id, number=707301)
    body = _body(seller_id, _sources(order_id))
    async with SessionLocal() as lookup:
        user_id = await lookup.scalar(select(User.id).where(User.tenant_id == tenant_id))
    async with SessionLocal() as first_session:
        first = await create_invoice_v2(
            first_session, tenant_id=tenant_id, user_id=user_id, request=body, idempotency_key="first",
        )
        started = asyncio.Event()

        async def second_request() -> uuid.UUID | str:
            async with SessionLocal() as second_session:
                started.set()
                try:
                    invoice = await create_invoice_v2(
                        second_session, tenant_id=tenant_id, user_id=user_id, request=body,
                        idempotency_key="first" if same_key else "second",
                    )
                    await second_session.commit()
                    return invoice.id
                except BillingInvoiceV2Error as exc:
                    await second_session.rollback()
                    return str(exc)

        second_task = asyncio.create_task(second_request())
        try:
            await started.wait()
            done, _ = await asyncio.wait({second_task}, timeout=0.2)
            assert not done, "второй запрос должен ждать, пока первый не зафиксирует счёт"
            await first_session.commit()
            result = await asyncio.wait_for(second_task, timeout=5)
        finally:
            if not second_task.done():
                second_task.cancel()
                await asyncio.gather(second_task, return_exceptions=True)
        assert result == (first.id if same_key else "selected_source_already_invoiced"), result
    counts = await _counts(tenant_id)
    assert counts["invoices"] == 1, f"должен остаться один счёт, есть {counts['invoices']}"


@pytest.mark.asyncio
@pytest.mark.parametrize("grown", [False, True], ids=["same-pieces", "grown-piece"])
async def test_c14_ozon_partial_handover_after_invoice_charges_only_new_pieces(async_client, grown):
    """C14, R10: Ozon с двумя позициями выставлен в работе; частичные передачи не удваивают уже выставленное."""
    headers, tenant_id = await _tenant(async_client)
    seller_id = await _seller(async_client, headers, "Селлер C14")
    warehouse_id = await _warehouse(tenant_id)
    await _seed_tariffs(tenant_id, seller_id)
    order_id = await _in_work_order(
        tenant_id, seller_id, warehouse_id, number=707401, marketplace="ozon", quantities=(1, 1),
    )
    created = await _create(async_client, headers, _body(seller_id, _sources(order_id)), "c14")
    assert created.status_code == 201, created.text
    invoiced_total = created.json()["total_amount_kopecks"]
    async with SessionLocal() as session:
        positions = list(await session.scalars(
            select(FbsOrderProduct).where(FbsOrderProduct.order_id == order_id).order_by(FbsOrderProduct.position_index)
        ))
        first_product, second_product = positions[0].product_id, positions[1].product_id
        if grown:
            positions[0].quantity = 2
            await session.commit()
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        await charge_handed_over_orders(
            session, [order], occurred_at=msk(2026, 8, 18, 12),
            quantities_by_order={order_id: {first_product: 1}},
        )
        await session.commit()
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        first_qty = 2 if grown else 1
        await charge_handed_over_orders(
            session, [order], occurred_at=msk(2026, 8, 19, 12),
            quantities_by_order={order_id: {first_product: first_qty, second_product: 1}},
        )
        await session.commit()
    expected = 3 if grown else 2
    charges = [row for row in await _charges(order_id) if row["entry_type"] == "charge"]
    for service in SERVICES:
        rows = [row for row in charges if row["service_code"] == service]
        assert sum(row["quantity"] for row in rows) == expected, (
            f"{service}: всего штук {sum(row['quantity'] for row in rows)}, ждали {expected}"
        )
        assert sum(int(row["amount"] or 0) for row in rows) == 1000 * expected, (
            f"{service}: сумма должна соответствовать {expected} штукам по 1000"
        )
    reread = await async_client.get(f"/billing/invoices-v2/{created.json()['id']}", headers=headers)
    assert reread.status_code == 200
    assert reread.json()["total_amount_kopecks"] == invoiced_total, "выставленный счёт не должен меняться при передаче"


@pytest.mark.asyncio
async def test_c15_preview_saves_nothing_for_in_work_order(async_client):
    """C15, R11: предпросмотр счёта по заказу в работе показывает сумму и ничего не сохраняет."""
    headers, tenant_id = await _tenant(async_client)
    seller_id = await _seller(async_client, headers, "Селлер C15")
    warehouse_id = await _warehouse(tenant_id)
    await _seed_tariffs(tenant_id, seller_id)
    order_id = await _in_work_order(tenant_id, seller_id, warehouse_id, number=707501)
    before = await _counts(tenant_id)
    preview = await async_client.post(
        "/billing/invoices-v2/preview", headers=headers, json=_body(seller_id, _sources(order_id))
    )
    assert preview.status_code == 200, f"предпросмотр по заказу в работе должен открываться: {preview.text}"
    assert preview.json()["total_amount_kopecks"] == 2 * 1000, "предпросмотр: сборка и упаковка по 1000"
    assert await _counts(tenant_id) == before, "предпросмотр не должен оставлять начислений и счетов в базе"


@pytest.mark.asyncio
async def test_c16_invoice_does_not_change_stock_reserve_or_status(async_client):
    """C16, R12: счёт по заказу с резервом не меняет остаток, резерв заказа и его статус."""
    headers, tenant_id = await _tenant(async_client)
    seller_id = await _seller(async_client, headers, "Селлер C16")
    warehouse_id = await _warehouse(tenant_id)
    await _seed_tariffs(tenant_id, seller_id)
    async with SessionLocal() as session:
        order = await _order(
            session, tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            number=707601, status="packed", packed=msk(2026, 8, 15, 12),
        )
        location = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
        session.add(InventoryBalance(
            tenant_id=tenant_id, product_id=order.product_id, storage_location_id=location.id,
            quantity=5, quantity_unpacked=5, quantity_packed=0,
        ))
        await session.flush()
        await update_fbs_order_reservation(session, order, reserve=True)
        await session.commit()
        order_id = order.id

    async def state() -> dict:
        async with SessionLocal() as session:
            current = await session.get(FbsOrder, order_id)
            return {
                "status": current.status,
                "reserve_status": current.reserve_status,
                "pick_status": current.pick_status,
                "pack_status": current.pack_status,
                "balances": sorted(
                    (str(b.product_id), b.quantity, b.quantity_unpacked, b.quantity_packed)
                    for b in await session.scalars(select(InventoryBalance).where(InventoryBalance.tenant_id == tenant_id))
                ),
                "reservations": sorted(
                    (str(r.product_id), r.quantity)
                    for r in await session.scalars(select(FbsOrderReservation).where(FbsOrderReservation.fbs_order_id == order_id))
                ),
                "movements": await session.scalar(select(func.count()).select_from(InventoryMovement).where(InventoryMovement.tenant_id == tenant_id)),
                "holds": await session.scalar(select(func.count()).select_from(InventoryReservation).where(InventoryReservation.tenant_id == tenant_id)),
            }

    before = await state()
    assert before["reservations"], "предусловие: у заказа должен быть резерв, иначе проверка пустая"
    created = await _create(async_client, headers, _body(seller_id, _sources(order_id)), "c16")
    assert created.status_code == 201, created.text
    assert await state() == before, "счёт не должен менять остаток, резерв, статус и движения"


@pytest.mark.asyncio
async def test_c17_no_rate_refuses_invoice_without_charges(async_client):
    """C17, R13: нет ставки — счёт не создаётся, понятная причина, начислений не остаётся."""
    headers, tenant_id = await _tenant(async_client)
    seller_id = await _seller(async_client, headers, "Селлер C17")
    warehouse_id = await _warehouse(tenant_id)
    order_id = await _in_work_order(tenant_id, seller_id, warehouse_id, number=707701)
    before = await _counts(tenant_id)
    created = await _create(async_client, headers, _body(seller_id, _sources(order_id)), "c17")
    assert created.status_code == 422, created.text
    assert created.json()["detail"] == "unpriced_or_cross_seller_chain", (
        "причина должна быть «операция без ставки» (её понимает экран), а не другое правило: "
        f"пришло {created.json()['detail']!r}"
    )
    assert await _counts(tenant_id) == before, "при отказе не должно остаться ни счёта, ни начисления"


@pytest.mark.asyncio
async def test_c18_cancel_after_in_work_invoice_keeps_the_invoice(async_client):
    """C18, R14: отмена заказа после счёта в работе — счёт сам не меняется, новых строк нет."""
    headers, tenant_id = await _tenant(async_client)
    seller_id = await _seller(async_client, headers, "Селлер C18")
    warehouse_id = await _warehouse(tenant_id)
    await _seed_tariffs(tenant_id, seller_id)
    order_id = await _in_work_order(tenant_id, seller_id, warehouse_id, number=707801)
    created = await _create(async_client, headers, _body(seller_id, _sources(order_id)), "c18")
    assert created.status_code == 201, created.text
    invoice_id = created.json()["id"]
    invoice_before = (await async_client.get(f"/billing/invoices-v2/{invoice_id}", headers=headers)).json()
    counts_before = await _counts(tenant_id)
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        order.status = "cancelled"
        await reverse_fbs_order_billing(session, order)
        await session.commit()
    invoice_after = (await async_client.get(f"/billing/invoices-v2/{invoice_id}", headers=headers)).json()
    assert invoice_after == invoice_before, "выставленный счёт после отмены заказа не должен меняться"
    counts_after = await _counts(tenant_id)
    assert counts_after["invoices"] == counts_before["invoices"], "отмена не создаёт нового счёта"
    assert counts_after["lines"] == counts_before["lines"], "отмена не добавляет строк в счёт"
    assert counts_after["sources"] == counts_before["sources"], "отмена не добавляет источников в счёт"
    preview = await async_client.post(
        "/billing/invoices-v2/preview", headers=headers, json=_body(seller_id, _sources(order_id))
    )
    assert preview.status_code == 422, "отменённый заказ не должен попадать в новый счёт"
    cancelled = await async_client.post(f"/billing/invoices-v2/{invoice_id}/cancel", headers=headers)
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled", (
        "существующая отмена счёта должна работать как раньше"
    )


@pytest.mark.asyncio
async def test_c24_early_ozon_invoice_is_not_counted_in_two_adjacent_periods(async_client):
    """C24, R10: сумма соседних периодов равна общей и единственному начислению 20 ₽.

    Счёт за сборку выставлен 15 августа, передача — 1 сентября, переход на факты
    операций — 26 августа. Контракт не выбирает месяц признания дохода.
    """
    headers, tenant_id = await _tenant(async_client)
    seller_id = await _seller(async_client, headers, "Селлер C24")
    warehouse_id = await _warehouse(tenant_id)
    async with SessionLocal() as session:
        # Только сборка тарифицируется: одно денежное начисление на 20 ₽.
        session.add(_tariff(tenant_id, seller_id, "fbs_order", 2000))
        session.add(OperationFactCutover(id=1, occurred_at=msk(2026, 8, 26)))
        await session.commit()
    order_id = await _in_work_order(
        tenant_id, seller_id, warehouse_id, number=707401, marketplace="ozon", packed=WORK_DAY,
    )
    created = await _create(
        async_client, headers, _body(seller_id, _sources(order_id, ("fbs_order",))), "c24",
    )
    assert created.status_code == 201, created.text
    assert created.json()["total_amount_kopecks"] == 2000
    before = await _charges(order_id)
    assert len(before) == 1 and before[0]["amount"] == 2000
    assert before[0]["occurred_at"] == WORK_DAY

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        order.status = "sorted"
        await charge_handed_over_orders(session, [order], occurred_at=msk(2026, 9, 1, 12))
        await session.commit()
    monetary_charges = [row for row in await _charges(order_id) if row["amount"]]
    assert monetary_charges == before, "передача должна сохранить единственное денежное начисление"

    august = await _details(async_client, headers, seller_id, period=PERIOD)
    september = await _details(
        async_client, headers, seller_id,
        period={"date_from": "2026-09-01", "date_to": "2026-09-30"},
    )
    combined = await _details(
        async_client, headers, seller_id,
        period={"date_from": "2026-08-01", "date_to": "2026-09-30"},
    )
    august_amount = august["totals"]["net_total_kopecks"]
    september_amount = september["totals"]["net_total_kopecks"]
    combined_amount = combined["totals"]["net_total_kopecks"]
    assert august_amount + september_amount == combined_amount == 2000, (
        "одно начисление 20 ₽ не должно учитываться в двух непересекающихся периодах: "
        f"август={august_amount}, сентябрь={september_amount}, "
        f"сумма месяцев={august_amount + september_amount}, общий период={combined_amount} коп."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("early_service", "late_service"),
    [("fbs_order", "packing"), ("packing", "fbs_order")],
    ids=["assembly-august-packing-september", "packing-august-assembly-september"],
)
async def test_c25_ozon_split_services_are_reported_in_their_occurrence_month(
    async_client, early_service, late_service,
):
    """C25, R5/R10: отдельные услуги Ozon остаются в месяцах собственных начислений."""
    headers, tenant_id = await _tenant(async_client)
    seller_id = await _seller(async_client, headers, "Селлер C25")
    warehouse_id = await _warehouse(tenant_id)
    handover = msk(2026, 9, 1, 12)
    async with SessionLocal() as session:
        for service in SERVICES:
            session.add(_tariff(tenant_id, seller_id, service, 1000))
        session.add(OperationFactCutover(id=1, occurred_at=msk(2026, 8, 26)))
        await session.commit()
    order_id = await _in_work_order(
        tenant_id, seller_id, warehouse_id, number=707501, marketplace="ozon", packed=WORK_DAY,
    )

    created = await _create(
        async_client, headers, _body(seller_id, _sources(order_id, (early_service,))), "c25",
    )
    assert created.status_code == 201, created.text
    assert created.json()["total_amount_kopecks"] == 1000

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        order.status = "sorted"
        await charge_handed_over_orders(session, [order], occurred_at=handover)
        await session.commit()

    charge_rows = [row for row in await _charges(order_id) if row["entry_type"] == "charge"]
    charges_by_service = {row["service_code"]: row for row in charge_rows}
    assert set(charges_by_service) == set(SERVICES), (
        f"нужны отдельные начисления за сборку и упаковку: {sorted(charges_by_service)}"
    )
    expected_dates = {
        early_service: WORK_DAY,
        late_service: handover,
    }
    for service in SERVICES:
        assert charges_by_service[service]["amount"] == 1000, f"{service} должна стоить 10 ₽"
        assert charges_by_service[service]["occurred_at"] == expected_dates[service], (
            f"{service} должна оставаться датированной собственным событием"
        )

    august = await _details(async_client, headers, seller_id, period=PERIOD)
    september = await _details(
        async_client, headers, seller_id,
        period={"date_from": "2026-09-01", "date_to": "2026-09-30"},
    )
    combined = await _details(
        async_client, headers, seller_id,
        period={"date_from": "2026-08-01", "date_to": "2026-09-30"},
    )
    august_amount = august["totals"]["net_total_kopecks"]
    september_amount = september["totals"]["net_total_kopecks"]
    combined_amount = combined["totals"]["net_total_kopecks"]
    assert (august_amount, september_amount, combined_amount) == (1000, 1000, 2000), (
        "сборка и упаковка должны учитываться по 10 ₽ каждая в месяце своего начисления, "
        f"а общий период должен сохранять 20 ₽: август={august_amount}, "
        f"сентябрь={september_amount}, август-сентябрь={combined_amount} коп."
    )


@pytest.mark.asyncio
async def test_c26_ozon_assembly_reversal_remains_in_report_after_handover(async_client):
    """C26, R10/R14: сторно сборки после передачи вычитается из общего отчёта."""
    headers, tenant_id = await _tenant(async_client)
    seller_id = await _seller(async_client, headers, "Селлер C26")
    warehouse_id = await _warehouse(tenant_id)
    async with SessionLocal() as session:
        for service in SERVICES:
            session.add(_tariff(tenant_id, seller_id, service, 1000))
        session.add(OperationFactCutover(id=1, occurred_at=msk(2026, 8, 26)))
        await session.commit()
    order_id = await _in_work_order(
        tenant_id, seller_id, warehouse_id, number=707601, marketplace="ozon", packed=WORK_DAY,
    )

    created = await _create(async_client, headers, _body(seller_id, _sources(order_id)), "c26")
    assert created.status_code == 201, created.text
    assert created.json()["total_amount_kopecks"] == 2000
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        order.status = "sorted"
        await charge_handed_over_orders(session, [order], occurred_at=msk(2026, 9, 1, 12))
        await session.commit()
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        order.status = "cancelled"
        await reverse_fbs_order_billing(session, order)
        await session.commit()

    async with SessionLocal() as session:
        reversals = list(await session.scalars(
            select(BillingLedgerEntry).where(
                BillingLedgerEntry.tenant_id == tenant_id,
                BillingLedgerEntry.source_type == "billing_reversal",
                BillingLedgerEntry.entry_type == "reversal",
                BillingLedgerEntry.service_code == "fbs_order",
            )
        ))
    assert any(row.amount == -1000 for row in reversals), (
        "в журнале должно сохраниться сторно сборки на -10 ₽"
    )

    report = await _details(
        async_client, headers, seller_id,
        period={"date_from": "2026-08-01", "date_to": "2026-10-09"},
    )
    net_total = report["totals"]["net_total_kopecks"]
    assert net_total == 1000, (
        "после сторно сборки итог должен быть 10 ₽: две исходные услуги на 20 ₽ "
        f"минус сторно сборки на 10 ₽; получено {net_total} коп."
    )


@pytest.mark.asyncio
async def test_c27_out_of_period_charges_keep_invoice_history(async_client):
    """C27, R10: сентябрьские строки сохраняют ссылку и историю августовского счёта."""
    headers, tenant_id = await _tenant(async_client)
    seller_id = await _seller(async_client, headers, "Селлер C27")
    warehouse_id = await _warehouse(tenant_id)
    handover = msk(2026, 9, 1, 12)
    async with SessionLocal() as session:
        for service in SERVICES:
            session.add(_tariff(tenant_id, seller_id, service, 1000))
        session.add(OperationFactCutover(id=1, occurred_at=msk(2026, 8, 26)))
        await session.commit()
    order_id = await _in_work_order(
        tenant_id, seller_id, warehouse_id, number=707701, marketplace="ozon", packed=WORK_DAY,
    )
    created = await _create(async_client, headers, _body(seller_id, _sources(order_id)), "c27")
    assert created.status_code == 201, created.text

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        order.status = "sorted"
        await charge_handed_over_orders(session, [order], occurred_at=handover)
        await session.commit()
    charge_ids = {
        row["service_code"]: str(row["id"])
        for row in await _charges(order_id)
        if row["entry_type"] == "charge"
    }
    assert set(charge_ids) == set(SERVICES), f"в счёте должны быть обе услуги: {sorted(charge_ids)}"

    september = await _details(
        async_client, headers, seller_id,
        period={"date_from": "2026-09-01", "date_to": "2026-09-30"},
    )
    rows = _rows_of(september["entries"], order_id)
    violations: list[str] = []
    for service in SERVICES:
        service_rows = [row for row in rows if row["service_code"] == service]
        if len(service_rows) != 1:
            violations.append(f"{service}: ожидалась одна строка, найдено {len(service_rows)}")
            continue
        row = service_rows[0]
        if row.get("result") == "unpriced":
            violations.append(f"{service}: строка ошибочно получила результат unpriced")
        if row.get("billing_ledger_entry_id") != charge_ids[service]:
            violations.append(
                f"{service}: потеряна ссылка billing_ledger_entry_id "
                f"(фактически {row.get('billing_ledger_entry_id')!r})"
            )
        history = row.get("invoice_history")
        if history != {"state": "known", "count": 1}:
            violations.append(f"{service}: потеряна история счёта (фактически {history!r})")
    assert not violations, "сентябрьские строки потеряли выставленный в августе счёт:\n" + "\n".join(violations)
