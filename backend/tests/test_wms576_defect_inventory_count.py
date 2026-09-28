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
