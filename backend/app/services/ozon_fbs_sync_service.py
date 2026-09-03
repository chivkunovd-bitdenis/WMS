"""Ozon FBS synchronization behind the shared marketplace provider boundary.

The current task runs this code only with ``FakeMarketplaceTransport``.  The
service still performs the real local side of the contract: provider rows are
upserted into the shared FBS tables, statuses are mapped to existing local
states, and stock payloads are built from the same physical allocation pool.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_order import (
    FBS_ORDER_STATUS_ASSEMBLING,
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_DONE,
    FBS_ORDER_STATUS_EXTERNAL_PROCESSING,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_IN_SUPPLY,
    FBS_ORDER_STATUS_NEW,
    FBS_ORDER_STATUS_PACKED,
    FBS_ORDER_STATUS_SORTED,
    MAPPING_STATUS_MAPPED,
    MAPPING_STATUS_MISSING,
    MARKING_KIND_IMEI,
    MARKING_KIND_SGTIN,
    MARKING_KIND_UIN,
    RESERVE_STATUS_NO_STOCK,
    RESERVE_STATUS_SKIPPED_NO_PRODUCT,
    RESERVE_STATUS_WAREHOUSE_UNMAPPED,
    FbsOrder,
    FbsOrderProduct,
)
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.schemas.ozon_fbs_api import OzonPostingV4PostingFbsUnfulfilledListResponsePostingsProducts
from app.services.fbs_stock_sync_service import (
    STOCK_SYNC_STATUS_NOTHING_TO_PUBLISH,
)
from app.services.marketplace_account_service import MarketplaceAccountService
from app.services.marketplace_provider import MarketplaceProviderError, OzonMarketplaceProvider
from app.services.marketplace_stock_sync_result import SellerStockSyncResult
from app.services.wb_marketplace_orders_service import _release_reservation, _try_reserve_order

OZON_FBS_DEADLINE_HOURS = 120

# Ключ в `meta_details_json`, по которому видно: Ozon уже ответил, нужна ли
# маркировка по этому отправлению. Без него пустое требование неотличимо от
# неполученного, и гейт выпуска вынужден гадать.
OZON_REQUIREMENTS_KEY = "ozon_requirements"

# Словарь статусов взят из описания поля `status` в официальной спецификации
# (`posting.v4.PostingFbsUnfulfilledListResponse.Postings`, `v3FbsPostingDetail`),
# а не из тестовой фикстуры, как было раньше.
#
# Что здесь важно и чего не было:
#
# * «Новый» у Ozon ровно один — `awaiting_packaging`: только в нём оператору
#   есть что делать. Раньше новым считался и `awaiting_deliver`, который
#   означает «уже собрано, ждёт отгрузки»: собранное отправление показывалось
#   как новое и его можно было взять в работу второй раз.
# * `awaiting_approve`, `awaiting_verification`, `awaiting_registration` — это
#   состояния самого Ozon до и после сборки; брать их в работу нельзя.
# * `delivered` в перечне Ozon есть, но только у карточки отправления
#   (`/v3/posting/fbs/get`). В списках его нет: там доставку видно подстатусом
#   `posting_delivered`/`posting_received`. Раньше мы ждали `delivered`/`done`
#   на верхнем уровне и заказ Ozon не доходил до «завершён» никогда.
# * `arbitration` и `client_arbitration` — это спор по доставке, а не отмена.
#   Считать их отменой опасно: отмена разворачивает отгрузку и снимает резерв.
_OZON_NEW_STATUSES = frozenset({"new", "awaiting_packaging"})
_OZON_ASSEMBLED_STATUSES = frozenset({"awaiting_deliver"})
_OZON_DELIVERY_STATUSES = frozenset({"delivering", "driver_pickup", "sent_by_seller"})
# «Идёт приёмка» — это Ozon подтвердил, что забрал отправление в пункте приёма.
# Ближайший аналог вайлдберрисовского `sorted`, и точно так же это момент, когда
# работа склада по заказу считается сделанной и попадает в счёт.
_OZON_ACCEPTED_STATUSES = frozenset({"acceptance_in_progress"})
_OZON_DONE_STATUSES = frozenset({"delivered", "done"})
_OZON_DONE_SUBSTATUSES = frozenset({"posting_delivered", "posting_received"})
_OZON_CANCELLED_STATUSES = frozenset(
    {"cancelled", "canceled", "cancelled_from_split_pending"}
)

# Этапы, которые ставит наш собственный процесс. Опрос Ozon не имеет права
# затирать их своим «отправление ещё не собрано»: заказ, взятый в поставку,
# иначе выдёргивало бы обратно в «новые» каждые десять минут.
_LOCAL_WORKFLOW_STATUSES = frozenset(
    {
        FBS_ORDER_STATUS_IN_SUPPLY,
        FBS_ORDER_STATUS_ASSEMBLING,
        FBS_ORDER_STATUS_PACKED,
        FBS_ORDER_STATUS_SORTED,
        FBS_ORDER_STATUS_IN_DELIVERY,
    }
)

# Состояния, в которых работа склада по заказу считается сделанной и попадает
# в счёт. Совпадают с теми, что уже приняты для Wildberries: подтверждение
# приходит от маркетплейса, а не от нашей кнопки.
_BILLABLE_STATUSES = frozenset({FBS_ORDER_STATUS_SORTED, FBS_ORDER_STATUS_DONE})

# Требования отправления Ozon (`requirements`) в терминах наших видов маркировки.
_OZON_REQUIREMENT_KINDS: tuple[tuple[str, str], ...] = (
    ("products_requiring_mandatory_mark", MARKING_KIND_SGTIN),
    ("products_requiring_jw_uin", MARKING_KIND_UIN),
    ("products_requiring_imei", MARKING_KIND_IMEI),
)


def _text(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int):
            return str(value)
    return None


def _nested(row: dict[str, Any], *path: str) -> Any:
    current: Any = row
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _nested_text(row: dict[str, Any], *path: str) -> str | None:
    value = _nested(row, *path)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, int):
        return str(value)
    return None


def _warehouse_id(row: dict[str, Any]) -> str | None:
    """Ozon кладёт склад внутрь `delivery_method`, а не на верхний уровень.

    На верхнем уровне отправления поля `warehouse_id` нет вовсе — это видно в
    схеме `posting.v4.PostingFbsUnfulfilledListResponse.Postings`. Пока мы
    искали его там, даже правильно заведённая привязка склада не находилась и
    каждый заказ Ozon получал `warehouse_unmapped`.
    """
    nested = _nested_text(row, "delivery_method", "warehouse_id")
    if nested is not None:
        return nested
    return _text(row, "warehouse_id", "warehouseId")


def _posting_barcode(row: dict[str, Any]) -> str | None:
    """Штрихкоды отправления лежат в объекте `barcodes`, а не на верхнем уровне."""
    for key in ("lower_barcode", "upper_barcode"):
        value = _nested_text(row, "barcodes", key)
        if value is not None:
            return value
    return _text(row, "barcode")


def _money_kopecks(value: Any) -> int | None:
    """Цена Ozon — строка рублей в объекте `money.postingMoney`.

    В нашей колонке `FbsOrder.price` лежат копейки: у Wildberries цена приходит
    умноженной на сто (фикстуры бэкенда и эмулятора — 199900 при цене 1999 ₽).
    Смешать в одной колонке рубли и копейки — тихо испортить данные, поэтому
    приводим озоновскую цену к тем же копейкам.
    """
    if isinstance(value, dict):
        value = value.get("amount")
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return round(float(value) * 100)
    if isinstance(value, str) and value.strip():
        try:
            return round(float(value.strip().replace(",", ".")) * 100)
        except ValueError:
            return None
    return None


def _posting_price_kopecks(row: dict[str, Any]) -> int | None:
    """Сумма отправления: у Ozon цены нет на верхнем уровне, только по позициям."""
    total = 0
    seen = False
    financial = _nested(row, "financial_data", "products")
    products = financial if isinstance(financial, list) else row.get("products")
    if isinstance(products, list):
        for product in products:
            if not isinstance(product, dict):
                continue
            amount = _money_kopecks(product.get("price"))
            if amount is None:
                continue
            quantity = product.get("quantity")
            total += amount * (quantity if isinstance(quantity, int) and quantity > 0 else 1)
            seen = True
    if seen:
        return total
    return _money_kopecks(row.get("price"))


def _requirement_kinds(row: dict[str, Any]) -> tuple[list[str], bool]:
    """Виды маркировки, которые Ozon требует по этому отправлению.

    Второй элемент говорит, ответил ли Ozon про требования вообще: пустой
    список при «ответил» — это «не требуется», а при «не ответил» — «мы не
    знаем». Разница принципиальная: гейт выпуска не имеет права трактовать
    незнание как разрешение.
    """
    requirements = row.get("requirements")
    if not isinstance(requirements, dict):
        return [], False
    kinds: list[str] = []
    for field, kind in _OZON_REQUIREMENT_KINDS:
        values = requirements.get(field)
        if isinstance(values, list) and values and kind not in kinds:
            kinds.append(kind)
    return kinds, True


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(tz=UTC)


def _legacy_numeric_order_id(external_order_id: str) -> int:
    """Fill the legacy non-null WB id without sharing WB's positive id space."""
    digest = hashlib.blake2b(external_order_id.encode("utf-8"), digest_size=8).digest()
    return -(int.from_bytes(digest, "big", signed=False) & ((1 << 63) - 1)) or -1


def _local_status(raw_status: str | None, raw_substatus: str | None = None) -> str:
    normalized = (raw_status or "").strip().lower()
    substatus = (raw_substatus or "").strip().lower()
    if normalized in _OZON_CANCELLED_STATUSES:
        return FBS_ORDER_STATUS_CANCELLED
    if normalized in _OZON_DONE_STATUSES or substatus in _OZON_DONE_SUBSTATUSES:
        return FBS_ORDER_STATUS_DONE
    if normalized in _OZON_ACCEPTED_STATUSES:
        return FBS_ORDER_STATUS_SORTED
    if normalized in _OZON_DELIVERY_STATUSES:
        return FBS_ORDER_STATUS_IN_DELIVERY
    if normalized in _OZON_NEW_STATUSES:
        return FBS_ORDER_STATUS_NEW
    # `awaiting_deliver` (уже собрано) и всё остальное — работа маркетплейса,
    # а не приглашение оператору собрать отправление ещё раз.
    if normalized in _OZON_ASSEMBLED_STATUSES:
        return FBS_ORDER_STATUS_EXTERNAL_PROCESSING
    return FBS_ORDER_STATUS_EXTERNAL_PROCESSING


async def _credentials(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> tuple[str, str]:
    return await MarketplaceAccountService(session).stored_credentials(tenant_id, seller_id)


def _stock_error_code(error: MarketplaceProviderError) -> str:
    if error.is_account_blocked:
        return "ozon_account_blocked"
    if error.status_code in {401, 403}:
        return "ozon_auth_failed"
    if error.status_code == 429:
        return "ozon_rate_limited"
    return "ozon_unavailable"


async def sync_ozon_stocks(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    provider: OzonMarketplaceProvider,
) -> SellerStockSyncResult:
    """Publish each Ozon binding's explicitly allocated pool through the provider boundary."""
    bindings = list(
        (
            await session.execute(
                select(FbsWarehouseBinding)
                .where(
                    FbsWarehouseBinding.tenant_id == tenant_id,
                    FbsWarehouseBinding.seller_id == seller_id,
                    FbsWarehouseBinding.marketplace == "ozon",
                    FbsWarehouseBinding.is_active.is_(True),
                    FbsWarehouseBinding.stock_sync_enabled.is_(True),
                )
                .order_by(FbsWarehouseBinding.external_warehouse_id)
            )
        )
        .scalars()
        .all()
    )
    result = SellerStockSyncResult()
    if not bindings:
        return result

    client_id, api_key = await _credentials(session, tenant_id, seller_id)
    for binding in bindings:
        result.bindings_processed += 1
        if binding.external_warehouse_id is None or not binding.external_warehouse_id.isdigit():
            binding.last_sync_status = "error"
            binding.last_error_code = "ozon_warehouse_id_invalid"
            binding.last_sync_at = datetime.now(tz=UTC)
            result.binding_errors += 1
            result.errors += 1
            continue

        rows = list(
            (
                await session.execute(
                    select(FbsBindingStockPool, ProductMarketplaceLink)
                    .outerjoin(
                        ProductMarketplaceLink,
                        and_(
                            ProductMarketplaceLink.tenant_id == tenant_id,
                            ProductMarketplaceLink.seller_id == seller_id,
                            ProductMarketplaceLink.product_id == FbsBindingStockPool.product_id,
                            ProductMarketplaceLink.marketplace == "ozon",
                            ProductMarketplaceLink.is_active.is_(True),
                        ),
                    )
                    .where(FbsBindingStockPool.binding_id == binding.id)
                    .order_by(FbsBindingStockPool.product_id)
                )
            ).all()
        )
        stocks: list[dict[str, object]] = []
        missing_links = 0
        for pool, link in rows:
            if link is None or (not link.external_offer_id and not link.external_sku):
                missing_links += 1
                continue
            stock: dict[str, object] = {
                "warehouse_id": int(binding.external_warehouse_id),
                "stock": max(int(pool.quantity), 0),
            }
            if link.external_offer_id:
                stock["offer_id"] = link.external_offer_id
            # `product_id` и `sku` у Ozon — разные числа: живой ответ
            # `/v4/product/info/stocks` по одной карточке отдаёт
            # {"product_id": 6204279711, "sku": 5680762790}. Раньше в поле с
            # именем `product_id` клали SKU, то есть подписывали остаток чужим
            # идентификатором. Кладём то, что действительно есть в связке.
            if link.external_product_id and link.external_product_id.isdigit():
                stock["product_id"] = int(link.external_product_id)
            stocks.append(stock)

        result.products_targeted += len(stocks)
        result.products_zeroed += sum(stock.get("stock") == 0 for stock in stocks)
        if missing_links:
            result.errors += missing_links
            result.binding_errors += 1
            binding.last_sync_status = "error"
            binding.last_error_code = "product_mapping_missing"
        if not stocks:
            if not missing_links:
                binding.last_sync_status = STOCK_SYNC_STATUS_NOTHING_TO_PUBLISH
                binding.last_error_code = None
            binding.last_sync_at = datetime.now(tz=UTC)
            continue

        try:
            await provider.publish_stocks(
                client_id=client_id,
                api_key=api_key,
                stocks=stocks,
            )
        except MarketplaceProviderError as error:
            result.errors += len(stocks)
            result.binding_errors += 1
            binding.last_sync_status = "error"
            binding.last_error_code = _stock_error_code(error)
        else:
            result.products_confirmed += len(stocks)
            if not missing_links:
                binding.last_sync_status = "confirmed"
                binding.last_error_code = None
        binding.last_sync_at = datetime.now(tz=UTC)

    await session.commit()
    return result


async def _product_id_for_row(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    row: dict[str, Any],
) -> uuid.UUID | None:
    sku = _text(row, "sku", "product_sku")
    offer_id = _text(row, "offer_id", "offerId")
    if sku is None and offer_id is None:
        return None
    identity_filters = []
    if sku is not None:
        identity_filters.append(ProductMarketplaceLink.external_sku == sku)
    if offer_id is not None:
        identity_filters.append(ProductMarketplaceLink.external_offer_id == offer_id)
    stmt = select(ProductMarketplaceLink.product_id).where(
        ProductMarketplaceLink.tenant_id == tenant_id,
        ProductMarketplaceLink.seller_id == seller_id,
        ProductMarketplaceLink.marketplace == "ozon",
        ProductMarketplaceLink.is_active.is_(True),
        or_(*identity_filters),
    )
    rows = list((await session.execute(stmt.limit(2))).scalars().all())
    return rows[0] if len(rows) == 1 else None


async def _binding_for_row(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    row: dict[str, Any],
) -> FbsWarehouseBinding | None:
    external_warehouse_id = _warehouse_id(row)
    if external_warehouse_id is None:
        return None
    stmt = select(FbsWarehouseBinding).where(
        FbsWarehouseBinding.tenant_id == tenant_id,
        FbsWarehouseBinding.seller_id == seller_id,
        FbsWarehouseBinding.marketplace == "ozon",
        FbsWarehouseBinding.external_warehouse_id == external_warehouse_id,
        FbsWarehouseBinding.is_active.is_(True),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _posting_products_for_row(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    row: dict[str, Any],
) -> list[FbsOrderProduct]:
    raw_products = row.get("products")
    if not isinstance(raw_products, list):
        return []

    positions: list[FbsOrderProduct] = []
    for position_index, raw_product in enumerate(raw_products):
        product_row = OzonPostingV4PostingFbsUnfulfilledListResponsePostingsProducts.model_validate(
            raw_product
        )
        provider_data = product_row.model_dump(mode="json", exclude_none=True)
        positions.append(
            FbsOrderProduct(
                product_id=await _product_id_for_row(session, tenant_id, seller_id, provider_data),
                ozon_sku=product_row.sku,
                offer_id=product_row.offer_id,
                name=product_row.name,
                quantity=int(product_row.quantity or 0),
                position_index=position_index,
                provider_data_json=provider_data,
            )
        )
    return positions


def _primary_product_id(
    positions: list[FbsOrderProduct], fallback_product_id: uuid.UUID | None
) -> uuid.UUID | None:
    return next(
        (position.product_id for position in positions if position.product_id is not None),
        fallback_product_id,
    )


def _positions_are_mapped(
    positions: list[FbsOrderProduct], fallback_product_id: uuid.UUID | None
) -> bool:
    return (
        all(position.product_id is not None for position in positions)
        if positions
        else fallback_product_id is not None
    )


def _position_signature(position: FbsOrderProduct) -> tuple[int | None, int, dict[str, Any] | None]:
    return position.ozon_sku, position.quantity, position.provider_data_json


def _apply_delivery_method(order: FbsOrder, row: dict[str, Any]) -> None:
    """Сохранить способ доставки Ozon: без него не создать перевозку.

    Создание перевозки читает `ozon_delivery_method_id` из деталей заказа, но
    записать этот ключ было некому — грепом по бэкенду находился один читатель
    и ни одного писателя. Идентификатор приходит в каждом отправлении, в
    `delivery_method.id`.
    """
    delivery_method_id = _nested_text(row, "delivery_method", "id")
    if delivery_method_id is None or not delivery_method_id.isdigit():
        return
    details = dict(order.meta_details_json or {})
    if details.get("ozon_delivery_method_id") == delivery_method_id:
        return
    details["ozon_delivery_method_id"] = delivery_method_id
    order.meta_details_json = details


def _apply_requirements(order: FbsOrder, kinds: list[str], seen: bool) -> None:
    """Записать требования маркировки Ozon туда, где их ищет гейт выпуска.

    Раньше `required_meta_json` заполнял ровно один писатель — вайлдберрисовский
    разбор заказа. У заказа Ozon поле оставалось пустым навсегда, а пустое
    требование гейт трактовал как «маркировка не нужна». Отправление Ozon с
    маркируемым товаром считалось готовым к отгрузке без единого кода.

    Отдельно храним признак «Ozon ответил про требования»: пустой список при
    полученном ответе — это «не требуется», а при неполученном — «мы не знаем».
    Гейт обязан различать эти два случая.
    """
    if not seen:
        return
    order.required_meta_json = list(kinds)
    details = dict(order.meta_details_json or {})
    details[OZON_REQUIREMENTS_KEY] = {"kinds": list(kinds)}
    order.meta_details_json = details


async def _apply_status(
    session: AsyncSession,
    order: FbsOrder,
    raw_status: str | None,
    raw_substatus: str | None = None,
) -> bool:
    normalized = (raw_status or "").strip().lower() or None
    substatus = (raw_substatus or "").strip().lower() or None
    local = _local_status(normalized, substatus)
    previous = order.status
    previous_wb_status = order.wb_status
    order.wb_status = normalized
    order.supplier_status = (
        "new" if local == FBS_ORDER_STATUS_NEW else (substatus or normalized)
    )
    # Опрос Ozon двигает заказ вперёд и в конечные состояния, но никогда не
    # тянет назад через наши собственные этапы. Иначе заказ, уже взятый в
    # поставку, каждые десять минут возвращался бы в «новые», а собранный —
    # в «ожидает сборки».
    terminal = {FBS_ORDER_STATUS_CANCELLED, FBS_ORDER_STATUS_DONE}
    if local in terminal:
        order.status = local
    elif local == FBS_ORDER_STATUS_SORTED:
        if previous not in terminal:
            order.status = local
    elif local == FBS_ORDER_STATUS_IN_DELIVERY:
        if previous not in terminal and previous != FBS_ORDER_STATUS_SORTED:
            order.status = local
    elif previous not in _LOCAL_WORKFLOW_STATUSES and previous not in terminal:
        order.status = local
    changed = previous != order.status or previous_wb_status != normalized
    if order.status in terminal:
        if order.status == FBS_ORDER_STATUS_CANCELLED:
            from app.services.fbs_cancellation_service import (
                reverse_fbs_shipment_if_needed,
            )

            await reverse_fbs_shipment_if_needed(
                session,
                order,
                actor_user_id=None,
            )
        await _release_reservation(session, order)
    if previous != order.status and order.status in _BILLABLE_STATUSES:
        # Заказы Ozon не тарифицировались вообще: единственная точка, где
        # появляются деньги за сборку FBS, вызывалась только из
        # вайлдберрисовского обработчика статусов. Селлер мог сдать через
        # фулфилмент сотню заказов Ozon, они уезжали, и в счёт не попадало ни
        # копейки. Начисление идемпотентно: повторный проход опроса его не
        # задваивает.
        from app.services.fbs_order_billing_service import record_fbs_order_confirmed

        await record_fbs_order_confirmed(session, order)
    return changed


async def sync_ozon_orders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    provider: OzonMarketplaceProvider,
    _http_client: httpx.AsyncClient,
) -> dict[str, int]:
    client_id, api_key = await _credentials(session, tenant_id, seller_id)
    rows = await provider.fetch_orders(client_id=client_id, api_key=api_key)
    upserted = 0
    created = 0
    statuses_updated = 0
    for row in rows:
        external_order_id = _text(row, "posting_number", "order_id", "id")
        if external_order_id is None:
            continue
        existing = (
            await session.execute(
                select(FbsOrder)
                .options(selectinload(FbsOrder.product_positions))
                .where(
                    FbsOrder.tenant_id == tenant_id,
                    FbsOrder.seller_id == seller_id,
                    FbsOrder.marketplace == "ozon",
                    FbsOrder.external_order_id == external_order_id,
                )
            )
        ).scalar_one_or_none()
        raw_status = _text(row, "status")
        raw_substatus = _text(row, "substatus")
        if raw_status is None:
            raw_status = raw_substatus
        required_kinds, requirements_seen = _requirement_kinds(row)
        fallback_product_id = await _product_id_for_row(session, tenant_id, seller_id, row)
        positions = await _posting_products_for_row(session, tenant_id, seller_id, row)
        has_positions_payload = isinstance(row.get("products"), list)
        product_id = _primary_product_id(positions, fallback_product_id)
        positions_mapped = _positions_are_mapped(positions, fallback_product_id)
        if existing is not None:
            composition_changed = has_positions_payload and [
                _position_signature(position) for position in existing.product_positions
            ] != [_position_signature(position) for position in positions]
            if composition_changed:
                await _release_reservation(session, existing)
                existing.product_positions.clear()
                await session.flush()
                existing.product_id = product_id
                if positions:
                    existing.product_positions.extend(positions)
                    existing.wb_nm_id = positions[0].ozon_sku
                    existing.wb_article = positions[0].offer_id
                existing.mapping_status = (
                    MAPPING_STATUS_MAPPED if positions_mapped else MAPPING_STATUS_MISSING
                )
                details = dict(existing.meta_details_json or {})
                details["ozon_products"] = [
                    position.provider_data_json
                    for position in positions
                    if position.provider_data_json
                ]
                existing.meta_details_json = details
            _apply_delivery_method(existing, row)
            _apply_requirements(existing, required_kinds, requirements_seen)
            statuses_updated += int(
                await _apply_status(session, existing, raw_status, raw_substatus)
            )
            if composition_changed and positions:
                await session.flush()
                await _try_reserve_order(session, existing)
            upserted += 1
            continue

        binding = await _binding_for_row(session, tenant_id, seller_id, row)
        # У отправления Ozon нет поля `created_at`: дата начала обработки живёт
        # в `in_process_at`. Пока читали `created_at`, дата создания молча
        # подменялась на «сейчас» у каждого заказа.
        created_at = _parse_datetime(
            row.get("in_process_at") or row.get("created_at") or row.get("createdAt")
        )
        deadline_at = _parse_datetime(row.get("shipment_date") or row.get("shipmentDate"))
        if deadline_at <= created_at:
            deadline_at = created_at + timedelta(hours=OZON_FBS_DEADLINE_HOURS)
        if not positions_mapped:
            reserve_status = RESERVE_STATUS_SKIPPED_NO_PRODUCT
        elif binding is None:
            reserve_status = RESERVE_STATUS_WAREHOUSE_UNMAPPED
        else:
            reserve_status = RESERVE_STATUS_NO_STOCK
        order = FbsOrder(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=binding.wms_warehouse_id if binding is not None else None,
            product_id=product_id,
            marketplace="ozon",
            external_order_id=external_order_id,
            wb_order_id=_legacy_numeric_order_id(external_order_id),
            wb_warehouse_id=binding.wb_warehouse_id if binding is not None else None,
            wb_article=(positions[0].offer_id if positions else _text(row, "offer_id", "offerId")),
            wb_nm_id=positions[0].ozon_sku if positions else None,
            wb_barcode=_posting_barcode(row),
            price=_posting_price_kopecks(row),
            created_at_wb=created_at,
            deadline_at=deadline_at,
            mapping_status=MAPPING_STATUS_MAPPED if positions_mapped else MAPPING_STATUS_MISSING,
            reserve_status=reserve_status,
        )
        if positions:
            order.product_positions.extend(positions)
            order.meta_details_json = {
                "ozon_products": [
                    position.provider_data_json
                    for position in positions
                    if position.provider_data_json
                ]
            }
        _apply_delivery_method(order, row)
        _apply_requirements(order, required_kinds, requirements_seen)
        await _apply_status(session, order, raw_status, raw_substatus)
        session.add(order)
        await session.flush()
        await _try_reserve_order(session, order)
        created += 1
        upserted += 1
    await session.commit()
    return {
        "orders_upserted": upserted,
        "orders_created": created,
        "statuses_updated": statuses_updated,
        "stocks_bindings_processed": 0,
        "stock_errors": 0,
    }


async def sync_ozon_order_statuses(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    provider: OzonMarketplaceProvider,
    _http_client: httpx.AsyncClient,
) -> int:
    orders = list(
        (
            await session.execute(
                select(FbsOrder).where(
                    FbsOrder.tenant_id == tenant_id,
                    FbsOrder.seller_id == seller_id,
                    FbsOrder.marketplace == "ozon",
                    FbsOrder.external_order_id.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if not orders:
        return 0
    client_id, api_key = await _credentials(session, tenant_id, seller_id)
    external_ids = [
        order.external_order_id for order in orders if order.external_order_id is not None
    ]
    rows = await provider.fetch_statuses(
        client_id=client_id,
        api_key=api_key,
        order_ids=external_ids,
    )
    by_external = {
        external_id: row
        for row in rows
        if (external_id := _text(row, "posting_number", "order_id", "id")) is not None
    }
    updated = 0
    for order in orders:
        row = by_external.get(order.external_order_id or "")
        if row is None:
            continue
        # Требование маркировки приходит в той же карточке отправления. Читаем
        # его и здесь: у заказа, заведённого до появления разбора требований,
        # оно иначе не появилось бы никогда.
        required_kinds, requirements_seen = _requirement_kinds(row)
        _apply_requirements(order, required_kinds, requirements_seen)
        status_value = _text(row, "status")
        substatus_value = _text(row, "substatus")
        updated += int(
            await _apply_status(
                session,
                order,
                status_value if status_value is not None else substatus_value,
                substatus_value,
            )
        )
    await session.commit()
    return updated
