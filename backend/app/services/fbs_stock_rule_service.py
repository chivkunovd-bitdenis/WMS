"""Проценты свободного остатка либо операторские потолки публикации (WMS-060)."""

from __future__ import annotations

import uuid
from collections import Counter
from contextlib import AsyncExitStack
from dataclasses import dataclass, field, replace
from typing import Literal

from sqlalchemy import ColumnElement, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_stock_sync_item import STOCK_SYNC_STATUS_PENDING, FbsStockSyncItem
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product import Product
from app.services import stock_direction_service
from app.services.catalog_service import list_ozon_product_links
from app.services.fbs_stock_availability_service import (
    FbsStockBreakdown,
    fbs_stock_breakdown_by_product,
)
from app.services.fbs_stock_publish_service import schedule_seller_stock_publish
from app.services.marketplace_seller_lock_service import marketplace_seller_lock

# WMS-469: принятый ползунок идёт шагом пять процентных пунктов.
PERCENT_STEP = 5
PERCENT_MAX = 100


def product_has_rule_predicate() -> ColumnElement[bool]:
    """WMS-384. SQL-предикат «у товара есть хоть какое-то правило публикации».

    Раньше та же самая проверка `or_(percent IS NOT NULL, units_mode)` жила
    отдельными копиями в `fbs_stock_sync_service` и `fbs_warehouse_binding_service`.
    Второй счётчик одного смысла: разойдутся, вопрос только когда. Здесь один
    предикат, к которому все обращаются по имени. Семантики callsite это НЕ
    меняет: сам отбор такой же грубый, как был. Точная проверка «правило
    задано и с положительным значением» остаётся в `_binding_has_rule` — она сложнее и
    требует per-binding pool_rows, поэтому её нельзя выразить одной колонкой.

    Не расширять этот предикат новыми условиями (published_now, флаги площадок
    и т.д.): у каждого места вызова свой смысл — served, stock_sync_enabled,
    per-marketplace publication flag — и они добавляются в WHERE отдельно.
    """
    return or_(Product.fbs_percent.is_not(None), Product.fbs_units_mode.is_(True))


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
class FbsBindingRule:
    """Одно правило одной пары товар x привязка (WMS-469)."""

    publish: bool
    mode: Literal["percent", "units"]
    value: int
    # WMS-483: в режиме штук отсутствие лимита и явный ноль — разные состояния.
    # Default сохраняет совместимость с клиентами WMS-469, которые до объединения
    # всегда присылали value и не знали отдельного признака.
    units_configured: bool = True


@dataclass(frozen=True)
class FbsRule:
    """Правило публикации остатка по одному товару."""

    publish: bool | None
    same_everywhere: bool
    percent: int
    # Ключ — идентификатор склада в кабинете WB, значение — доля в процентах.
    by_warehouse: dict[int | str, int] = field(default_factory=dict)
    # Режим «остаток по штукам»: вместо доли оператор задаёт число по каждому
    # складу WB. Доля при этом не стирается — переключил галку обратно, и работает
    # прежний процент.
    units_mode: bool = False
    # Ключ — склад в кабинете WB, значение — сколько штук задал оператор.
    # Потолок публикации; резерв и физический расход учитывает inventory_service.
    units_by_warehouse: dict[int | str, int] = field(default_factory=dict)
    publish_ozon: bool | None = None
    # UUID не зависит от совпадающих внешних номеров WB и Ozon.
    by_binding: dict[uuid.UUID, FbsBindingRule] = field(default_factory=dict)
    # Старый JSON без `by_binding` и новая форма с явным `by_binding: {}` имеют
    # разный смысл. Второй вариант означает «видимых строк нет, ничего не менять».
    by_binding_present: bool = False

    def publishes(self, marketplace: str) -> bool:
        if marketplace == "ozon" and self.publish_ozon is not None:
            return self.publish_ozon
        return bool(self.publish)


@dataclass(frozen=True)
class FbsBindingRuleView:
    binding_id: uuid.UUID
    marketplace: str
    external_warehouse_id: str
    wms_warehouse_id: uuid.UUID
    served: bool
    applicable: bool
    publish: bool
    mode: Literal["percent", "units"]
    value: int
    units_configured: bool
    on_hand: int
    reserved: int
    free_stock: int
    published_now: int


@dataclass(frozen=True)
class FbsRuleView:
    """Правило плюс три числа, из которых видно, почему доля даёт столько штук."""

    rule: FbsRule
    on_hand: int
    reserved: int
    free_stock: int
    published_now: int
    # Числа по складам WB — только в режиме штук. Именно они подставляются в
    # поля ввода, когда оператор открывает окно: операторские потолки.
    units_remaining_by_warehouse: dict[int | str, int] = field(default_factory=dict)
    by_binding: dict[uuid.UUID, FbsBindingRuleView] = field(default_factory=dict)


@dataclass(frozen=True)
class FbsRuleClamp:
    binding_id: uuid.UUID
    requested_value: int
    saved_value: int
    limiting_product_id: uuid.UUID
    limiting_product_name: str


@dataclass(frozen=True)
class FbsRuleSaveResult:
    updated_count: int
    clamps: dict[uuid.UUID, FbsRuleClamp] = field(default_factory=dict)


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
    """Проверить диапазон одного значения без общего потолка между связками."""
    if rule.units_mode:
        _validate_units(rule)
        return
    _check_percent(rule.percent)
    for percent in rule.by_warehouse.values():
        _check_percent(percent)


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


def _validate_units(rule: FbsRule) -> None:
    for quantity in rule.units_by_warehouse.values():
        if quantity < 0:
            raise FbsStockRuleError(
                "invalid_units",
                message="Количество штук не может быть отрицательным.",
                context={"quantity": quantity},
            )


async def _seller_bindings(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    publishing_only: bool,
) -> list[FbsWarehouseBinding]:
    """Активные привязки продавца по обеим площадкам (WMS-469).

    Они читают один физический остаток, но каждая независимо публикует свой
    ``min(лимит оператора, свободный остаток)``. Поэтому список общий для одного
    снимка остатка, а сумма процентов/чисел между привязками не ограничивается.
    """
    stmt = select(FbsWarehouseBinding).where(
        FbsWarehouseBinding.tenant_id == tenant_id,
        FbsWarehouseBinding.seller_id == seller_id,
        FbsWarehouseBinding.is_active.is_(True),
    )
    if publishing_only:
        # WMS-376. Свободный остаток делят между собой те привязки, которые его
        # действительно транслируют. Обслуживание склада тут ни при чём.
        stmt = stmt.where(FbsWarehouseBinding.stock_sync_enabled.is_(True))
    rows = list((await session.execute(stmt)).scalars().all())
    # Стабильный порядок нужен для воспроизводимого ответа API. Номера складов у
    # разных площадок могут совпасть, поэтому площадка остаётся вторым ключом.
    rows.sort(key=lambda row: (int(row.wb_warehouse_id), row.marketplace))
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
    ).execution_options(populate_existing=True)
    return {row.binding_id: row for row in (await session.execute(stmt)).scalars().all()}


async def _pool_rows_for_products(
    session: AsyncSession,
    product_ids: list[uuid.UUID],
    binding_ids: list[uuid.UUID],
) -> dict[uuid.UUID, dict[uuid.UUID, FbsBindingStockPool]]:
    """Read all product x binding rows in one query for a bulk save."""
    rows_by_product: dict[
        uuid.UUID, dict[uuid.UUID, FbsBindingStockPool]
    ] = {product_id: {} for product_id in product_ids}
    if not product_ids or not binding_ids:
        return rows_by_product
    stmt = (
        select(FbsBindingStockPool)
        .where(
            FbsBindingStockPool.product_id.in_(product_ids),
            FbsBindingStockPool.binding_id.in_(binding_ids),
        )
        .execution_options(populate_existing=True)
    )
    for row in (await session.execute(stmt)).scalars().all():
        rows_by_product[row.product_id][row.binding_id] = row
    return rows_by_product


async def _free_stock_by_product_for_binding(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_ids: list[uuid.UUID],
    binding: FbsWarehouseBinding,
) -> dict[uuid.UUID, int]:
    """Read one binding's free stock for a whole bulk selection without N+1 queries."""
    breakdown = await fbs_stock_breakdown_by_product(
        session,
        tenant_id,
        binding.wms_warehouse_id,
        product_ids,
        include_global_direction_reserve=False,
    )
    directions = await stock_direction_service.direction_totals_by_product(
        session,
        tenant_id,
        product_ids,
    )
    free_by_product: dict[uuid.UUID, int] = {}
    for product_id in product_ids:
        row = breakdown.get(product_id)
        free = row.free if row is not None else 0
        direction = directions.get(product_id)
        direction_reserved = int(direction.total) if direction is not None else 0
        free_by_product[product_id] = max(0, free - direction_reserved)
    return free_by_product


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


def _binding_key(binding: FbsWarehouseBinding) -> str:
    return f"{binding.marketplace}:{binding.wb_warehouse_id}"


def _qualified_rule(rule: FbsRule, bindings: list[FbsWarehouseBinding]) -> FbsRule:
    """Resolve legacy numeric keys once; explicit marketplace keys are never ambiguous."""
    by_number: dict[int, list[FbsWarehouseBinding]] = {}
    known_keys = {_binding_key(binding) for binding in bindings}
    for binding in bindings:
        by_number.setdefault(int(binding.wb_warehouse_id), []).append(binding)

    def qualify(
        values: dict[int | str, int], *, strict: bool,
    ) -> dict[int | str, int]:
        result: dict[int | str, int] = {}
        for key, value in values.items():
            qualified = str(key)
            if isinstance(key, int) or str(key).isdigit():
                matches = by_number.get(int(key), [])
                if len(matches) > 1:
                    if not strict:
                        continue
                    raise FbsStockRuleError(
                        "warehouse_id_collision",
                        message="Для склада с одинаковым номером укажите площадку: WB или Ozon.",
                        context={"wb_warehouse_ids": [int(key)]},
                    )
                qualified = _binding_key(matches[0]) if matches else str(key)
            if qualified not in known_keys:
                if not strict:
                    continue
                raise FbsStockRuleError("warehouse_not_found", message="Склад продавца не найден.")
            if qualified in result:
                if not strict:
                    continue
                raise FbsStockRuleError(
                    "warehouse_id_collision", message="Один склад указан в правиле дважды.",
                )
            result[qualified] = value
        return result

    return replace(
        rule,
        by_warehouse=qualify(rule.by_warehouse, strict=not rule.units_mode),
        units_by_warehouse=qualify(rule.units_by_warehouse, strict=rule.units_mode),
    )


def _effective_publish_ozon(product: Product, *, has_ozon_link: bool) -> bool:
    """Эффективный флаг публикации в Ozon: сохранённое значение И наличие карточки.

    WMS-456. Без активной ProductMarketplaceLink(marketplace="ozon") сервер не
    считает товар озоновским — публиковать нечего, что бы ни было сохранено или
    унаследовано в products.fbs_ozon_stock_sync_enabled (NULL, True или False).
    Это единственное место, где считается эффективный флаг: его читают
    rule_from_product (для проверки, расчёта и ответа API) и
    publish_amounts_for_binding (для отбора публикуемых товаров), чтобы не
    разойтись в двух копиях одной формулы.
    """
    if not has_ozon_link:
        return False
    return (
        product.fbs_stock_sync_enabled
        if product.fbs_ozon_stock_sync_enabled is None
        else product.fbs_ozon_stock_sync_enabled
    )


def _binding_rule_from_state(
    product: Product,
    pool: FbsBindingStockPool | None,
    binding: FbsWarehouseBinding,
    *,
    has_ozon_link: bool,
) -> FbsBindingRule:
    """Read explicit WMS-469 state, falling back to the pre-WMS-469 rule."""
    applicable = binding.marketplace != "ozon" or has_ozon_link
    if pool is not None and pool.publish_enabled is not None:
        if pool.percent is None:
            mode: Literal["percent", "units"] = "units"
            value = int(pool.quantity or 0)
            units_configured = bool(pool.units_configured or value > 0)
        else:
            mode = "percent"
            value = int(pool.percent)
            units_configured = False
        return FbsBindingRule(
            publish=bool(pool.publish_enabled and binding.stock_sync_enabled and applicable),
            mode=mode,
            value=value,
            units_configured=units_configured,
        )

    publish = (
        bool(product.fbs_stock_sync_enabled)
        if binding.marketplace == "wb"
        else _effective_publish_ozon(product, has_ozon_link=has_ozon_link)
    )
    publish = bool(publish and binding.stock_sync_enabled and applicable)
    if product.fbs_units_mode:
        value = int(pool.quantity or 0) if pool is not None else 0
        return FbsBindingRule(
            publish=publish,
            mode="units",
            value=value,
            units_configured=bool(
                pool is not None and (pool.units_configured or value > 0)
            ),
        )
    percent = (
        int(product.fbs_percent or 0)
        if product.fbs_same_everywhere
        else int(pool.percent or 0) if pool is not None else 0
    )
    return FbsBindingRule(
        publish=publish,
        mode="percent",
        value=percent,
        units_configured=False,
    )


def rule_from_product(
    product: Product,
    pool_rows: dict[uuid.UUID, FbsBindingStockPool],
    bindings: list[FbsWarehouseBinding],
    *,
    has_ozon_link: bool,
) -> FbsRule:
    by_warehouse: dict[int | str, int] = {}
    units_by_warehouse: dict[int | str, int] = {}
    warehouse_counts = Counter(int(binding.wb_warehouse_id) for binding in bindings)
    binding_rules: dict[uuid.UUID, FbsBindingRule] = {}
    for binding in bindings:
        key: int | str = int(binding.wb_warehouse_id)
        if warehouse_counts[int(binding.wb_warehouse_id)] > 1:
            key = _binding_key(binding)
        pool = pool_rows.get(binding.id)
        if pool is None:
            continue
        if pool.percent is not None:
            by_warehouse[key] = int(pool.percent)
        if pool.units_configured or int(pool.quantity or 0) > 0:
            units_by_warehouse[key] = int(pool.quantity or 0)
        binding_rules[binding.id] = _binding_rule_from_state(
            product,
            pool,
            binding,
            has_ozon_link=has_ozon_link,
        )
    for binding in bindings:
        if binding.id not in binding_rules:
            binding_rules[binding.id] = _binding_rule_from_state(
                product,
                None,
                binding,
                has_ozon_link=has_ozon_link,
            )
    return FbsRule(
        publish=bool(product.fbs_stock_sync_enabled),
        publish_ozon=_effective_publish_ozon(product, has_ozon_link=has_ozon_link),
        same_everywhere=bool(product.fbs_same_everywhere),
        percent=int(product.fbs_percent or 0),
        by_warehouse=by_warehouse,
        units_mode=bool(product.fbs_units_mode),
        units_by_warehouse=units_by_warehouse,
        by_binding=binding_rules,
    )


def _binding_has_rule(
    product: Product,
    binding_id: uuid.UUID,
    pool_rows: dict[uuid.UUID, FbsBindingStockPool],
) -> bool:
    """Есть ли правило именно у запрошенной пары товар x привязка.

    WMS-376. Ноль — это не «ноль штук», а «правило не задано». Раньше проверка
    была `fbs_percent is not None`, и карточка с нулём проходила отбор, а потом
    получала осознанный ноль каждые пять минут — так у ИП Горячкина Т.И. три
    карточки очков ушли в ноль при 72 штуках на складе.

    Проверять сам ноль в лоб нельзя: у ВСЕХ 82 поштучных товаров на бою
    `fbs_percent = 0`, потому что в режиме штук доля не используется вовсе.
    Наивное `fbs_percent == 0` выбросило бы из публикации живые числа Ловианы,
    Фэшн и Чжоу. Поэтому признак трёхветочный, по режиму товара.
    """
    pool = pool_rows.get(binding_id)
    if pool is not None and pool.publish_enabled is not None:
        if not pool.publish_enabled:
            return False
        if pool.percent is not None:
            # WMS-469 D6: включённые 0% — явное активное правило нуля.
            return True
        return bool(pool.units_configured or int(pool.quantity or 0) > 0)
    if product.fbs_units_mode:
        # Режим штук: само значение живёт в строке этой привязки. Новая
        # привязка без строки пула не получает неявную команду опубликовать ноль.
        # Legacy-строка с quantity=0 сохраняет прежний одноразовый переходный
        # ноль, но units_configured ниже не включает для неё периодический цикл.
        return pool is not None
    if product.fbs_percent is None:
        return False
    if product.fbs_same_everywhere:
        return int(product.fbs_percent or 0) > 0
    # Своя доля по каждому складу: правило считается заданным, если хоть один
    # пул несёт положительный процент. По-привязочная проверка обязательна —
    # иначе товар с 40% на одном складе и нулём на другом вылетел бы целиком.
    return pool is not None and int(pool.percent or 0) > 0


def split_amounts(
    rule: FbsRule,
    free_stock: int,
    bindings: list[FbsWarehouseBinding],
    *,
    pool_rows: dict[uuid.UUID, FbsBindingStockPool] | None = None,
) -> dict[uuid.UUID, int]:
    """Посчитать каждую привязку независимо и ограничить фактическим остатком."""
    available = max(free_stock, 0)
    amounts: dict[uuid.UUID, int] = {}
    for binding in bindings:
        binding_rule = rule.by_binding.get(binding.id)
        if binding_rule is not None:
            if not binding_rule.publish:
                amounts[binding.id] = 0
                continue
            if binding_rule.mode == "units" and not binding_rule.units_configured:
                continue
            share = (
                amount_from_percent(available, binding_rule.value)
                if binding_rule.mode == "percent"
                else max(0, binding_rule.value)
            )
            amounts[binding.id] = min(share, available)
            continue
        if not rule.publishes(binding.marketplace):
            amounts[binding.id] = 0
            continue
        pool = pool_rows.get(binding.id) if pool_rows is not None else None
        if rule.units_mode:
            if pool_rows is None:
                units = rule.units_by_warehouse.get(
                    _binding_key(binding),
                    rule.units_by_warehouse.get(int(binding.wb_warehouse_id), 0),
                )
            else:
                units = int(pool.quantity or 0) if pool is not None else 0
            share = max(0, units)
        else:
            if rule.same_everywhere:
                percent = rule.percent
            elif pool_rows is None:
                percent = rule.by_warehouse.get(
                    _binding_key(binding),
                    rule.by_warehouse.get(int(binding.wb_warehouse_id), 0),
                )
            else:
                percent = int(pool.percent or 0) if pool is not None else 0
            share = amount_from_percent(available, percent)
        amounts[binding.id] = min(share, available)
    return amounts


def _units_by_wb(rule: FbsRule, bindings: list[FbsWarehouseBinding]) -> dict[int | str, int]:
    allowed: set[int | str] = {int(binding.wb_warehouse_id) for binding in bindings}
    allowed.update(_binding_key(binding) for binding in bindings)
    return {key: value for key, value in rule.units_by_warehouse.items() if key in allowed}


async def get_rule_view(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
) -> FbsRuleView:
    return (await get_rule_views(session, tenant_id, [product_id]))[product_id]


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
    # WMS-456: один пакетный запрос связок на весь список товаров, а не по одной
    # на продавца — связка ищется по product_id и продавца не касается.
    ozon_links = await list_ozon_product_links(session, tenant_id, set(unique_ids))

    products_by_seller: dict[uuid.UUID, list[Product]] = {}
    for product in products:
        assert product.seller_id is not None
        products_by_seller.setdefault(product.seller_id, []).append(product)

    views: dict[uuid.UUID, FbsRuleView] = {}
    for seller_id, seller_products in products_by_seller.items():
        bindings = await _seller_bindings(session, tenant_id, seller_id, publishing_only=False)
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
        free_by_warehouse: dict[uuid.UUID, dict[uuid.UUID, int]] = {}
        stock_rows_by_warehouse: dict[
            uuid.UUID, dict[uuid.UUID, FbsStockBreakdown]
        ] = {}
        warehouse_ids = sorted({binding.wms_warehouse_id for binding in bindings}, key=str)
        for warehouse_id in warehouse_ids:
            breakdown = await fbs_stock_breakdown_by_product(
                session,
                tenant_id,
                warehouse_id,
                seller_product_ids,
                include_global_direction_reserve=False,
            )
            stock_rows_by_warehouse[warehouse_id] = dict(breakdown)
            free_by_warehouse[warehouse_id] = {pid: row.free for pid, row in breakdown.items()}
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

        publishing = [binding for binding in bindings if binding.stock_sync_enabled]
        for product in seller_products:
            pool_rows = pools_by_product[product.id]
            rule = rule_from_product(
                product, pool_rows, bindings, has_ozon_link=product.id in ozon_links
            )
            on_hand, reserved, free = stock_by_product[product.id]
            directions = direction_totals.get(product.id)
            direction_reserved = int(directions.total) if directions is not None else 0
            amounts: dict[uuid.UUID, int] = {}
            for warehouse_id in warehouse_ids:
                local_bindings = [b for b in publishing if b.wms_warehouse_id == warehouse_id]
                # Match publish_amounts_for_binding: global direction reserves
                # are conservatively deducted from each physical warehouse.
                local_free = max(
                    0, free_by_warehouse[warehouse_id].get(product.id, 0) - direction_reserved
                )
                local_pools = {b.id: pool_rows[b.id] for b in local_bindings if b.id in pool_rows}
                amounts.update(
                    split_amounts(rule, local_free, local_bindings, pool_rows=local_pools)
                )
            binding_views: dict[uuid.UUID, FbsBindingRuleView] = {}
            for binding in bindings:
                local = free_by_warehouse.get(binding.wms_warehouse_id, {}).get(product.id)
                stock = stock_rows_by_warehouse.get(binding.wms_warehouse_id, {}).get(
                    product.id
                )
                local_on_hand = stock.on_hand if stock is not None else 0
                local_reserved = (stock.reserved if stock is not None else 0) + direction_reserved
                local_free = max(0, (local if local is not None else 0) - direction_reserved)
                binding_rule = rule.by_binding[binding.id]
                applicable = binding.marketplace != "ozon" or product.id in ozon_links
                binding_views[binding.id] = FbsBindingRuleView(
                    binding_id=binding.id,
                    marketplace=binding.marketplace,
                    external_warehouse_id=(
                        binding.external_warehouse_id or str(binding.wb_warehouse_id)
                    ),
                    wms_warehouse_id=binding.wms_warehouse_id,
                    served=binding.served,
                    applicable=applicable,
                    publish=bool(binding_rule.publish and applicable),
                    mode=binding_rule.mode,
                    value=binding_rule.value,
                    units_configured=(
                        binding_rule.mode == "units" and binding_rule.units_configured
                    ),
                    on_hand=local_on_hand,
                    reserved=local_reserved,
                    free_stock=local_free,
                    published_now=amounts.get(binding.id, 0),
                )
            views[product.id] = FbsRuleView(
                # Старые Python/API-потребители получают прежнюю форму. Новое
                # состояние пар лежит рядом в by_binding и не превращает
                # replace(view.rule, ...) в запрос нового формата.
                rule=replace(rule, by_binding={}),
                on_hand=on_hand,
                reserved=reserved,
                free_stock=free,
                published_now=sum(amounts.values()),
                units_remaining_by_warehouse=_units_by_wb(rule, bindings),
                by_binding=binding_views,
            )
    return views


def _marketplace_rule_signature(
    rule: FbsRule,
    marketplace: str,
    bindings: list[FbsWarehouseBinding],
) -> tuple[object, ...]:
    if not rule.publishes(marketplace):
        return (False,)
    shares = tuple(
        (
            _binding_key(binding),
            # WB absent -> explicit zero is a publication event (WMS-483).
            rule.units_by_warehouse.get(_binding_key(binding), None if marketplace == "wb" else 0)
            if rule.units_mode
            else rule.percent
            if rule.same_everywhere
            else rule.by_warehouse.get(_binding_key(binding), 0),
        )
        for binding in bindings
        if binding.marketplace == marketplace
    )
    return (True, rule.units_mode, shares)


async def _clear_product_publication(
    session: AsyncSession,
    binding: FbsWarehouseBinding,
    product_ids: set[uuid.UUID],
) -> None:
    """Confirm the final zero before saving off; preserve the old rule on failure."""
    import httpx

    from app.services.fbs_stock_sync_service import publish_explicit_zero_for_binding
    from app.services.fbs_warehouse_binding_service import (
        FbsWarehouseBindingError,
        _clear_previous_ozon_stock,
    )

    async with AsyncSession(bind=session.bind, expire_on_commit=False) as zero_session:
        zero_binding = await zero_session.get(FbsWarehouseBinding, binding.id)
        assert zero_binding is not None
        if binding.marketplace == "ozon":
            try:
                await _clear_previous_ozon_stock(
                    zero_session,
                    zero_binding,
                    product_ids=product_ids,
                )
                await zero_session.commit()
            except FbsWarehouseBindingError as exc:
                raise FbsStockRuleError(exc.code, message=exc.message) from exc
        else:
            async with httpx.AsyncClient() as client:
                result = await publish_explicit_zero_for_binding(
                    zero_session,
                    binding.tenant_id,
                    binding.seller_id,
                    zero_binding,
                    client,
                    product_ids=product_ids,
                )
            if result.errors or result.skipped_busy or result.error_code:
                raise FbsStockRuleError(
                    "stock_cleanup_failed",
                    message="WB не подтвердил обнуление. Настройки не изменены; повторите попытку.",
                )


async def set_rule_for_products(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_ids: list[uuid.UUID],
    rule: FbsRule | None,
    *,
    updated_by: uuid.UUID | None = None,
    _binding_quantity: tuple[uuid.UUID, int] | None = None,
) -> FbsRuleSaveResult:
    """Записать правило одному товару или сразу нескольким.

    Массовое присвоение отказывает на товарах разных продавцов: у каждого свои
    склады в кабинете WB, и один и тот же процент разложился бы не туда.
    """
    if not product_ids:
        raise FbsStockRuleError("empty_selection", message="Не выбрано ни одного товара.")
    ordered_product_ids = list(dict.fromkeys(product_ids))
    stmt = (
        select(Product)
        .where(Product.tenant_id == tenant_id, Product.id.in_(ordered_product_ids))
        .order_by(Product.id)
        .execution_options(populate_existing=True)
    )
    products = list((await session.execute(stmt)).scalars().all())
    missing = set(ordered_product_ids) - {product.id for product in products}
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

    async with AsyncExitStack() as stack:
        lock_session = await stack.enter_async_context(AsyncSession(bind=session.bind))
        for marketplace in ("ozon", "wb"):
            acquired = await stack.enter_async_context(
                marketplace_seller_lock(
                    lock_session,
                    seller_id,
                    marketplace,
                    wait_timeout_sec=30,
                )
            )
            if not acquired:
                raise FbsStockRuleError(
                    "stock_sync_busy",
                    message="Отправка остатков ещё идёт; повторите сохранение.",
                )
        locked_products = list((await session.scalars(stmt.with_for_update())).all())
        locked_by_id = {product.id: product for product in locked_products}
        products = [locked_by_id[product_id] for product_id in ordered_product_ids]
        if any(p.seller_id != seller_id for p in products):
            raise FbsStockRuleError("mixed_sellers")
        bindings = await _seller_bindings(session, tenant_id, seller_id, publishing_only=False)
        served = [binding for binding in bindings if binding.served]
        # WMS-456: один запрос связок на всю пачку товаров — тот же признак,
        # что решает эффективный флаг в get_rule_views и publish_amounts_for_binding.
        ozon_links = await list_ozon_product_links(
            session, tenant_id, {product.id for product in products}
        )
        binding_ids = [binding.id for binding in bindings]
        pools_by_product = await _pool_rows_for_products(
            session,
            [product.id for product in products],
            binding_ids,
        )
        old_rules = {}
        for product in products:
            old_rules[product.id] = _qualified_rule(
                rule_from_product(
                    product,
                    pools_by_product[product.id],
                    bindings,
                    has_ozon_link=product.id in ozon_links,
                ),
                bindings,
            )
        if _binding_quantity is not None:
            binding_id, quantity = _binding_quantity
            binding = next((b for b in bindings if b.id == binding_id), None)
            if binding is None:
                raise FbsStockRuleError("binding_not_found")
            if len(products) != 1:
                raise FbsStockRuleError("invalid_selection")
            previous = old_rules[products[0].id]
            previous_binding = previous.by_binding[binding.id]
            rule = FbsRule(
                publish=None,
                publish_ozon=None,
                same_everywhere=False,
                percent=0,
                by_binding={
                    binding.id: FbsBindingRule(
                        publish=previous_binding.publish,
                        mode="units",
                        value=quantity,
                    )
                },
            )
        if rule is None:
            raise FbsStockRuleError("rule_not_configured")

        if rule.by_binding_present and not rule.by_binding:
            # Новая форма явно прислала пустой набор видимых блоков. Это не
            # legacy-запрос и не команда сбросить соседние независимые правила.
            return FbsRuleSaveResult(updated_count=0)

        if rule.by_binding_present or rule.by_binding:
            binding_by_id = {binding.id: binding for binding in bindings}
            unknown = set(rule.by_binding) - set(binding_by_id)
            if unknown:
                raise FbsStockRuleError(
                    "binding_not_found",
                    message="Связка склада продавца со складом ФФ не найдена.",
                )

            saved_rules = dict(rule.by_binding)
            saved_rules = {
                binding_id: replace(binding_rule, units_configured=False)
                if binding_rule.mode == "percent"
                else replace(binding_rule, value=0)
                if not binding_rule.units_configured
                else binding_rule
                for binding_id, binding_rule in saved_rules.items()
            }
            clamps: dict[uuid.UUID, FbsRuleClamp] = {}
            for binding_id, binding_rule in rule.by_binding.items():
                if binding_rule.value < 0:
                    raise FbsStockRuleError(
                        "invalid_units",
                        message="Количество штук не может быть отрицательным.",
                    )
                if binding_rule.mode == "percent":
                    _check_percent(binding_rule.value)
                    continue
                if binding_rule.mode != "units":
                    raise FbsStockRuleError("invalid_rule_mode")
                if not binding_rule.units_configured:
                    continue
                # A stock event may make an already saved operator cap larger
                # than today's free stock. OFF/ON must preserve that cap (R8,
                # R14); clamp only a newly entered manual value.
                value_changed = any(
                    old_rules[product.id].by_binding[binding_id].mode != "units"
                    or old_rules[product.id].by_binding[binding_id].value
                    != binding_rule.value
                    for product in products
                )
                if not value_changed:
                    continue
                binding = binding_by_id[binding_id]
                free_by_product = await _free_stock_by_product_for_binding(
                    session,
                    tenant_id,
                    [product.id for product in products],
                    binding,
                )
                free_rows = [
                    (product, free_by_product[product.id]) for product in products
                ]
                limiting_product, minimum_free = min(
                    free_rows,
                    key=lambda item: item[1],
                )
                if binding_rule.value > minimum_free:
                    saved_rules[binding_id] = replace(
                        binding_rule,
                        value=minimum_free,
                    )
                    clamps[binding_id] = FbsRuleClamp(
                        binding_id=binding_id,
                        requested_value=binding_rule.value,
                        saved_value=minimum_free,
                        limiting_product_id=limiting_product.id,
                        limiting_product_name=limiting_product.name,
                    )

            applied: dict[uuid.UUID, dict[uuid.UUID, FbsBindingRule]] = {}
            for product in products:
                requested_product_bindings: dict[uuid.UUID, FbsBindingRule] = {}
                for binding_id, binding_rule in saved_rules.items():
                    binding = binding_by_id[binding_id]
                    if binding.marketplace == "ozon" and product.id not in ozon_links:
                        requested_product_bindings[binding_id] = replace(
                            binding_rule, publish=False
                        )
                    else:
                        requested_product_bindings[binding_id] = binding_rule
                applied[product.id] = requested_product_bindings

            for binding_id, binding in binding_by_id.items():
                disabled = {
                    product.id
                    for product in products
                    if binding_id in applied[product.id]
                    and old_rules[product.id].by_binding[binding_id].publish
                    and not applied[product.id][binding_id].publish
                }
                if disabled and binding.stock_sync_enabled:
                    await _clear_product_publication(session, binding, disabled)

            changed_marketplaces: set[str] = set()
            for product in products:
                pool_rows = pools_by_product[product.id]
                for binding_id, binding_rule in applied[product.id].items():
                    old_binding_rule = old_rules[product.id].by_binding[binding_id]
                    if old_binding_rule != binding_rule:
                        changed_marketplaces.add(binding_by_id[binding_id].marketplace)

                combined = dict(old_rules[product.id].by_binding)
                combined.update(applied[product.id])
                # До смены product-level режима каждая соседняя legacy-привязка
                # становится явной строкой. Иначе глобальные поля ниже задним
                # числом меняют не присланный оператором WB/Ozon-блок.
                for binding_id, binding_rule in combined.items():
                    requested = binding_id in applied[product.id]
                    pool = pool_rows.get(binding_id)
                    has_explicit_publish = (
                        pool is not None and pool.publish_enabled is not None
                    )
                    if pool is None:
                        pool = FbsBindingStockPool(
                            tenant_id=tenant_id,
                            binding_id=binding_id,
                            product_id=product.id,
                        )
                        session.add(pool)
                        pool_rows[binding_id] = pool
                    # ``binding_rule.publish`` is effective state: a technical
                    # transport OFF makes it false even when the operator's
                    # explicit per-binding decision remains ON. A partial save
                    # may materialize a missing legacy decision, but must not
                    # overwrite an untouched explicit decision with transport
                    # state (R8/R24, D7/R26).
                    if requested or not has_explicit_publish:
                        pool.publish_enabled = binding_rule.publish
                    if binding_rule.mode == "percent":
                        pool.percent = binding_rule.value
                        pool.units_configured = False
                        # У явного нового правила источник один. У нетронутой
                        # legacy-строки сохраняем неактивное старое число: оно
                        # не влияет на процент, но старый скрытый endpoint
                        # продолжает видеть свой прежний операторский потолок.
                        if requested:
                            pool.quantity = 0
                    else:
                        pool.percent = None
                        pool.units_configured = binding_rule.units_configured
                        pool.quantity = (
                            binding_rule.value if binding_rule.units_configured else 0
                        )
                    pool.updated_by = updated_by

                product.fbs_stock_sync_enabled = any(
                    combined[binding.id].publish
                    for binding in bindings
                    if binding.marketplace == "wb"
                )
                product.fbs_ozon_stock_sync_enabled = any(
                    combined[binding.id].publish
                    for binding in bindings
                    if binding.marketplace == "ozon" and product.id in ozon_links
                )
                product.fbs_units_mode = any(
                    item.publish and item.mode == "units" for item in combined.values()
                )
                product.fbs_same_everywhere = False
                product.fbs_percent = 0

            for binding_id in saved_rules:
                if any(
                    per_product_rules[binding_id].publish
                    for per_product_rules in applied.values()
                ):
                    binding_by_id[binding_id].stock_sync_enabled = True

            for marketplace in sorted(changed_marketplaces):
                if any(
                    binding_rule.publish
                    for per_product_rules in applied.values()
                    for binding_id, binding_rule in per_product_rules.items()
                    if binding_by_id[binding_id].marketplace == marketplace
                ):
                    schedule_seller_stock_publish(
                        session,
                        tenant_id,
                        seller_id,
                        marketplace,
                    )
            await session.commit()
            return FbsRuleSaveResult(updated_count=len(products), clamps=clamps)

        rule = _qualified_rule(rule, bindings)
        product_rules = {
            product.id: replace(
                rule,
                publish=old_rules[product.id].publishes("wb")
                if rule.publish is None else rule.publish,
                publish_ozon=(
                    old_rules[product.id].publishes("ozon")
                    if rule.publish_ozon is None else rule.publish_ozon
                )
                # WMS-456: без активной карточки Ozon эффективный флаг всегда
                # false — даже если оператор явно прислал true в этом запросе,
                # публиковать некуда, и в базу true не попадает (решение 3).
                and product.id in ozon_links,
            )
            for product in products
        }
        changed = {
            marketplace
            for marketplace in ("wb", "ozon")
            if any(
                _marketplace_rule_signature(old_rules[p.id], marketplace, bindings)
                != _marketplace_rule_signature(product_rules[p.id], marketplace, bindings)
                for p in products
            )
        }
        if rule.units_mode:
            # Legacy clients still get sign validation, but no fake stock
            # validation: the old calls calculated free stock and then ignored it.
            for effective_rule in product_rules.values():
                _validate_units(effective_rule)

        else:
            for effective_rule in product_rules.values():
                enabled_bindings = [b for b in served if effective_rule.publishes(b.marketplace)]
                enabled_keys = {_binding_key(b) for b in enabled_bindings}
                validate_rule(
                    replace(
                        effective_rule,
                        by_warehouse={
                            key: value
                            for key, value in effective_rule.by_warehouse.items()
                            if key in enabled_keys
                        },
                    ),
                    served_warehouse_count=len(enabled_bindings),
                )
        for binding in bindings:
            disabled = {
                p.id
                for p in products
                if old_rules[p.id].publishes(binding.marketplace)
                and not product_rules[p.id].publishes(binding.marketplace)
            }
            if disabled and binding.stock_sync_enabled:
                await _clear_product_publication(session, binding, disabled)

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
            addressed = {_binding_key(binding) for binding in served}
        else:
            addressed = set(rule.by_warehouse)
        for binding in served:
            if (
                _binding_key(binding) in addressed
                and binding.marketplace in changed
                and any(r.publishes(binding.marketplace) for r in product_rules.values())
            ):
                binding.stock_sync_enabled = True

        binding_by_key = {_binding_key(binding): binding for binding in bindings}
        for product in products:
            was_units_publish_enabled = product.fbs_units_mode and product.fbs_stock_sync_enabled
            product.fbs_ozon_stock_sync_enabled = product_rules[product.id].publishes("ozon")
            product.fbs_stock_sync_enabled = product_rules[product.id].publishes("wb")
            product.fbs_same_everywhere = rule.same_everywhere
            product.fbs_percent = rule.percent
            # Доля не стирается при переходе в штуки и наоборот: переключил галку
            # обратно — работает то, что было. Оба числа лежат рядом, режим решает,
            # какое из них читает публикация.
            product.fbs_units_mode = rule.units_mode
            pool_rows = await _pool_rows(session, product.id, [b.id for b in bindings])
            for warehouse_key, binding in binding_by_key.items():
                percent = rule.by_warehouse.get(warehouse_key)
                units = rule.units_by_warehouse.get(warehouse_key)
                pool = pool_rows.get(binding.id)
                was_explicit_zero = (
                    was_units_publish_enabled and pool is not None
                    and pool.units_configured and pool.quantity == 0
                )
                if (
                    binding.marketplace == "wb" and product_rules[product.id].publishes("wb")
                    and rule.units_mode and units == 0 and not was_explicit_zero
                ):
                    # A newly saved zero must not inherit suppression from the
                    # previous rule, even if its old confirmed amount was zero.
                    await session.execute(
                        update(FbsStockSyncItem)
                        .where(
                            FbsStockSyncItem.binding_id == binding.id,
                            FbsStockSyncItem.product_id == product.id,
                        )
                        .values(
                            status=STOCK_SYNC_STATUS_PENDING,
                            last_target_amount=0,
                            last_error_code=None,
                        )
                    )
                if pool is None:
                    if percent is None and units is None:
                        continue
                    pool = FbsBindingStockPool(
                        tenant_id=tenant_id,
                        binding_id=binding.id,
                        product_id=product.id,
                        quantity=int(units or 0) if rule.units_mode else 0,
                        units_configured=rule.units_mode and units is not None,
                        percent=percent,
                        updated_by=updated_by,
                    )
                    session.add(pool)
                    continue
                # A save through the legacy whole-product form intentionally
                # returns this row to Product-level switch semantics while the
                # WMS-483 explicit-zero marker keeps the selected value mode.
                pool.publish_enabled = None
                # Omitted units clear only that mode, preserving saved percentages.
                if not rule.units_mode or percent is not None:
                    pool.percent = percent
                if rule.units_mode:
                    pool.units_configured = units is not None
                    pool.quantity = int(units or 0)
                pool.updated_by = updated_by
        for marketplace in sorted(changed):
            if any(r.publishes(marketplace) for r in product_rules.values()):
                schedule_seller_stock_publish(session, tenant_id, seller_id, marketplace)
        await session.commit()
        return FbsRuleSaveResult(updated_count=len(products))


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
    await session.commit()
    return len(unique_ids)


async def publish_amounts_for_binding(
    session: AsyncSession,
    binding: FbsWarehouseBinding,
    products: list[Product],
    *,
    refresh_zero_product_ids: set[uuid.UUID] | None = None,
) -> dict[uuid.UUID, int]:
    """Сколько штук отправить в WB по этой привязке: product_id -> количество.

    Это тот самый «источник числа», который заменил сохранённый абсолютный лимит.
    Товар без правила или с выключенной публикацией не попадает в ответ.
    Последний ноль подтверждается при выключении, перед сохранением настройки.

    WMS-456. Товар без активной карточки Ozon (ProductMarketplaceLink) не
    попадает в ответ вовсе для Ozon-привязки — не с нулём, а отсутствием: ноль
    означал бы команду «опубликовать ноль», а sync_ozon_stocks посчитал бы
    такой товар без связки в missing_links. Тот же признак связки нужен и для
    WB-привязки: иначе фантомная озоновская доля отъедала бы часть общего
    остатка у WB внутри split_amounts (см. _effective_publish_ozon).
    """
    # WMS-376. Обслуживание склада решает только то, какие входящие заказы мы
    # видим, и к трансляции остатка отношения не имеет. Публикацией распоряжается
    # её собственная галка.
    if not binding.stock_sync_enabled:
        return {}
    ozon_links = await list_ozon_product_links(
        session, binding.tenant_id, {product.id for product in products}
    )
    applicable = [
        product
        for product in products
        if binding.marketplace != "ozon" or product.id in ozon_links
    ]
    if not applicable:
        return {}
    seller_bindings = await _seller_bindings(
        session, binding.tenant_id, binding.seller_id, publishing_only=True
    )
    if not any(row.id == binding.id for row in seller_bindings):
        return {}
    seller_bindings = [
        row for row in seller_bindings if row.wms_warehouse_id == binding.wms_warehouse_id
    ]
    product_ids = [product.id for product in applicable]
    breakdown = await fbs_stock_breakdown_by_product(
        session, binding.tenant_id, binding.wms_warehouse_id, product_ids
    )
    amounts: dict[uuid.UUID, int] = {}
    for product in applicable:
        pool_rows = await _pool_rows(session, product.id, [row.id for row in seller_bindings])
        if not _binding_has_rule(product, binding.id, pool_rows):
            continue
        rule = rule_from_product(
            product, pool_rows, seller_bindings, has_ozon_link=product.id in ozon_links
        )
        binding_rule = rule.by_binding.get(binding.id)
        if binding_rule is None or not binding_rule.publish:
            continue
        free = breakdown[product.id].free if product.id in breakdown else 0
        split = split_amounts(rule, free, seller_bindings, pool_rows=pool_rows)
        amounts[product.id] = split.get(binding.id, 0)
        # WMS-483: use the same free-stock snapshot as the published amount.
        # A missing allocation is not an explicit zero-unit operator limit.
        pool = pool_rows.get(binding.id)
        if pool is not None and pool.publish_enabled is not None:
            has_refresh_rule = bool(
                pool.publish_enabled
                and (
                    pool.percent is not None
                    or pool.units_configured
                    or int(pool.quantity or 0) > 0
                )
            )
        elif binding_rule.mode == "units":
            has_refresh_rule = bool(
                pool is not None
                and (pool.units_configured or int(pool.quantity or 0) > 0)
            )
        elif product.fbs_same_everywhere:
            has_refresh_rule = int(product.fbs_percent or 0) > 0
        else:
            has_refresh_rule = bool(pool is not None and int(pool.percent or 0) > 0)
        explicit_zero_units = (
            binding_rule.mode == "units"
            and binding_rule.units_configured
            and binding_rule.value == 0
        )
        if (
            refresh_zero_product_ids is not None
            and binding.marketplace == "wb"
            and binding_rule.publish
            and has_refresh_rule
            and (free == 0 or explicit_zero_units)
        ):
            refresh_zero_product_ids.add(product.id)
    return amounts
