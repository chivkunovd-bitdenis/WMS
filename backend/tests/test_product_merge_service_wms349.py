"""WMS-349 · сериализация merge_products с обычной складской записью.

Что доказывается. Merge берёт ``SELECT Product ... FOR UPDATE`` до того, как
читает любые балансовые строки, и ровно в порядке возрастания ``id``. Именно
такой порядок берёт штатный writer остатков через
``inventory_service.lock_stock_product`` — совпадение порядка исключает встречный
deadlock, а сама блокировка сериализует конкурентное движение.

Границы теста. Тест-БД — SQLite, у которого ``FOR UPDATE`` синтаксически
игнорируется. Поэтому наличие блокировки и порядок инструкций проверяются на
уровне SQLAlchemy: каждый выполненный ``Select`` перекомпилируется под диалект
PostgreSQL и в его тексте ищется ``FOR UPDATE``. Дополнительный тест test_postgres_merge_replays_committed_movement_with_stale_balances
запускается только на PostgreSQL и проверяет настоящую конкурентную запись.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import event, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import ClauseElement

from app.db.session import SessionLocal, engine
from app.models.inventory_balance import InventoryBalance
from app.models.seller import Seller
from app.services import inventory_service
from app.services.product_merge_service import merge_products
from tests.inventory_actor_helpers import resolve_test_actor_user_id


async def _register_admin(async_client: AsyncClient, suffix: str) -> dict[str, str]:
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"WMS-349 {suffix}",
            "slug": f"wms349-{suffix}",
            "admin_email": f"wms349-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    return {"Authorization": f"Bearer {registered.json()['access_token']}"}


async def _create_product(
    async_client: AsyncClient,
    headers: dict[str, str],
    *,
    sku_code: str,
    seller_id: str,
    wb_vendor_code: str | None = None,
) -> dict[str, Any]:
    response = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": sku_code,
            "sku_code": sku_code,
            "seller_id": seller_id,
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "wb_vendor_code": wb_vendor_code,
        },
    )
    assert response.status_code == 200, response.text
    payload: dict[str, Any] = response.json()
    return payload


async def _seller_tenant_id(seller_id: str) -> uuid.UUID:
    async with SessionLocal() as session:
        seller_row = await session.get(Seller, uuid.UUID(seller_id))
        assert seller_row is not None
        return seller_row.tenant_id


async def _create_warehouse_location(
    async_client: AsyncClient, headers: dict[str, str], suffix: str
) -> uuid.UUID:
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WH", "code": f"wh-{suffix[-8:]}"},
    )
    assert warehouse.status_code in (200, 201), warehouse.text
    location = await async_client.post(
        f"/warehouses/{warehouse.json()['id']}/locations",
        headers=headers,
        json={"code": f"A-{suffix[-6:]}"},
    )
    assert location.status_code in (200, 201), location.text
    return uuid.UUID(location.json()["id"])


async def _add_stock(
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    location_id: uuid.UUID,
    quantity: int,
) -> None:
    async with SessionLocal() as session:
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=location_id,
            quantity_delta=quantity,
            movement_type="inbound_intake",
            actor_user_id=await resolve_test_actor_user_id(session, tenant_id),
        )
        await session.commit()


def _compile_pg(clauseelement: ClauseElement) -> str:
    """Компиляция SELECT под PostgreSQL-диалектом.

    Тест-БД — SQLite, а в её диалекте ``FOR UPDATE`` вырезается на этапе
    компиляции. Чтобы всё-таки увидеть блокирующий SELECT, тот же ORM-объект
    выражения перекомпилируем как под боевой PostgreSQL: там ``FOR UPDATE``
    попадает в итоговый текст ровно так же, как оно уйдёт в бой.
    """
    try:
        return str(clauseelement.compile(dialect=postgresql.dialect()))
    except Exception:  # pragma: no cover — все Select компилируются под PG
        return ""


class _Captured:
    __slots__ = ("bind_uuids", "kind", "pg_text", "sql", "text")

    def __init__(
        self,
        sql_lower: str,
        pg_text: str,
        bind_uuids: list[uuid.UUID],
    ) -> None:
        self.sql = sql_lower
        self.text = sql_lower
        self.pg_text = pg_text
        self.bind_uuids = bind_uuids
        if "from products" in sql_lower:
            self.kind = "product"
        elif "from inventory_balances" in sql_lower:
            self.kind = "balance"
        else:
            self.kind = "other"


def _parameters_to_uuids(parameters: Any) -> list[uuid.UUID]:
    """UUID'ы из параметров, приходящих в драйвер."""
    found: list[uuid.UUID] = []

    def _visit(value: Any) -> None:
        if isinstance(value, uuid.UUID):
            found.append(value)
            return
        if isinstance(value, str):
            try:
                found.append(uuid.UUID(value))
            except ValueError:
                return
            return
        if isinstance(value, dict):
            for item in value.values():
                _visit(item)
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                _visit(item)

    _visit(parameters)
    return found


def _install_capture() -> tuple[list[_Captured], Any]:
    captured: list[_Captured] = []
    pending_element: dict[str, ClauseElement | None] = {"last": None}

    def _before_execute(
        _conn: Any,
        clauseelement: ClauseElement,
        _multiparams: Any,
        _params: Any,
        _execution_options: Any,
    ) -> None:
        pending_element["last"] = clauseelement

    def _before_cursor(
        _conn: Any,
        _cursor: Any,
        statement: str,
        parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        clauseelement = pending_element["last"]
        pg_text = ""
        if clauseelement is not None:
            pg_text = _compile_pg(clauseelement).lower()
        captured.append(
            _Captured(statement.lower(), pg_text, _parameters_to_uuids(parameters))
        )

    event.listen(engine.sync_engine, "before_execute", _before_execute)
    event.listen(engine.sync_engine, "before_cursor_execute", _before_cursor)
    return captured, (_before_execute, _before_cursor)


def _uninstall_capture(handlers: Any) -> None:
    before_execute, before_cursor = handlers
    event.remove(engine.sync_engine, "before_execute", before_execute)
    event.remove(engine.sync_engine, "before_cursor_execute", before_cursor)


@pytest.mark.asyncio
@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="real PostgreSQL required")
@pytest.mark.parametrize("movement_side", ["source", "target"])
async def test_postgres_merge_replays_committed_movement_with_stale_balances(
    async_client: AsyncClient, movement_side: str,
) -> None:
    """Two real transactions: merge waits for a warehouse writer, then rereads."""
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, f"pg-{suffix}")
    response = await async_client.post("/sellers", headers=headers, json={"name": "Seller"})
    assert response.status_code == 201, response.text
    seller_id = response.json()["id"]
    tenant_id = await _seller_tenant_id(seller_id)
    location_id = await _create_warehouse_location(async_client, headers, suffix)
    target = await _create_product(
        async_client, headers, sku_code=f"pg-wb-{suffix}", seller_id=seller_id,
        wb_vendor_code=f"pg-vendor-{suffix}",
    )
    source = await _create_product(
        async_client, headers, sku_code=f"pg-oz-{suffix}", seller_id=seller_id,
    )
    target_id, source_id = uuid.UUID(target["id"]), uuid.UUID(source["id"])
    await _add_stock(tenant_id, target_id, location_id, 8)
    await _add_stock(tenant_id, source_id, location_id, 5)
    from app.models.inventory_movement import InventoryMovement

    async with SessionLocal() as merger, SessionLocal() as writer:
        # Keep ORM objects alive to exercise a caller that read old balances.
        stale = list((await merger.scalars(select(InventoryBalance))).all())
        assert sorted(row.quantity for row in stale) == [5, 8]
        merger_pid = await merger.scalar(text("select pg_backend_pid()"))
        await inventory_service.record_movement_and_adjust_balance(
            writer, tenant_id=tenant_id,
            product_id=source_id if movement_side == "source" else target_id,
            storage_location_id=location_id, quantity_delta=3,
            movement_type="inbound_intake",
            actor_user_id=await resolve_test_actor_user_id(writer, tenant_id),
        )
        merge_task = asyncio.create_task(merge_products(merger, tenant_id, [source_id, target_id]))
        try:
            async with asyncio.timeout(5):
                while not await writer.scalar(
                    text("select cardinality(pg_blocking_pids(:pid)) > 0"), {"pid": merger_pid},
                ):
                    assert not merge_task.done(), "merge failed to wait for the Product lock"
                    await asyncio.sleep(0.01)
            await writer.commit()
            merged = await asyncio.wait_for(merge_task, timeout=10)
            assert merged.id == target_id
        finally:
            if not merge_task.done():
                merge_task.cancel()
                await asyncio.gather(merge_task, return_exceptions=True)
    async with SessionLocal() as check:
        balances = list((await check.scalars(select(InventoryBalance))).all())
        movements = list((await check.scalars(select(InventoryMovement))).all())
        assert len(balances) == 1
        assert balances[0].product_id == target_id
        assert balances[0].quantity == 16
        assert sum(row.quantity_delta for row in movements) == 16
        assert len(movements) == 3
        assert all(row.product_id == target_id for row in movements)


@pytest.mark.asyncio
async def test_merge_takes_product_locks_in_ascending_id_order_input_forward(
    async_client: AsyncClient,
) -> None:
    """Product-lock идёт в порядке возрастания id, независимо от порядка входа.

    Вход: id в естественном порядке. FOR UPDATE в захваченных инструкциях
    появляется дважды, оба раза раньше любого чтения баланса, и параметры этих
    двух SELECT — это ровно сортированные по возрастанию id обеих карточек.
    """
    await _run_stable_lock_order_case(async_client, reverse_input=False)


@pytest.mark.asyncio
async def test_merge_takes_product_locks_in_ascending_id_order_input_reversed(
    async_client: AsyncClient,
) -> None:
    """Порядок блокировок остаётся возрастающим, даже когда клиент прислал наоборот.

    Именно это исключает встречный deadlock: два параллельных merge, получившие
    один и тот же набор id в разном порядке, всё равно выстраиваются в одну и ту
    же очередь блокировок.
    """
    await _run_stable_lock_order_case(async_client, reverse_input=True)


async def _run_stable_lock_order_case(
    async_client: AsyncClient, *, reverse_input: bool
) -> None:
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, f"order-{suffix}")
    seller_response = await async_client.post(
        "/sellers", headers=headers, json={"name": "Seller"}
    )
    assert seller_response.status_code == 201, seller_response.text
    seller_id = seller_response.json()["id"]
    tenant_id = await _seller_tenant_id(seller_id)
    location_id = await _create_warehouse_location(async_client, headers, suffix)

    wb_card = await _create_product(
        async_client,
        headers,
        sku_code=f"WMS349-WB-{suffix}",
        seller_id=seller_id,
        wb_vendor_code=f"WMS349-V-{suffix}",
    )
    ozon_card = await _create_product(
        async_client,
        headers,
        sku_code=f"WMS349-OZ-{suffix}",
        seller_id=seller_id,
    )
    await _add_stock(tenant_id, uuid.UUID(wb_card["id"]), location_id, 3)
    await _add_stock(tenant_id, uuid.UUID(ozon_card["id"]), location_id, 2)

    wb_id = uuid.UUID(wb_card["id"])
    ozon_id = uuid.UUID(ozon_card["id"])
    ordered_ids = sorted([wb_id, ozon_id])

    input_ids: list[uuid.UUID] = (
        list(reversed(ordered_ids)) if reverse_input else list(ordered_ids)
    )

    captured, handler = _install_capture()
    try:
        async with SessionLocal() as session:
            merged = await merge_products(session, tenant_id, input_ids)
    finally:
        _uninstall_capture(handler)

    # Merge отработал сам — этот тест не про регресс поведения, а про порядок,
    # но если бы сервис упал, весь захват был бы бессмыслен.
    assert merged.id in ordered_ids

    # Продуктовые SELECT'ы с FOR UPDATE, в том порядке, как они пошли на engine.
    product_for_update = [
        c for c in captured if c.kind == "product" and "for update" in c.pg_text
    ]
    assert len(product_for_update) >= 2, (
        "merge должен блокировать обе карточки, а не читать их обычным SELECT; "
        f"захвачено FOR UPDATE product SELECT'ов: {len(product_for_update)}"
    )

    # Первые два FOR UPDATE — это наши блокировки. Их фактические bind-параметры
    # (не переигранная компиляция, а то, что реально ушло на execute) должны
    # совпадать с ascending-сортировкой id.
    first_two = product_for_update[:2]
    locked_id_params: list[uuid.UUID] = []
    for stmt in first_two:
        # Из bind-параметров выбираем тот UUID, который относится к продукту.
        # Обычно там ещё есть tenant_id — отфильтровываем его.
        candidates = [u for u in stmt.bind_uuids if u != tenant_id]
        assert candidates, (
            f"не нашёл product-UUID в bind-параметрах SELECT: {stmt.bind_uuids}"
        )
        locked_id_params.append(candidates[0])
    assert locked_id_params == ordered_ids, (
        "merge берёт блокировки не в порядке возрастания id: "
        f"порядок захвата {locked_id_params}, ожидалось {ordered_ids}"
    )

    # И — главное — FOR UPDATE идёт до первого чтения баланса.
    first_lock_index = next(
        i
        for i, c in enumerate(captured)
        if c.kind == "product" and "for update" in c.pg_text
    )
    balance_indexes = [i for i, c in enumerate(captured) if c.kind == "balance"]
    assert balance_indexes, (
        "merge не сходил ни разу в inventory_balances — тест не покрывает исходный "
        "сценарий"
    )
    assert first_lock_index < balance_indexes[0], (
        "порядок разъехался: merge прочитал баланс раньше, чем взял Product-lock; "
        f"lock в позиции {first_lock_index}, первый balance в {balance_indexes[0]}"
    )


@pytest.mark.asyncio
async def test_merge_reads_balances_under_for_update_lock(
    async_client: AsyncClient,
) -> None:
    """Балансовые SELECT'ы тоже идут под FOR UPDATE.

    Product-lock уже сериализует конкурентную запись; дополнительный лок на
    балансовые строки исключает то, что новая строка появится между чтением и
    суммированием и не попадёт в свод.
    """
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, f"bal-{suffix}")
    seller_response = await async_client.post(
        "/sellers", headers=headers, json={"name": "Seller"}
    )
    assert seller_response.status_code == 201, seller_response.text
    seller_id = seller_response.json()["id"]
    tenant_id = await _seller_tenant_id(seller_id)
    location_id = await _create_warehouse_location(async_client, headers, suffix)

    wb_card = await _create_product(
        async_client,
        headers,
        sku_code=f"WMS349-BW-{suffix}",
        seller_id=seller_id,
        wb_vendor_code=f"WMS349-BV-{suffix}",
    )
    ozon_card = await _create_product(
        async_client,
        headers,
        sku_code=f"WMS349-BO-{suffix}",
        seller_id=seller_id,
    )
    await _add_stock(tenant_id, uuid.UUID(wb_card["id"]), location_id, 4)
    await _add_stock(tenant_id, uuid.UUID(ozon_card["id"]), location_id, 6)

    captured, handler = _install_capture()
    try:
        async with SessionLocal() as session:
            await merge_products(
                session,
                tenant_id,
                [uuid.UUID(wb_card["id"]), uuid.UUID(ozon_card["id"])],
            )
    finally:
        _uninstall_capture(handler)

    balance_for_update = [
        c for c in captured if c.kind == "balance" and "for update" in c.pg_text
    ]
    assert len(balance_for_update) >= 2, (
        "оба SELECT из inventory_balances должны идти под FOR UPDATE, "
        f"захвачено: {len(balance_for_update)}"
    )


@pytest.mark.asyncio
async def test_merge_still_sums_stock_end_to_end_after_lock_change(
    async_client: AsyncClient,
) -> None:
    """Регресс-щит: добавление блокировок не сломало итог по остаткам.

    Мы поменяли путь чтения — важно убедиться, что арифметика сложения
    остатков и переезд озоновской привязки на WB-карточку остались прежними.
    """
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, f"e2e-{suffix}")
    seller_response = await async_client.post(
        "/sellers", headers=headers, json={"name": "Seller"}
    )
    assert seller_response.status_code == 201, seller_response.text
    seller_id = seller_response.json()["id"]
    tenant_id = await _seller_tenant_id(seller_id)
    location_id = await _create_warehouse_location(async_client, headers, suffix)

    wb_card = await _create_product(
        async_client,
        headers,
        sku_code=f"WMS349-E2E-WB-{suffix}",
        seller_id=seller_id,
        wb_vendor_code=f"WMS349-E2E-V-{suffix}",
    )
    ozon_card = await _create_product(
        async_client,
        headers,
        sku_code=f"WMS349-E2E-OZ-{suffix}",
        seller_id=seller_id,
    )
    await _add_stock(tenant_id, uuid.UUID(wb_card["id"]), location_id, 8)
    await _add_stock(tenant_id, uuid.UUID(ozon_card["id"]), location_id, 5)

    async with SessionLocal() as session:
        merged = await merge_products(
            session,
            tenant_id,
            [uuid.UUID(ozon_card["id"]), uuid.UUID(wb_card["id"])],
        )
        assert merged.id == uuid.UUID(wb_card["id"])

    # Проверка суммы через модель, чтобы не зависеть от роутинга сводки.
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(InventoryBalance).where(
                    InventoryBalance.product_id == uuid.UUID(wb_card["id"])
                )
            )
        ).scalars().all()
        assert sum(r.quantity for r in rows) == 13


@pytest.mark.asyncio
async def test_merge_reports_missing_product_before_touching_balances(
    async_client: AsyncClient,
) -> None:
    """Отсутствующая карточка ловится на этапе блокировки, а не позже.

    Раньше "product_not_found" возвращался после общего чтения обоих продуктов
    без лока. Теперь мы блокируем по одному в возрастающем порядке — тест
    сторожит, что ошибочный сценарий не начинает читать балансы или связи.
    """
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, f"missing-{suffix}")
    seller_response = await async_client.post(
        "/sellers", headers=headers, json={"name": "Seller"}
    )
    assert seller_response.status_code == 201, seller_response.text
    seller_id = seller_response.json()["id"]
    tenant_id = await _seller_tenant_id(seller_id)
    real = await _create_product(
        async_client,
        headers,
        sku_code=f"WMS349-MISS-{suffix}",
        seller_id=seller_id,
    )
    missing_id = uuid.uuid4()

    captured, handler = _install_capture()
    try:
        async with SessionLocal() as session:
            from app.services.product_merge_service import ProductMergeError

            with pytest.raises(ProductMergeError) as excinfo:
                await merge_products(
                    session,
                    tenant_id,
                    [uuid.UUID(real["id"]), missing_id],
                )
            assert excinfo.value.code == "product_not_found"
    finally:
        _uninstall_capture(handler)

    balance_reads = [c for c in captured if c.kind == "balance"]
    assert not balance_reads, (
        "при отсутствующей карточке merge не должен ходить в inventory_balances; "
        f"попал: {[c.text for c in balance_reads]}"
    )
