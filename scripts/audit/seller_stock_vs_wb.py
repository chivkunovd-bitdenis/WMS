"""Сверка: сколько товара числится у нас и сколько стоит в кабинете WB.

Запускается на боевом сервере, только на чтение: ни одной записи в базу и ни
одного изменения в кабинете продавца. Нужен, когда маркетплейс продолжает
продавать товар, которого на складе физически нет.

Как пользоваться на боевом сервере, ничего там не меняя:

    cd /opt/wms                     # корень репозитория на сервере
    git fetch origin staging
    git show origin/staging:scripts/audit/seller_stock_vs_wb.py > /tmp/sverka.py
    PYTHONPATH=backend backend/.venv/bin/python /tmp/sverka.py "Чжоу"

Выкачка файла через `git show` не трогает рабочую копию: боевой код остаётся на
своей ветке, скрипт живёт во временной папке.

Можно передать часть названия — скрипт покажет всех подходящих продавцов, если
их окажется несколько, и ничего не сделает.

Что печатает по каждому складу WB продавца:

    товар · артикул · chrtId · у нас на складе · в кабинете WB · расхождение

«У нас» — это физический остаток по всем ячейкам склада фулфилмента, без
резервов. «В кабинете WB» — то, что маркетплейс отдаёт прямо сейчас по своей
ручке остатков. Расхождение со знаком плюс значит, что WB продаёт то, чего у
нас нет: именно эти строки и надо занулять.
"""

from __future__ import annotations

import asyncio
import sys
import uuid

import httpx
from app.db.session import SessionLocal
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.services.fbs_stock_sync_service import _resolve_marketplace_api_token
from app.services.wildberries_client import (
    WildberriesClientError,
    fetch_marketplace_stocks,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# WB принимает ограниченную пачку артикулов за один запрос.
CHRT_BATCH = 1000


async def _find_sellers(session: AsyncSession, needle: str) -> list[Seller]:
    rows = await session.scalars(
        select(Seller).where(Seller.name.ilike(f"%{needle}%")).order_by(Seller.name)
    )
    return list(rows.all())


async def _our_stock(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> dict[uuid.UUID, int]:
    """Физический остаток по каждому товару продавца, сложенный по всем ячейкам."""
    rows = await session.execute(
        select(
            InventoryBalance.product_id,
            func.coalesce(func.sum(InventoryBalance.quantity), 0),
        )
        .join(Product, Product.id == InventoryBalance.product_id)
        .join(StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            Product.seller_id == seller_id,
        )
        .group_by(InventoryBalance.product_id)
    )
    return {product_id: int(quantity) for product_id, quantity in rows.all()}


async def main(needle: str) -> int:
    async with SessionLocal() as session:
        sellers = await _find_sellers(session, needle)
        if not sellers:
            print(f"Продавец по запросу «{needle}» не найден.")
            return 1
        if len(sellers) > 1:
            print(f"Под «{needle}» подходит несколько продавцов, уточните:")
            for seller in sellers:
                print(f"  · {seller.name}")
            return 1

        seller = sellers[0]
        print(f"Продавец: {seller.name}  ({seller.id})")

        products = list(
            (
                await session.scalars(
                    select(Product).where(
                        Product.tenant_id == seller.tenant_id,
                        Product.seller_id == seller.id,
                    )
                )
            ).all()
        )
        by_chrt = {int(p.wb_chrt_id): p for p in products if p.wb_chrt_id is not None}
        without_chrt = [p for p in products if p.wb_chrt_id is None]
        print(f"Товаров всего: {len(products)}, из них с артикулом WB: {len(by_chrt)}")
        if without_chrt:
            print(f"Без артикула WB (сверить нечем): {len(without_chrt)}")

        ours = await _our_stock(session, seller.tenant_id, seller.id)

        bindings = list(
            (
                await session.scalars(
                    select(FbsWarehouseBinding).where(
                        FbsWarehouseBinding.tenant_id == seller.tenant_id,
                        FbsWarehouseBinding.seller_id == seller.id,
                        FbsWarehouseBinding.is_active.is_(True),
                    )
                )
            ).all()
        )
        if not bindings:
            print("У продавца нет ни одного активного склада WB в системе.")
            return 1

        try:
            token = await _resolve_marketplace_api_token(session, seller.tenant_id, seller.id)
        except Exception as exc:  # noqa: BLE001
            print(f"Не удалось получить токен WB продавца: {exc}")
            return 1

        chrt_ids = sorted(by_chrt)
        async with httpx.AsyncClient() as http_client:
            for binding in bindings:
                print()
                print(f"=== Склад WB {binding.wb_warehouse_id} ===")
                print(
                    "    публикация остатков: "
                    + ("включена" if binding.stock_sync_enabled else "выключена")
                )
                amounts: dict[int, int] = {}
                failed = False
                for start in range(0, len(chrt_ids), CHRT_BATCH):
                    batch = chrt_ids[start : start + CHRT_BATCH]
                    try:
                        rows = await fetch_marketplace_stocks(
                            http_client,
                            api_token=token,
                            warehouse_id=int(binding.wb_warehouse_id),
                            chrt_ids=batch,
                        )
                    except WildberriesClientError as exc:
                        print(f"    WB не ответил по этому складу: {exc}")
                        failed = True
                        break
                    for row in rows:
                        amounts[int(row.chrt_id)] = int(row.amount)
                if failed:
                    continue

                header = (
                    f"{'Артикул продавца':<24} {'chrtId':>12} "
                    f"{'у нас':>8} {'в WB':>8} {'расхождение':>12}"
                )
                print(header)
                print("-" * len(header))
                total_gap = 0
                shown = 0
                for chrt_id in chrt_ids:
                    in_wb = amounts.get(chrt_id, 0)
                    product = by_chrt[chrt_id]
                    at_us = ours.get(product.id, 0)
                    gap = in_wb - at_us
                    if in_wb == 0 and at_us == 0:
                        continue
                    shown += 1
                    total_gap += max(0, gap)
                    print(
                        f"{product.sku_code[:24]:<24} {chrt_id:>12} "
                        f"{at_us:>8} {in_wb:>8} {gap:>+12}"
                    )
                if shown == 0:
                    print("    ни у нас, ни в WB остатков нет")
                else:
                    print("-" * len(header))
                    print(f"    WB продаёт сверх нашего остатка суммарно: {total_gap} шт")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Укажите продавца, например: python -m scripts.audit.seller_stock_vs_wb "Чжоу"')
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1])))
