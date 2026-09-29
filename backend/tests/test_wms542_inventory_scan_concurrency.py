"""WMS-542 C2: two operators scanning the same already-expected line, real PG only.

Isolated test DB only, mirrors tests/test_wms153_count_post_concurrency.py.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text

from app.db.session import SessionLocal, engine
from app.models.inventory_count import InventoryCount, InventoryCountFoundScan, InventoryCountLine
from app.models.product import Product
from app.services import inventory_count_service as counts
from tests.test_inventory_counts import _balance, _product, _tenant
from tests.test_wms156_discrepancy_concurrency import _wait_blocked

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(
    engine.dialect.name != "postgresql", reason="real PostgreSQL required",
)]


async def test_two_concurrent_scans_of_the_same_expected_line_both_count(
    async_client: AsyncClient,
) -> None:
    """Два оператора одновременно сканируют один и тот же товар в одном месте.

    Строка уже числится по учёту (создана вместе с документом, не находкой,
    как в остальных тестах record_found). record_found блокирует документ
    (`with_for_update`) на всё время записи: второй запрос обязан дождаться
    коммита первого, перечитать строку и прибавить свою штуку поверх уже
    увеличенного значения, а не поверх устаревшего прочтения. Ни одна из двух
    штук не теряется и не задваивается сверх двух — ровно то, что требует R3.
    """
    setup = await _tenant(async_client, "ScanRaceCount")
    counted = await _product(async_client, setup, name="Гонка сканов")
    await _balance(setup, counted, 5)
    async with SessionLocal() as session:
        product = await session.get(Product, counted)
        assert product is not None
        product.wb_barcode = "4600000009999"
        await session.commit()

    created = await async_client.post(
        "/operations/inventory-counts",
        headers=setup.headers,
        json={"source": "planned", "filters": {}},
    )
    assert created.status_code == 201, created.text
    count_id = uuid.UUID(created.json()["id"])
    seeded_line = next(
        line for line in created.json()["lines"] if line["product_id"] == str(counted)
    )
    assert seeded_line["expected_quantity"] == 5
    assert seeded_line["actual_quantity"] is None

    async with SessionLocal() as first, SessionLocal() as second:
        # Первый оператор пришёл первым: держит блокировку документа ещё до
        # того, как второй вообще начал свой запрос — так гонка выстроена
        # детерминированно, а не «как повезёт с планировщиком».
        await first.execute(
            select(InventoryCount).where(InventoryCount.id == count_id).with_for_update()
        )
        pid = await second.scalar(text("select pg_backend_pid()"))
        second_task = asyncio.create_task(counts.record_found(
            second, setup.tenant_id, count_id,
            barcodes=["4600000009999"], cell_id=setup.location_id,
            container_kind=None, container_id=None, scan_id="scan-race-operator-b",
        ))
        try:
            # Второй оператор реально стоит на чужой блокировке в Postgres —
            # не просто "ещё не успел", а физически заблокирован сервером.
            await _wait_blocked(first, pid, second_task)

            first_result = await counts.record_found(
                first, setup.tenant_id, count_id,
                barcodes=["4600000009999"], cell_id=setup.location_id,
                container_kind=None, container_id=None, scan_id="scan-race-operator-a",
            )
            assert first_result.expected_quantity == 5
            assert first_result.notice == ""

            # Освободили блокировку коммитом первого скана — второй теперь
            # проходит, перечитывает уже увеличенную строку и прибавляет свою.
            second_result = await asyncio.wait_for(second_task, 10)
            assert second_result.expected_quantity == 5
            assert second_result.notice == ""
        finally:
            if not second_task.done():
                second_task.cancel()
                await asyncio.gather(second_task, return_exceptions=True)

    async with SessionLocal() as check:
        line = await check.scalar(select(InventoryCountLine).where(
            InventoryCountLine.count_id == count_id,
            InventoryCountLine.product_id == counted,
        ))
        assert line is not None
        assert line.id == uuid.UUID(seeded_line["id"]), "скан не должен плодить вторую строку"
        assert line.actual_quantity == 2, "оба скана обязаны быть учтены, ни один не потерян"
        scans = await check.scalar(select(func.count(InventoryCountFoundScan.id)).where(
            InventoryCountFoundScan.count_id == count_id,
        ))
        assert scans == 2, "у каждого скана свой scan_id — обе записи должны сохраниться"
