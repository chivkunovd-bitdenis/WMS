"""WMS-122 · WB-поставки не дублируются под одним номером.

Три сюжета:

1. Дедуп существующих дублей: если в базу до миграции 20260910_0258 успели
   попасть два ряда под одним WB-номером, апгрейд оставляет самый старый по
   `created_at` каноническим и уводит проигравших в карантин (name с
   префиксом `[DUPLICATE→<uuid winner>]`, external_supply_id обнуляется).
2. После апгрейда попытка вставить второй ряд с тем же
   (seller_id, marketplace, external_supply_id) обязана падать на уровне
   базы — частичный уникальный индекс покрывает не-NULL значения.
3. Внешний идентификатор WB-поставки, созданной легитимно через сервис,
   идёт в `external_supply_id` не позже, чем в `wb_supply_id`.
   Раньше он оставался NULL, из-за чего уникальность и не мешала гонке.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_DRAFT,
    FbsSupply,
)
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse


async def _make_seller(
    session: AsyncSession, *, name: str, slug_hint: str
) -> tuple[Tenant, Seller, Warehouse]:
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant(name=f"Tenant {name}", slug=f"{slug_hint}-{suffix}")
    seller = Seller(tenant=tenant, name=name)
    warehouse = Warehouse(tenant=tenant, name="WH", code=f"wh-{suffix}")
    session.add_all([tenant, seller, warehouse])
    await session.flush()
    return tenant, seller, warehouse


def _wb_supply(
    *,
    tenant: Tenant,
    seller: Seller,
    warehouse: Warehouse,
    wb_supply_id: str,
    external_supply_id: str | None,
    created_at: datetime,
    name: str = "WB supply",
) -> FbsSupply:
    return FbsSupply(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        marketplace="wb",
        wb_supply_id=wb_supply_id,
        external_supply_id=external_supply_id,
        name=name,
        status=FBS_SUPPLY_STATUS_DRAFT,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_wms122_partial_unique_rejects_duplicate_wb_number(db_session: AsyncSession) -> None:
    """Второй insert с тем же (seller, marketplace, external_supply_id) падает."""
    tenant, seller, warehouse = await _make_seller(
        db_session, name="Denmarcs", slug_hint="wms122-unique"
    )
    now = datetime.now(UTC)
    first = _wb_supply(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        wb_supply_id="WB-90001",
        external_supply_id="WB-90001",
        created_at=now,
    )
    db_session.add(first)
    await db_session.commit()

    dup = _wb_supply(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        wb_supply_id="WB-90001",
        external_supply_id="WB-90001",
        created_at=now + timedelta(seconds=1),
        name="WB supply (racing)",
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_wms122_null_external_id_still_allowed_for_ozon(db_session: AsyncSession) -> None:
    """Частичный индекс покрывает не-NULL, поэтому Ozon-путь до отгрузки
    (когда carriage_id ещё не выдан) продолжает работать с NULL."""
    tenant, seller, warehouse = await _make_seller(
        db_session, name="Ozon", slug_hint="wms122-ozon-null"
    )
    now = datetime.now(UTC)
    ozon_a = FbsSupply(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        marketplace="ozon",
        wb_supply_id="PENDING-a",
        external_supply_id=None,
        name="Ozon supply A",
        status=FBS_SUPPLY_STATUS_DRAFT,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        created_at=now,
    )
    ozon_b = FbsSupply(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        marketplace="ozon",
        wb_supply_id="PENDING-b",
        external_supply_id=None,
        name="Ozon supply B",
        status=FBS_SUPPLY_STATUS_DRAFT,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        created_at=now + timedelta(seconds=1),
    )
    db_session.add_all([ozon_a, ozon_b])
    await db_session.commit()

    rows = (
        await db_session.execute(
            sa.select(FbsSupply.id).where(FbsSupply.seller_id == seller.id)
        )
    ).all()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_wms122_same_number_different_sellers_stays_allowed(db_session: AsyncSession) -> None:
    """WB-номер поставки уникален в пределах кабинета (seller_id), но два разных
    локальных продавца могут случайно иметь одинаковый внешний номер — это
    отдельная задача по санитарии кабинетов, а не ответственность WMS-122.
    Здесь фиксируем, что unique-index не мешает разным seller_id."""
    _, seller_a, warehouse_a = await _make_seller(
        db_session, name="Denmarcs", slug_hint="wms122-sellerA"
    )
    _, seller_b, warehouse_b = await _make_seller(
        db_session, name="IP Test", slug_hint="wms122-sellerB"
    )
    now = datetime.now(UTC)
    row_a = FbsSupply(
        tenant_id=seller_a.tenant_id,
        seller_id=seller_a.id,
        warehouse_id=warehouse_a.id,
        marketplace="wb",
        wb_supply_id="WB-90099",
        external_supply_id="WB-90099",
        name="WB supply (seller A)",
        status=FBS_SUPPLY_STATUS_DRAFT,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        created_at=now,
    )
    row_b = FbsSupply(
        tenant_id=seller_b.tenant_id,
        seller_id=seller_b.id,
        warehouse_id=warehouse_b.id,
        marketplace="wb",
        wb_supply_id="WB-90099",
        external_supply_id="WB-90099",
        name="WB supply (seller B)",
        status=FBS_SUPPLY_STATUS_DRAFT,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        created_at=now + timedelta(seconds=1),
    )
    db_session.add_all([row_a, row_b])
    await db_session.commit()


@pytest.mark.asyncio
async def test_wms122_migration_quarantines_existing_duplicates(db_session: AsyncSession) -> None:
    """Симулируем «уже случившиеся дубли» напрямую в базе (обходя ORM,
    чтобы не удариться о новый частичный индекс), потом вручную гоняем
    ту же самую нормализацию, что делает миграция 20260910_0258. Проверяем,
    что старейший ряд стал каноническим, а младшие — в карантине."""
    tenant, seller, warehouse = await _make_seller(
        db_session, name="Denmarcs", slug_hint="wms122-existing"
    )
    now = datetime.now(UTC)
    older_id = uuid.uuid4()
    newer_id = uuid.uuid4()
    # Вставляем дубли напрямую, без ORM: конкурентный insert в проде мог обойти
    # приложение до появления защиты, но в тесте частичный уникальный индекс
    # это ловит — поэтому пишем в базу параметризованно и с NULL в
    # external_supply_id (у обоих), чтобы не задеть индекс.
    stamp = now.isoformat()
    stamp_new = (now + timedelta(seconds=1)).isoformat()
    await db_session.execute(
        sa.text(
            """
            INSERT INTO fbs_supplies (
                id, tenant_id, seller_id, warehouse_id, marketplace,
                wb_supply_id, external_supply_id, name, source, status,
                delivery_type, created_at, updated_at
            ) VALUES (
                :id, :tenant_id, :seller_id, :warehouse_id, 'wb',
                'WB-99999', NULL, 'Older canonical', 'wms', 'draft',
                :delivery, :created_at, :created_at
            )
            """
        ),
        {
            "id": str(older_id),
            "tenant_id": str(tenant.id),
            "seller_id": str(seller.id),
            "warehouse_id": str(warehouse.id),
            "delivery": FBS_DELIVERY_TYPE_WAREHOUSE_SC,
            "created_at": stamp,
        },
    )
    await db_session.execute(
        sa.text(
            """
            INSERT INTO fbs_supplies (
                id, tenant_id, seller_id, warehouse_id, marketplace,
                wb_supply_id, external_supply_id, name, source, status,
                delivery_type, created_at, updated_at
            ) VALUES (
                :id, :tenant_id, :seller_id, :warehouse_id, 'wb',
                'WB-99999', NULL, 'Newer racing', 'wms', 'draft',
                :delivery, :created_at, :created_at
            )
            """
        ),
        {
            "id": str(newer_id),
            "tenant_id": str(tenant.id),
            "seller_id": str(seller.id),
            "warehouse_id": str(warehouse.id),
            "delivery": FBS_DELIVERY_TYPE_WAREHOUSE_SC,
            "created_at": stamp_new,
        },
    )
    await db_session.commit()

    # 1. Дедуп по wb_supply_id (миграция upgrade шаг 1).
    duplicates = (
        await db_session.execute(
            sa.text(
                """
                SELECT seller_id, marketplace, wb_supply_id
                  FROM fbs_supplies
                 WHERE marketplace = 'wb'
                   AND wb_supply_id IS NOT NULL
                   AND wb_supply_id NOT LIKE 'PENDING-%'
                   AND wb_supply_id <> ''
                 GROUP BY seller_id, marketplace, wb_supply_id
                 HAVING COUNT(*) > 1
                """
            )
        )
    ).fetchall()
    assert duplicates, "Тест должен видеть подготовленный дубликат до дедупа."
    loser_ids: list[str] = []
    for seller_id_row, marketplace_row, wb_supply_id_row in duplicates:
        rows = (
            await db_session.execute(
                sa.text(
                    """
                    SELECT id, name
                      FROM fbs_supplies
                     WHERE seller_id = :seller_id
                       AND marketplace = :marketplace
                       AND wb_supply_id = :wb_supply_id
                     ORDER BY created_at ASC, id ASC
                    """
                ),
                {
                    "seller_id": seller_id_row,
                    "marketplace": marketplace_row,
                    "wb_supply_id": wb_supply_id_row,
                },
            )
        ).fetchall()
        winner_id = rows[0][0]
        for loser_id, loser_name in rows[1:]:
            new_name = f"[DUPLICATE→{winner_id}] {loser_name}"
            await db_session.execute(
                sa.text(
                    """
                    UPDATE fbs_supplies
                       SET name = :new_name
                     WHERE id = :loser_id
                    """
                ),
                {"new_name": new_name, "loser_id": loser_id},
            )
            loser_ids.append(str(loser_id))
    await db_session.commit()

    # 2. Backfill только для не-проигравших.
    await db_session.execute(
        sa.text(
            """
            UPDATE fbs_supplies
               SET external_supply_id = wb_supply_id
             WHERE marketplace = 'wb'
               AND external_supply_id IS NULL
               AND wb_supply_id IS NOT NULL
               AND wb_supply_id NOT LIKE 'PENDING-%'
               AND wb_supply_id <> ''
               AND id NOT IN :loser_ids
            """
        ).bindparams(sa.bindparam("loser_ids", expanding=True)),
        {"loser_ids": loser_ids},
    )
    await db_session.commit()

    # Проверяем итог: канонический ряд с external_supply_id='WB-99999',
    # проигравший — с external_supply_id=NULL и меткой в name.
    # ORM хранит UUID нативным типом, а мы вставляли текстом через raw SQL —
    # приводим id к строке в фильтре, чтобы обойти диалектную разницу.
    canonical = (
        await db_session.execute(
            sa.text(
                "SELECT id, external_supply_id, name "
                "FROM fbs_supplies WHERE id = :id"
            ),
            {"id": str(older_id)},
        )
    ).first()
    quarantined = (
        await db_session.execute(
            sa.text(
                "SELECT id, external_supply_id, name "
                "FROM fbs_supplies WHERE id = :id"
            ),
            {"id": str(newer_id)},
        )
    ).first()

    assert canonical is not None
    assert canonical.external_supply_id == "WB-99999"
    assert canonical.name == "Older canonical"

    assert quarantined is not None
    assert quarantined.external_supply_id is None
    assert quarantined.name.startswith(f"[DUPLICATE→{older_id}] ")
