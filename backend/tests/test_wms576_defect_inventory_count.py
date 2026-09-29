"""WMS-576: инвентаризация брака должна проходить под защитой WMS-516.

Ревью 28.09.2026 (docs/reviews/artifacts/release-audit-20260928/review-astra-rest.md,
REST-03) нашло, что защита служебных складов WMS-516 блокирует ровно ту
инвентаризацию брака, которую WMS-530 R1/R9/R11 прямо предусматривает: брак
считается остатком и должен пересчитываться как любое другое место. Разрешение
`defect_service_write` было установлено только на запись строк документа
(`_add_count_lines`), а заголовок документа, сохранение факта (`save_actuals`)
и проведение (`post_count`) писали в те же физически защищённые таблицы без
разрешения и падали с `physical_warehouse_required`.

Оба сценария из находки воспроизведены с настоящими штатными ограничениями
(`install_guards`), как и в `test_wms516_physical_warehouse.py`, плюс
проведение, которое ревью не успело проверить, потому что сценарий обрывался
раньше.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.physical_warehouse_guard import install_guards, remove_guards
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services import inventory_count_service as svc
from app.services.defect_warehouse_service import get_or_create_defect_location


async def _seed(session):
    tenant = Tenant(name="Fixture", slug=uuid.uuid4().hex)
    session.add(tenant)
    await session.flush()
    seller = Seller(tenant_id=tenant.id, name="Owner")
    warehouse = Warehouse(tenant_id=tenant.id, name="Physical", code="physical")
    actor = User(tenant_id=tenant.id, role="ff_admin", password_hash="test-only")
    session.add_all([seller, warehouse, actor])
    await session.flush()
    location = StorageLocation(tenant_id=tenant.id, warehouse_id=warehouse.id,
                               code="A1", barcode=f"A1-{uuid.uuid4().hex}")
    session.add(location)
    await session.flush()
    product = Product(tenant_id=tenant.id, seller_id=seller.id, name="Defective",
                      sku_code=f"sku-{uuid.uuid4().hex[:10]}")
    session.add(product)
    await session.flush()
    defect = await get_or_create_defect_location(session, tenant.id)
    await session.commit()
    return tenant, seller, warehouse, location, actor, product, defect


def _balance(tenant_id, product_id, location_id, quantity):
    # quantity_unpacked must mirror quantity: the deduction UPDATE checks
    # unpacked + packed, not the denormalized `quantity` column alone.
    return InventoryBalance(
        tenant_id=tenant_id, product_id=product_id, storage_location_id=location_id,
        quantity=quantity, quantity_unpacked=quantity, quantity_packed=0,
    )


async def _install(session):
    await (await session.connection()).run_sync(install_guards)
    await session.commit()


async def _cleanup(session):
    await session.rollback()
    await (await session.connection()).run_sync(remove_guards)
    await session.commit()


async def test_wms576_scenario1_whole_product_count_of_pure_defect_stock(db_session):
    """Сценарий 1 находки: у товара остались только 2 штуки брака.

    Инвентаризация по всему остатку товара должна создать документ, а не
    упасть на вставке заголовка (physical_warehouse_required).
    """
    session = db_session
    tenant, _seller, _warehouse, _location, actor, product, defect = await _seed(session)
    session.add(_balance(tenant.id, product.id, defect.id, 2))
    await session.commit()
    await _install(session)
    try:
        count = await svc.create_count(
            session, tenant.id, actor.id,
            source=svc.SOURCE_OBJECT,
            object_scope=svc.CountObject(type="product", id=product.id),
            filters=None,
            comment=None,
        )
        assert count.status == svc.STATUS_DRAFT
        assert len(count.lines) == 1
        line = count.lines[0]
        assert line.storage_location_id == defect.id
        assert line.expected_quantity == 2
    finally:
        await _cleanup(session)


async def test_wms576_scenario2_save_actuals_recounts_defect_line(db_session):
    """Сценарий 2 находки: 3 штуки в обычной ячейке и 2 штуки брака.

    Документ создаётся с двумя строками (создание строк уже было разрешено
    декоратором). Ввод факта по строке брака (2 -> 1) должен сохраниться, а
    не упасть на UPDATE inventory_count_lines.
    """
    session = db_session
    tenant, _seller, _warehouse, location, actor, product, defect = await _seed(session)
    session.add_all([
        _balance(tenant.id, product.id, location.id, 3),
        _balance(tenant.id, product.id, defect.id, 2),
    ])
    await session.commit()
    await _install(session)
    try:
        count = await svc.create_count(
            session, tenant.id, actor.id,
            source=svc.SOURCE_OBJECT,
            object_scope=svc.CountObject(type="product", id=product.id),
            filters=None,
            comment=None,
        )
        assert len(count.lines) == 2
        defect_line = next(line for line in count.lines
                           if line.storage_location_id == defect.id)
        updated = await svc.save_actuals(
            session, tenant.id, count.id, [(defect_line.id, 1)],
        )
        saved_line = next(line for line in updated.lines if line.id == defect_line.id)
        assert saved_line.actual_quantity == 1
    finally:
        await _cleanup(session)


async def test_wms576_post_count_posts_defect_recount(db_session):
    """Проведение документа, затрагивающего брак, должно тоже пройти под защитой.

    Ревью не успело проверить эту часть, потому что сценарий обрывался раньше
    (REST-03: «Проведение после неудачного сохранения не проверялось»).
    Здесь доходим до конца: создание, сохранение факта и проведение — весь
    цикл одной операции.
    """
    session = db_session
    tenant, _seller, _warehouse, location, actor, product, defect = await _seed(session)
    session.add_all([
        _balance(tenant.id, product.id, location.id, 3),
        _balance(tenant.id, product.id, defect.id, 2),
    ])
    await session.commit()
    await _install(session)
    try:
        count = await svc.create_count(
            session, tenant.id, actor.id,
            source=svc.SOURCE_OBJECT,
            object_scope=svc.CountObject(type="product", id=product.id),
            filters=None,
            comment=None,
        )
        defect_line = next(line for line in count.lines
                           if line.storage_location_id == defect.id)
        normal_line = next(line for line in count.lines
                           if line.storage_location_id == location.id)
        await svc.save_actuals(
            session, tenant.id, count.id,
            [(defect_line.id, 1), (normal_line.id, 3)],
        )
        result = await svc.post_count(session, tenant.id, count.id, actor.id)
        assert result.count.status == svc.STATUS_POSTED
        assert result.posted_lines == 1
        defect_balance = await session.scalar(
            select(InventoryBalance.quantity).where(
                InventoryBalance.tenant_id == tenant.id,
                InventoryBalance.product_id == product.id,
                InventoryBalance.storage_location_id == defect.id,
            )
        )
        assert defect_balance == 1
        normal_balance = await session.scalar(
            select(InventoryBalance.quantity).where(
                InventoryBalance.tenant_id == tenant.id,
                InventoryBalance.product_id == product.id,
                InventoryBalance.storage_location_id == location.id,
            )
        )
        assert normal_balance == 3
    finally:
        await _cleanup(session)


async def test_wms576_scan_recounts_pure_defect_stock_and_posts(db_session):
    """Итоговое ревью, REST-N01: скан по документу брака, где остаток — только брак.

    create_count по товару с остатком только в __DEFECT__ сразу заводит одну
    строку (её заводить разрешено ещё в первой части WMS-576). Каждый
    следующий скан этой строки идёт по ветке «строка уже есть»
    (record_found: existing.actual_quantity += 1, запись в
    inventory_count_found_scans) — именно она падала physical_warehouse_required
    без разрешения. Сценарий из находки: скан, повтор того же scan_id
    (идемпотентность, без второй записи), следующий скан, затем проведение.
    """
    session = db_session
    tenant, _seller, _warehouse, _location, actor, product, defect = await _seed(session)
    session.add(_balance(tenant.id, product.id, defect.id, 3))
    await session.commit()
    await _install(session)
    try:
        count = await svc.create_count(
            session, tenant.id, actor.id,
            source=svc.SOURCE_OBJECT,
            object_scope=svc.CountObject(type="product", id=product.id),
            filters=None,
            comment=None,
        )
        assert len(count.lines) == 1
        line_id = count.lines[0].id
        first_scan = str(uuid.uuid4())
        result = await svc.record_found(
            session, tenant.id, count.id, barcodes=[product.sku_code],
            cell_id=defect.id, container_kind=None, container_id=None,
            scan_id=first_scan, line_id=line_id,
        )
        assert result.count.lines[0].actual_quantity == 1
        # Повтор того же scan_id — идемпотентность, штука не прибавляется второй раз.
        repeat = await svc.record_found(
            session, tenant.id, count.id, barcodes=[product.sku_code],
            cell_id=defect.id, container_kind=None, container_id=None,
            scan_id=first_scan, line_id=line_id,
        )
        assert repeat.count.lines[0].actual_quantity == 1
        # Следующий скан — новый scan_id, штука прибавляется.
        second = await svc.record_found(
            session, tenant.id, count.id, barcodes=[product.sku_code],
            cell_id=defect.id, container_kind=None, container_id=None,
            scan_id=str(uuid.uuid4()), line_id=line_id,
        )
        assert second.count.lines[0].actual_quantity == 2
        posted = await svc.post_count(session, tenant.id, count.id, actor.id)
        assert posted.count.status == svc.STATUS_POSTED
        balance = await session.scalar(
            select(InventoryBalance.quantity).where(
                InventoryBalance.tenant_id == tenant.id,
                InventoryBalance.product_id == product.id,
                InventoryBalance.storage_location_id == defect.id,
            )
        )
        assert balance == 2
    finally:
        await _cleanup(session)


async def test_wms576_record_found_new_line_on_pure_defect_stock(db_session):
    """REST-N01: скан товара, которого ещё нет в документе, а адрес — __DEFECT__.

    Отдельная ветка от инкремента существующей строки (предыдущий тест):
    record_found заводит НОВУЮ строку (INSERT inventory_count_lines) и её
    скан (INSERT inventory_count_found_scans) — оба тоже должны быть под
    разрешением, а не только вставка при create_count.
    """
    session = db_session
    tenant, seller, _warehouse, _location, actor, product, defect = await _seed(session)
    other_product = Product(tenant_id=tenant.id, seller_id=seller.id, name="Other defective",
                            sku_code=f"sku-{uuid.uuid4().hex[:10]}")
    session.add(other_product)
    await session.flush()
    session.add(_balance(tenant.id, other_product.id, defect.id, 1))
    session.add(_balance(tenant.id, product.id, defect.id, 3))
    await session.commit()
    await _install(session)
    try:
        count = await svc.create_count(
            session, tenant.id, actor.id,
            source=svc.SOURCE_OBJECT,
            object_scope=svc.CountObject(type="product", id=other_product.id),
            filters=None,
            comment=None,
        )
        # Документ заведён по другому товару, но его единственный остаток —
        # тоже брак, поэтому его склад — тот же __DEFECT__, и сканировать
        # ячейку брака в него можно (_resolve_found_location сверяет склад).
        assert count.warehouse_id == defect.warehouse_id
        assert len(count.lines) == 1
        assert count.lines[0].product_id == other_product.id
        result = await svc.record_found(
            session, tenant.id, count.id, barcodes=[product.sku_code],
            cell_id=defect.id, container_kind=None, container_id=None,
            scan_id=str(uuid.uuid4()), line_id=None,
        )
        assert result.expected_quantity == 3
        found_lines = [ln for ln in result.count.lines if ln.product_id == product.id]
        assert len(found_lines) == 1
        assert found_lines[0].actual_quantity == 1
        assert found_lines[0].storage_location_id == defect.id
    finally:
        await _cleanup(session)


async def test_wms576_cancel_pure_defect_count(db_session):
    """Итоговое ревью, REST-N02: отмена документа брака.

    count.status = STATUS_CANCELLED — тоже UPDATE строки inventory_counts,
    которая уже ссылается на __DEFECT__ (заведена как разрешённая запись в
    create_count), и без разрешения падает так же, как проведение до
    исправления.
    """
    session = db_session
    tenant, _seller, _warehouse, _location, actor, product, defect = await _seed(session)
    session.add(_balance(tenant.id, product.id, defect.id, 2))
    await session.commit()
    await _install(session)
    try:
        count = await svc.create_count(
            session, tenant.id, actor.id,
            source=svc.SOURCE_OBJECT,
            object_scope=svc.CountObject(type="product", id=product.id),
            filters=None,
            comment=None,
        )
        cancelled = await svc.cancel_count(session, tenant.id, count.id)
        assert cancelled.status == svc.STATUS_CANCELLED
        reloaded = await svc.get_count(session, tenant.id, count.id)
        assert reloaded is not None
        assert reloaded.status == svc.STATUS_CANCELLED
        balance = await session.scalar(
            select(InventoryBalance.quantity).where(
                InventoryBalance.tenant_id == tenant.id,
                InventoryBalance.product_id == product.id,
                InventoryBalance.storage_location_id == defect.id,
            )
        )
        assert balance == 2
    finally:
        await _cleanup(session)


async def test_wms576_guard_still_blocks_unpermitted_defect_write(db_session):
    """Контроль: защита не отключена глобально — прямая запись без разрешения падает."""
    session = db_session
    tenant, _seller, _warehouse, _location, _actor, product, defect = await _seed(session)
    await _install(session)
    try:
        with pytest.raises(IntegrityError, match="physical_warehouse_required"):
            async with session.begin_nested():
                session.add(InventoryBalance(tenant_id=tenant.id, product_id=product.id,
                                             storage_location_id=defect.id, quantity=5))
                await session.flush()
    finally:
        await _cleanup(session)
