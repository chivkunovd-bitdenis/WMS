"""Проценты свободного остатка либо выделенное доступное ФБС (WMS-060)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product import Product
from app.services import stock_direction_service
from app.services.fbs_stock_availability_service import fbs_stock_breakdown_by_product
from app.services.fbs_stock_publish_service import schedule_seller_stock_publish

# Доли задаются ползунком с шагом в десять процентов: промежуточные значения
# оператору не нужны, а круглые числа он читает не считая.
PERCENT_STEP = 10
PERCENT_MAX = 100


class FbsStockRuleError(Exception):
    def __init__(
        self,
        code: str,
        *,
        message: str | None = None,
        context: dict[str, object] | None = None,
    ) -> None:
        self.code = code
        self.message = message or code
        self.context = context or {}
        super().__init__(self.message)


@dataclass(frozen=True)
class FbsRule:
    """Правило публикации остатка по одному товару."""

    publish: bool
    same_everywhere: bool
    percent: int
    # Ключ — идентификатор склада в кабинете WB, значение — доля в процентах.
    by_warehouse: dict[int, int] = field(default_factory=dict)
    # Режим «остаток по штукам»: вместо доли оператор задаёт число по каждому
    # складу WB. Доля при этом не стирается — переключил галку обратно, и работает
    # прежний процент.
    units_mode: bool = False
    # Ключ — склад в кабинете WB, значение — сколько штук задал оператор.
    # Доступное новым заказам; резерв и физический расход учитывает inventory_service.
    units_by_warehouse: dict[int, int] = field(default_factory=dict)


@dataclass(frozen=True)
class FbsRuleView:
    """Правило плюс три числа, из которых видно, почему доля даёт столько штук."""

    rule: FbsRule
    on_hand: int
    reserved: int
    free_stock: int
    published_now: int
    # Числа по складам WB — только в режиме штук. Именно они подставляются в
    # поля ввода, когда оператор открывает окно: текущая доступность.
    units_remaining_by_warehouse: dict[int, int] = field(default_factory=dict)


def amount_from_percent(free_stock: int, percent: int) -> int:
    """Штуки из доли. Округление вниз: лучше недодать, чем продать чужое."""
    if free_stock <= 0 or percent <= 0:
        return 0
    return (free_stock * percent) // 100


def validate_rule(
    rule: FbsRule,
    *,
    served_warehouse_count: int,
    free_stock: int | None = None,
) -> None:
    """Проверить правило до записи — сумма долей не должна превышать сто процентов.

    Склады продавца делят один и тот же свободный остаток: товар лежит у нас, а
    склады в кабинете WB — это направления отгрузки. Отдать сто процентов одному
    и семьдесят другому нельзя, столько товара просто нет.

    В режиме штук то же самое ограничение, только в единицах: сумма чисел по
    складам не может быть больше свободного остатка. ``free_stock`` при этом
    обязателен и должен быть прочитан в той же транзакции, что и запись, — иначе
    между показом окна и нажатием «Сохранить» приедет заказ, и проверка пройдёт
    по устаревшему числу.
    """
    if rule.units_mode:
        _validate_units(rule, free_stock)
        return
    _check_percent(rule.percent)
    for percent in rule.by_warehouse.values():
        _check_percent(percent)

    if rule.same_everywhere:
        # Одна доля применяется к каждому обслуживаемому складу, поэтому в сумме
        # она умножается на их количество.
        total = rule.percent * max(served_warehouse_count, 1)
    else:
        total = sum(rule.by_warehouse.values())
    if total > PERCENT_MAX:
        raise FbsStockRuleError(
            "percent_sum_exceeded",
            message=(
                f"В сумме по складам получается {total}% свободного остатка, "
                "а он у складов общий — больше 100% отдать нельзя."
            ),
            context={"total": total},
        )


def _check_percent(percent: int) -> None:
    if percent < 0 or percent > PERCENT_MAX:
        raise FbsStockRuleError(
            "invalid_percent",
            message="Доля задаётся от 0 до 100 процентов.",
            context={"percent": percent},
        )
    if percent % PERCENT_STEP != 0:
        raise FbsStockRuleError(
            "invalid_percent",
            message=f"Доля задаётся шагом в {PERCENT_STEP} процентов.",
            context={"percent": percent},
        )


def _validate_units(rule: FbsRule, free_stock: int | None) -> None:
    for quantity in rule.units_by_warehouse.values():
        if quantity < 0:
            raise FbsStockRuleError(
                "invalid_units",
                message="Количество штук не может быть отрицательным.",
                context={"quantity": quantity},
            )
    total = sum(rule.units_by_warehouse.values())
    if free_stock is not None and total > free_stock:
        raise FbsStockRuleError(
            "units_sum_exceeded",
            message=(
                f"По складам распределено {total} шт, а свободно только "
                f"{free_stock}. Склады делят один и тот же остаток."
            ),
            context={"total": total, "free_stock": free_stock},
        )


async def _seller_bindings(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    served_only: bool,
) -> list[FbsWarehouseBinding]:
    stmt = select(FbsWarehouseBinding).where(
        FbsWarehouseBinding.tenant_id == tenant_id,
        FbsWarehouseBinding.seller_id == seller_id,
        FbsWarehouseBinding.is_active.is_(True),
    )
    if served_only:
        stmt = stmt.where(FbsWarehouseBinding.served.is_(True))
    rows = list((await session.execute(stmt)).scalars().all())
    # Порядок важен: при раздаче остатка он определяет, кому достанется остаток
    # от округления. Стабильный порядок делает публикацию воспроизводимой.
    rows.sort(key=lambda row: int(row.wb_warehouse_id))
    return rows


async def _pool_rows(
    session: AsyncSession,
    product_id: uuid.UUID,
    binding_ids: list[uuid.UUID],
) -> dict[uuid.UUID, FbsBindingStockPool]:
    if not binding_ids:
        return {}
    stmt = select(FbsBindingStockPool).where(
        FbsBindingStockPool.product_id == product_id,
        FbsBindingStockPool.binding_id.in_(binding_ids),
    )
    return {row.binding_id: row for row in (await session.execute(stmt)).scalars().all()}


async def _free_stock_for_bindings(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    bindings: list[FbsWarehouseBinding],
) -> tuple[int, int, int]:
    """(on_hand, reserved, free) по всем нашим складам, откуда кормится этот продавец.

    Обычно склад один: один физический склад фулфилмента кормит все адреса
    продавца в кабинете WB. Но если их несколько, числа складываются — иначе на
    экране было бы видно меньше товара, чем лежит.
    """
    warehouse_ids = {binding.wms_warehouse_id for binding in bindings}
    on_hand = reserved = free = 0
    for warehouse_id in sorted(warehouse_ids, key=str):
        breakdown = await fbs_stock_breakdown_by_product(
            session,
            tenant_id,
            warehouse_id,
            [product_id],
            include_global_direction_reserve=False,
        )
        row = breakdown.get(product_id)
        if row is None:
            continue
        on_hand += row.on_hand
        reserved += row.reserved
        free += row.free
    directions = (
        await stock_direction_service.direction_totals_by_product(session, tenant_id, [product_id])
    ).get(product_id)
    direction_reserved = int(directions.total) if directions is not None else 0
    reserved += direction_reserved
    free = max(0, free - direction_reserved)
    return on_hand, reserved, free


def rule_from_product(
    product: Product,
    pool_rows: dict[uuid.UUID, FbsBindingStockPool],
    bindings: list[FbsWarehouseBinding],
) -> FbsRule:
    by_warehouse: dict[int, int] = {}
    units_by_warehouse: dict[int, int] = {}
    for binding in bindings:
        pool = pool_rows.get(binding.id)
        if pool is None:
            continue
        if pool.percent is not None:
            by_warehouse[int(binding.wb_warehouse_id)] = int(pool.percent)
        units_by_warehouse[int(binding.wb_warehouse_id)] = int(pool.quantity or 0)
    return FbsRule(
        publish=bool(product.fbs_stock_sync_enabled),
        same_everywhere=bool(product.fbs_same_everywhere),
        percent=int(product.fbs_percent or 0),
        by_warehouse=by_warehouse,
        units_mode=bool(product.fbs_units_mode),
        units_by_warehouse=units_by_warehouse,
    )


def split_amounts(
    rule: FbsRule,
    free_stock: int,
    bindings: list[FbsWarehouseBinding],
) -> dict[uuid.UUID, int]:
    """Штуки уже выделены; проценты вычисляются от свободного остатка."""
    if not rule.publish:
        return {binding.id: 0 for binding in bindings}
    if rule.units_mode:
        return {
            binding.id: max(0, rule.units_by_warehouse.get(int(binding.wb_warehouse_id), 0))
            for binding in bindings
        }
    remaining = max(free_stock, 0)
    amounts: dict[uuid.UUID, int] = {}
    for binding in bindings:
        percent = (
            rule.percent
            if rule.same_everywhere
            else rule.by_warehouse.get(int(binding.wb_warehouse_id), 0)
        )
        amount = min(amount_from_percent(free_stock, percent), remaining)
        amounts[binding.id] = amount
        remaining -= amount
    return amounts


def _units_by_wb(rule: FbsRule, bindings: list[FbsWarehouseBinding]) -> dict[int, int]:
    return {
        int(binding.wb_warehouse_id): rule.units_by_warehouse[int(binding.wb_warehouse_id)]
        for binding in bindings
        if int(binding.wb_warehouse_id) in rule.units_by_warehouse
    }


async def get_rule_view(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
) -> FbsRuleView:
    product = await session.get(Product, product_id)
    if product is None or product.tenant_id != tenant_id:
        raise FbsStockRuleError("product_not_found", message="Товар не найден.")
    if product.seller_id is None:
        raise FbsStockRuleError(
            "product_without_seller",
            message="У товара нет продавца, поэтому складов WB для него тоже нет.",
        )
    bindings = await _seller_bindings(session, tenant_id, product.seller_id, served_only=False)
    served = [binding for binding in bindings if binding.served]
    pool_rows = await _pool_rows(session, product_id, [b.id for b in bindings])
    rule = rule_from_product(product, pool_rows, bindings)
    on_hand, reserved, free = await _free_stock_for_bindings(
        session, tenant_id, product_id, bindings
    )
    amounts = split_amounts(rule, free, served)
    return FbsRuleView(
        rule=rule,
        on_hand=on_hand,
        reserved=reserved,
        free_stock=free,
        published_now=sum(amounts.values()),
        units_remaining_by_warehouse=_units_by_wb(rule, bindings),
    )


async def get_rule_views(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> dict[uuid.UUID, FbsRuleView]:
    """Получить правила нескольких товаров без поштучных запросов к БД.

    Товары группируются по продавцу, потому что у каждого продавца свой набор
    складов WB. Остатки при этом считаются пакетно для всех товаров продавца на
    каждом обслуживающем их физическом складе.
    """
    unique_ids = list(dict.fromkeys(product_ids))
    if not unique_ids:
        raise FbsStockRuleError("empty_selection", message="Не выбрано ни одного товара.")

    products = list(
        (
            await session.scalars(
                select(Product).where(
                    Product.tenant_id == tenant_id,
                    Product.id.in_(unique_ids),
                )
            )
        ).all()
    )
    products_by_id = {product.id: product for product in products}
    if len(products_by_id) != len(unique_ids):
        raise FbsStockRuleError("product_not_found", message="Товар не найден.")
    if any(product.seller_id is None for product in products):
        raise FbsStockRuleError(
            "product_without_seller",
            message="У товара нет продавца, поэтому складов WB для него тоже нет.",
        )

    products_by_seller: dict[uuid.UUID, list[Product]] = {}
    for product in products:
        assert product.seller_id is not None
        products_by_seller.setdefault(product.seller_id, []).append(product)

    views: dict[uuid.UUID, FbsRuleView] = {}
    for seller_id, seller_products in products_by_seller.items():
        bindings = await _seller_bindings(session, tenant_id, seller_id, served_only=False)
        served = [binding for binding in bindings if binding.served]
        binding_ids = [binding.id for binding in bindings]
        seller_product_ids = [product.id for product in seller_products]

        pools_by_product: dict[uuid.UUID, dict[uuid.UUID, FbsBindingStockPool]] = {
            product_id: {} for product_id in seller_product_ids
        }
        if binding_ids:
            pool_stmt = select(FbsBindingStockPool).where(
                FbsBindingStockPool.tenant_id == tenant_id,
                FbsBindingStockPool.product_id.in_(seller_product_ids),
                FbsBindingStockPool.binding_id.in_(binding_ids),
            )
            for pool in (await session.scalars(pool_stmt)).all():
                pools_by_product[pool.product_id][pool.binding_id] = pool

        stock_by_product = {product_id: [0, 0, 0] for product_id in seller_product_ids}
        warehouse_ids = sorted({binding.wms_warehouse_id for binding in bindings}, key=str)
        for warehouse_id in warehouse_ids:
            breakdown = await fbs_stock_breakdown_by_product(
                session,
                tenant_id,
                warehouse_id,
                seller_product_ids,
                include_global_direction_reserve=False,
            )
            for product_id, row in breakdown.items():
                totals = stock_by_product[product_id]
                totals[0] += row.on_hand
                totals[1] += row.reserved
                totals[2] += row.free

        # StockDirection has no warehouse dimension: it reserves a product from
        # the tenant-wide stock once.  Warehouse-specific outbound/FBS reserves
        # above remain clamped inside their own physical warehouses; only this
        # global reserve is applied after those warehouse results are summed.
        direction_totals = await stock_direction_service.direction_totals_by_product(
            session, tenant_id, seller_product_ids
        )
        for product_id in seller_product_ids:
            directions = direction_totals.get(product_id)
            direction_reserved = int(directions.total) if directions is not None else 0
            totals = stock_by_product[product_id]
            totals[1] += direction_reserved
            totals[2] = max(0, totals[2] - direction_reserved)

        for product in seller_products:
            pool_rows = pools_by_product[product.id]
            rule = rule_from_product(product, pool_rows, bindings)
            on_hand, reserved, free = stock_by_product[product.id]
            amounts = split_amounts(rule, free, served)
            views[product.id] = FbsRuleView(
                rule=rule,
                on_hand=on_hand,
                reserved=reserved,
                free_stock=free,
                published_now=sum(amounts.values()),
                units_remaining_by_warehouse=_units_by_wb(rule, bindings),
            )
    return views


async def set_rule_for_products(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_ids: list[uuid.UUID],
    rule: FbsRule,
    *,
    updated_by: uuid.UUID | None = None,
) -> None:
    """Записать правило одному товару или сразу нескольким.

    Массовое присвоение отказывает на товарах разных продавцов: у каждого свои
    склады в кабинете WB, и один и тот же процент разложился бы не туда.
    """
    if not product_ids:
        raise FbsStockRuleError("empty_selection", message="Не выбрано ни одного товара.")
    stmt = (
        select(Product)
        .where(Product.tenant_id == tenant_id, Product.id.in_(product_ids))
        .order_by(Product.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    products = list((await session.execute(stmt)).scalars().all())
    missing = set(product_ids) - {product.id for product in products}
    if missing:
        raise FbsStockRuleError("product_not_found", message="Товар не найден.")
    seller_ids = {product.seller_id for product in products}
    if len(seller_ids) > 1:
        raise FbsStockRuleError(
            "mixed_sellers",
            message=(
                "Товары разных продавцов: склады у них свои, "
                "поэтому один процент на всех задать нельзя."
            ),
        )
    seller_id = next(iter(seller_ids))
    if seller_id is None:
        raise FbsStockRuleError(
            "product_without_seller",
            message="У товара нет продавца, поэтому складов WB для него тоже нет.",
        )

    bindings = await _seller_bindings(session, tenant_id, seller_id, served_only=False)
    served = [binding for binding in bindings if binding.served]
    known_wb_ids = {int(binding.wb_warehouse_id) for binding in bindings}
    unknown = (
        set(rule.units_by_warehouse) if rule.units_mode else set(rule.by_warehouse)
    ) - known_wb_ids
    if unknown:
        raise FbsStockRuleError(
            "warehouse_not_found",
            message="Среди складов продавца нет такого склада.",
            context={"wb_warehouse_ids": sorted(unknown)},
        )
    # Свободный остаток читается ЗДЕСЬ, в той же транзакции, что и запись, а не
    # берётся с экрана: между открытием окна и нажатием «Сохранить» мог приехать
    # заказ, и проверка по показанному числу пропустила бы перебор.
    if rule.units_mode:
        # Проверяем КАЖДЫЙ товар отдельно: в штуках у каждого свой остаток, и
        # одно число на всех сойдётся у одного, а у соседнего окажется перебором.
        for product in products:
            _, _, product_free = await _free_stock_for_bindings(
                session, tenant_id, product.id, bindings
            )
            # Выделение выключенных/неактивных направлений тоже занимает товар.
            hidden_pools = (
                list(
                    (
                        await session.scalars(
                            select(FbsBindingStockPool).where(
                                FbsBindingStockPool.product_id == product.id,
                                FbsBindingStockPool.binding_id.notin_([b.id for b in bindings]),
                            )
                        )
                    ).all()
                )
                if product.fbs_units_mode
                else []
            )
            hidden_by_warehouse: dict[uuid.UUID, int] = {}
            for hidden_pool in hidden_pools:
                hidden_binding = await session.get(FbsWarehouseBinding, hidden_pool.binding_id)
                if hidden_binding is not None:
                    wid = hidden_binding.wms_warehouse_id
                    hidden_by_warehouse[wid] = (
                        hidden_by_warehouse.get(wid, 0) + hidden_pool.quantity
                    )
            product_free = max(
                0,
                product_free
                - sum(
                    hidden_by_warehouse.get(wid, 0)
                    for wid in {b.wms_warehouse_id for b in bindings}
                ),
            )
            validate_rule(
                rule,
                served_warehouse_count=len(served),
                free_stock=product_free,
            )
            for warehouse_id in {b.wms_warehouse_id for b in bindings}:
                local_bindings = [b for b in bindings if b.wms_warehouse_id == warehouse_id]
                _, _, local_free = await _free_stock_for_bindings(
                    session, tenant_id, product.id, local_bindings
                )
                local_free = max(0, local_free - hidden_by_warehouse.get(warehouse_id, 0))
                local_total = sum(
                    rule.units_by_warehouse.get(int(b.wb_warehouse_id), 0) for b in local_bindings
                )
                if local_total > local_free:
                    raise FbsStockRuleError(
                        "units_sum_exceeded",
                        message="На физическом складе не хватает свободного товара.",
                        context={"total": local_total, "free_stock": local_free},
                    )
    else:
        validate_rule(rule, served_warehouse_count=len(served))

    # Обслуживание склада — граница «наш он или чужой», и включать публикацию
    # можно только по нашим. Но включать её РАЗОМ ПО ВСЕМ обслуживаемым нельзя:
    # оператор настраивает один товар, а флаг переключается на весь кабинет
    # продавца. 04.09.2026 на этом и споткнулись — сохранение правила по Фэшн
    # включило публикацию по складу `1865709`, которого в кабинете WB давно нет,
    # и он начал отвечать 404 на каждом обходе.
    #
    # Поэтому включаем только те склады, которые правило действительно называет.
    # Галка «одинаково по всем складам» — единственное исключение: она про все
    # обслуживаемые по своему смыслу, там перечисления просто нет.
    if rule.units_mode:
        addressed = set(rule.units_by_warehouse)
    elif rule.same_everywhere:
        addressed = {int(binding.wb_warehouse_id) for binding in served}
    else:
        addressed = set(rule.by_warehouse)
    for binding in served:
        if int(binding.wb_warehouse_id) in addressed:
            binding.stock_sync_enabled = True

    binding_by_wb = {int(binding.wb_warehouse_id): binding for binding in bindings}
    for product in products:
        product.fbs_stock_sync_enabled = rule.publish
        product.fbs_same_everywhere = rule.same_everywhere
        product.fbs_percent = rule.percent
        # Доля не стирается при переходе в штуки и наоборот: переключил галку
        # обратно — работает то, что было. Оба числа лежат рядом, режим решает,
        # какое из них читает публикация.
        product.fbs_units_mode = rule.units_mode
        if not rule.units_mode:
            await session.execute(
                update(FbsBindingStockPool)
                .where(
                    FbsBindingStockPool.product_id == product.id,
                    FbsBindingStockPool.tenant_id == tenant_id,
                )
                .values(quantity=0)
            )
        pool_rows = await _pool_rows(session, product.id, [b.id for b in bindings])
        for wb_warehouse_id, binding in binding_by_wb.items():
            percent = rule.by_warehouse.get(wb_warehouse_id)
            units = rule.units_by_warehouse.get(wb_warehouse_id)
            pool = pool_rows.get(binding.id)
            if pool is None:
                if percent is None and units is None:
                    continue
                pool = FbsBindingStockPool(
                    tenant_id=tenant_id,
                    binding_id=binding.id,
                    product_id=product.id,
                    quantity=int(units or 0) if rule.units_mode else 0,
                    percent=percent,
                    updated_by=updated_by,
                )
                session.add(pool)
                continue
            pool.percent = percent
            if rule.units_mode:
                pool.quantity = int(units or 0)
            else:
                # Выделение возвращается в общий остаток; резервы заказов остаются.
                pool.quantity = 0
            pool.updated_by = updated_by
    schedule_seller_stock_publish(session, tenant_id, seller_id)
    await session.commit()


async def reset_legacy_limits_for_products(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> int:
    """Явно обнулить старые абсолютные лимиты после настройки нового правила.

    Это намеренно отдельная операция, а не побочный эффект сохранения правила и
    не data migration. До её вызова товар без доли продолжает публиковаться по
    старому безопасному пути.
    """
    unique_ids = list(dict.fromkeys(product_ids))
    if not unique_ids:
        raise FbsStockRuleError("empty_selection", message="Не выбрано ни одного товара.")
    stmt = select(Product).where(
        Product.tenant_id == tenant_id,
        Product.id.in_(unique_ids),
    )
    products = list((await session.execute(stmt)).scalars().all())
    if len(products) != len(unique_ids):
        raise FbsStockRuleError("product_not_found", message="Товар не найден.")
    if any(product.fbs_percent is None for product in products):
        raise FbsStockRuleError(
            "rule_not_configured",
            message="Сначала настройте правило доли для каждого выбранного товара.",
        )

    await session.execute(
        update(Product)
        .where(Product.id.in_(unique_ids), Product.tenant_id == tenant_id)
        .values(fbs_stock_limit=0)
    )
    await session.execute(
        update(FbsBindingStockPool)
        .where(
            FbsBindingStockPool.tenant_id == tenant_id,
            FbsBindingStockPool.product_id.in_(
                [product.id for product in products if not product.fbs_units_mode]
            ),
        )
        .values(quantity=0)
    )
    await session.commit()
    return len(unique_ids)


async def publish_amounts_for_binding(
    session: AsyncSession,
    binding: FbsWarehouseBinding,
    products: list[Product],
) -> dict[uuid.UUID, int]:
    """Сколько штук отправить в WB по этой привязке: product_id -> количество.

    Это тот самый «источник числа», который заменил сохранённый абсолютный лимит.
    Товар без правила в ответ не попадает вовсе. Если правило настроено, но
    публикация выключена, в ответе остаётся осознанный ноль: WB не должен хранить
    последнее положительное значение после выключения товара.
    """
    publishable = [
        product for product in products if product.fbs_percent is not None or product.fbs_units_mode
    ]
    if not publishable or not binding.served:
        return {}
    seller_bindings = await _seller_bindings(
        session, binding.tenant_id, binding.seller_id, served_only=True
    )
    if not any(row.id == binding.id for row in seller_bindings):
        return {}
    seller_bindings = [
        row for row in seller_bindings if row.wms_warehouse_id == binding.wms_warehouse_id
    ]
    product_ids = [product.id for product in publishable]
    breakdown = await fbs_stock_breakdown_by_product(
        session, binding.tenant_id, binding.wms_warehouse_id, product_ids
    )
    amounts: dict[uuid.UUID, int] = {}
    for product in publishable:
        pool_rows = await _pool_rows(session, product.id, [row.id for row in seller_bindings])
        rule = rule_from_product(product, pool_rows, seller_bindings)
        free = breakdown[product.id].free if product.id in breakdown else 0
        split = split_amounts(rule, free, seller_bindings)
        amounts[product.id] = split.get(binding.id, 0)
    return amounts
