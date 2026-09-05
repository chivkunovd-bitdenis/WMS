"""FBS shipment — delivery preflight, safe deliver, supply barcode."""

from __future__ import annotations

import hashlib
import logging
import uuid
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx
from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.settings import settings
from app.models.fbs_order import (
    FBS_ORDER_STATUS_ASSEMBLING,
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_DEFECT,
    FBS_ORDER_STATUS_DONE,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_IN_SUPPLY,
    FBS_ORDER_STATUS_PACKED,
    MARKING_KIND_SGTIN,
    STICKER_STATUS_APPLIED,
    STICKER_STATUS_PRINT_OPENED,
    STICKER_STATUS_READY,
    FbsOrder,
    current_order_marking,
)
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_PVZ,
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_DONE,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FbsSupply,
)
from app.models.fbs_wb_operation import (
    WB_OPERATION_STATE_CONFIRMED,
    WB_OPERATION_STATE_FAILED,
    WB_OPERATION_STATE_PENDING,
    WB_OPERATION_STATE_PENDING_CONFIRMATION,
    FbsWbOperation,
)
from app.models.storage_location import StorageLocation
from app.services import fbs_marking_service as marking_svc
from app.services import fbs_packing_box_service as packing_box_svc
from app.services import fbs_shipment_pvz_service as pvz_svc
from app.services import fbs_shipment_source_service as source_svc
from app.services import fbs_supply_composition_service as composition_svc
from app.services import inventory_service as inventory_svc
from app.services.fbs_ozon_packaging_service import (
    OzonPackagingError,
)
from app.services.fbs_ozon_packaging_service import (
    plan_shipment_sources as plan_ozon_shipment_sources,
)
from app.services.fbs_ozon_packaging_service import (
    prepare_shipment_sources as prepare_ozon_shipment_sources,
)
from app.services.fbs_ozon_packaging_service import (
    write_off_order as write_off_ozon_order,
)
from app.services.fbs_print_asset_service import upsert_supply_qr_asset_from_bytes
from app.services.fbs_print_asset_storage import FbsPrintAssetStorageError
from app.services.fbs_supply_reconcile_service import (
    WB_RECONCILE_NOT_DELIVERED,
    create_pending_deliver_operation,
    get_active_deliver_operation_for_supply,
    get_deliver_operation_by_idempotency,
    list_deliver_operations_for_supply,
    mark_deliver_operation_confirmed,
    mark_operation_failed,
    mark_operation_pending_confirmation,
    reconcile_supply_delivered,
    request_hash_for_deliver,
)
from app.services.inventory_container_service import ContainerKind
from app.services.marketplace_account_service import (
    MarketplaceAccountError,
    MarketplaceAccountService,
)
from app.services.marketplace_provider import (
    MarketplaceProviderError,
    OzonMarketplaceProvider,
    provider_error_message,
)
from app.services.marketplace_seller_lock_service import marketplace_seller_lock
from app.services.ozon_fbs_process_service import (
    OzonFbsProcessError,
    OzonHandoffProgress,
    OzonHandoffResult,
    handoff_supply,
)
from app.services.ozon_provider_factory import build_ozon_provider, ozon_live_api_enabled
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.wb_marketplace_orders_service import (
    _apply_wb_status_to_order,
    _release_reservation,
    _supplier_status_from_row,
    _wb_status_from_row,
)
from app.services.wildberries_client import (
    deliver_marketplace_supply,
    fetch_marketplace_orders_status,
    fetch_marketplace_supply_barcode,
)
from app.services.wildberries_credentials_service import (
    _seller_in_tenant,
    get_decrypted_marketplace_token,
)
from app.services.wildberries_errors import (
    WildberriesBusinessError,
    WildberriesClientError,
    log_wb_client_error,
    translate_wb_message,
    truncate_wb_response_body,
    wb_error_context,
    wb_error_ref,
    wb_operator_message,
)
from app.services.wildberries_fbs_client import split_marketplace_order_id_batches

_DELIVER_READY_STICKER_STATUSES = frozenset(
    {STICKER_STATUS_READY, STICKER_STATUS_PRINT_OPENED, STICKER_STATUS_APPLIED}
)
_TERMINAL_ORDER_STATUSES = frozenset(
    {FBS_ORDER_STATUS_CANCELLED, FBS_ORDER_STATUS_DONE, FBS_ORDER_STATUS_DEFECT}
)
_DELIVER_READY_ORDER_STATUSES = frozenset({FBS_ORDER_STATUS_PACKED})
_PACKAGING_PENDING_ORDER_STATUSES = frozenset(
    {FBS_ORDER_STATUS_IN_SUPPLY, FBS_ORDER_STATUS_ASSEMBLING}
)
# ⛔⛔⛔ РЕШЕНИЕ ВЛАДЕЛЬЦА ОТ 01.09.2026 — НЕ ОТМЕНЯТЬ БЕЗ ЕГО СЛОВ ⛔⛔⛔
#
# Уровень проверки перед передачей поставки. Смысл строго такой:
#   blocker — передача невозможна физически или уже состоялась;
#   warning — оператор должен это знать, но останавливать его нельзя;
#   info    — просто факт, зелёная галочка.
#
# У Wildberries `blocker` разрешён РОВНО двум проверкам, они перечислены в
# WB_ALLOWED_BLOCKER_CODES. Всё остальное — стикеры, Честный знак, физические
# короба, распределение заказов по коробам, QR коробов и грузомест, расхождения
# состава — оператора НЕ останавливает. Владелец: «напечатали, галочку
# поставили — хватит; ничто не должно мешать положить в короб и отгрузить».
# Если Wildberries чего-то действительно не хватает, он откажет сам, и это будет
# честный отказ маркетплейса, а не наша выдумка.
#
# Эти семь внутренних блокировок с 04.08.2026 держали склад: оператор доходил
# до финальной кнопки и упирался в серую кнопку без выхода. Восстанавливать их
# нельзя ни напрямую, ни под новым именем. Набор заморожен тестом
# test_wb_delivery_blocker_codes_are_frozen, а _apply_wb_blocker_policy ниже
# понижает до предупреждения любую новую проверку, которую кто-то попробует
# сделать блокирующей для WB в обход этого списка.
CHECK_BLOCKER = "blocker"
CHECK_WARNING = "warning"
CHECK_INFO = "info"

WB_ALLOWED_BLOCKER_CODES = frozenset({"supply_bad_status", "supply_empty"})

# Правило одно, значит и текст один. Раньше оно жило в двух местах с разными
# формулировками, и вторая говорила «обновите preflight» — слово, которое
# кладовщику не значит ничего.
_STALE_PREFLIGHT_MESSAGE = (
    "Пока было открыто окно передачи, поставка изменилась. Закройте окно и "
    "откройте заново — проверки пересчитаются."
)
_DELIVER_ALLOWED_DELIVERY_TYPES = frozenset({FBS_DELIVERY_TYPE_WAREHOUSE_SC, FBS_DELIVERY_TYPE_PVZ})
_DELIVER_BLOCKED_SUPPLY_STATUSES = frozenset(
    {
        FBS_SUPPLY_STATUS_IN_DELIVERY,
        FBS_SUPPLY_STATUS_DONE,
    }
)

logger = logging.getLogger(__name__)

_WB_DISPATCH_PENDING_MESSAGE = "fix them to dispatch items"


class FbsShipmentError(Exception):
    def __init__(
        self,
        code: str,
        *,
        message: str | None = None,
        context: dict[str, Any] | None = None,
        retryable: bool = False,
        http_status: int | None = None,
    ) -> None:
        self.code = code
        self.message = message or code
        self.context = context or {}
        self.retryable = retryable
        self.http_status = http_status
        super().__init__(code)


def _meta_validation_message(exc: WildberriesBusinessError) -> tuple[str, bool]:
    raw_messages = [
        value.strip()
        for value in [exc.message, *(item.reason for item in exc.meta_validation)]
        if isinstance(value, str) and value.strip()
    ]
    dispatch_pending = any(_WB_DISPATCH_PENDING_MESSAGE in value.lower() for value in raw_messages)

    details: list[str] = []
    for item in exc.meta_validation:
        prefix = f"Заказ WB {item.order_id}: " if item.order_id is not None else ""
        # Причина может приехать и в reason, и в decision — переводим обе.
        # Слово `sgtinRetired` кладовщику не говорит ничего, а «код Честного
        # знака выведен из оборота» говорит, что делать.
        raw_reason = item.reason or item.decision
        translated = translate_wb_message(raw_reason) if raw_reason else None
        if translated:
            reason = translated
        elif item.reason:
            reason = f"Wildberries ответил: {item.reason}"
        else:
            reason = f"маркировка {item.key} — {item.decision}"
        rendered = f"{prefix}{reason}"
        if rendered not in details:
            details.append(rendered)
    # ⛔ Подробности по заказам показываем ВСЕГДА, если они есть.
    #
    # Раньше фраза WB «fix them to dispatch items» перехватывалась первой и
    # превращалась в «Wildberries ещё обрабатывает поставку, повторите через
    # минуту» — а всё, что WB сказал про конкретные заказы, выбрасывалось.
    # Английский оригинал читается как «исправьте их, чтобы отгрузить», то есть
    # WB просит починить данные заказов, а мы советовали подождать. Оператор жал
    # «Повторить» по кругу, и ничего не менялось, потому что само оно не
    # рассасывается.
    if details:
        head = (
            "Wildberries не принял поставку и просит исправить заказы: " if dispatch_pending else ""
        )
        # Повтор остаётся доступным сознательно. Оператор чинит названное —
        # перебивает код Честного знака на упаковке — и жмёт «Повторить» тут же,
        # не выходя из окна. Прятать кнопку значит заставлять его искать путь
        # заново; вреда от лишнего нажатия нет, ключ идемпотентности на отказе
        # и так меняется на новый. Вредило утром не наличие кнопки, а текст,
        # который обещал, что само рассосётся.
        return f"{head}{'; '.join(details)}", True

    # Подробностей по заказам нет. Показываем оператору собственные слова WB —
    # молчать и советовать «повторите через минуту» нельзя: 02.09.2026 склад так
    # шесть раз подряд нажал повтор и остановился, а причина осталась только в
    # голове у Wildberries.
    if dispatch_pending:
        own = next((value for value in raw_messages if value), "")
        translated = translate_wb_message(own) if own else None
        if translated:
            return translated, True
        if own:
            return (
                f"Wildberries не принял поставку и ответил: «{own}». "
                "Если повтор через минуту не помогает, причину надо смотреть "
                "в кабинете продавца.",
                True,
            )
        return (
            "Wildberries ещё обрабатывает поставку. Повторите передачу через минуту.",
            True,
        )

    if exc.message:
        translated = translate_wb_message(exc.message)
        return translated or f"Wildberries ответил: {exc.message}", False
    return "WB отклонил данные маркировки заказов.", False


@dataclass(frozen=True)
class DeliveryCheck:
    code: str
    message: str
    ok: bool
    # Уровень задаётся явно и намеренно не имеет значения по умолчанию: тот, кто
    # добавляет новую проверку, обязан решить, останавливает она склад или нет.
    severity: str
    order_id: uuid.UUID | None = None


@dataclass(frozen=True)
class DeliveryPreflightResult:
    can_deliver: bool
    version: str
    checked_at: datetime
    checks: tuple[DeliveryCheck, ...]


def _wb_error_code(exc: WildberriesClientError) -> str:
    suffix = f"_{exc.status_code}" if exc.status_code else ""
    return f"wb_{exc.code}{suffix}"


def _shipment_error_from_wb(
    exc: WildberriesClientError,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    local_entity_id: uuid.UUID | str | None,
    wb_supply_id: str | None,
    event: str,
    retryable: bool | None = None,
    http_status: int | None = None,
    extra_context: dict[str, Any] | None = None,
) -> FbsShipmentError:
    ref = wb_error_ref()
    log_wb_client_error(
        logger,
        event,
        exc,
        tenant_id=tenant_id,
        seller_id=seller_id,
        local_entity_id=local_entity_id,
        wb_object_id=wb_supply_id,
        ref=ref,
    )
    extra: dict[str, Any] = {}
    if wb_supply_id is not None:
        extra["wb_supply_id"] = wb_supply_id
    if local_entity_id is not None:
        extra["local_entity_id"] = str(local_entity_id)
    if extra_context:
        extra.update(extra_context)
    return FbsShipmentError(
        _wb_error_code(exc),
        message=wb_operator_message(exc),
        context=wb_error_context(exc, ref=ref, extra=extra),
        retryable=exc.code == "transport_error" if retryable is None else retryable,
        http_status=http_status or (504 if exc.code == "transport_error" else 502),
    )


async def _require_marketplace_token(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> str:
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsShipmentError("seller_not_found")
    token = await get_decrypted_marketplace_token(session, tenant_id, seller_id)
    if not token:
        raise FbsShipmentError("missing_marketplace_token")
    return token


def _barcode_relative_path(supply_id: uuid.UUID) -> str:
    return f"fbs-supply-barcodes/{supply_id}.png"


def _barcode_storage_root() -> Path:
    return (Path(settings.wms_data_dir) / "fbs-supply-barcodes").resolve()


def _resolve_barcode_path(rel: str) -> Path:
    root = _barcode_storage_root()
    target = (Path(settings.wms_data_dir) / rel).resolve()
    if root not in target.parents and target != root:
        raise FbsShipmentError("invalid_barcode_path")
    return target


def _save_barcode_png(supply_id: uuid.UUID, png_bytes: bytes) -> str:
    rel = _barcode_relative_path(supply_id)
    target = _resolve_barcode_path(rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(png_bytes)
    return rel


async def _get_supply_for_update(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    with_trbxes: bool = False,
) -> FbsSupply | None:
    stmt = (
        select(FbsSupply)
        .where(
            FbsSupply.id == supply_id,
            FbsSupply.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    if with_trbxes:
        stmt = stmt.options(selectinload(FbsSupply.trbxes))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _supply_orders_stmt(
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> Select[tuple[FbsOrder]]:
    return (
        select(FbsOrder)
        .where(
            FbsOrder.supply_id == supply_id,
            FbsOrder.tenant_id == tenant_id,
        )
        .options(
            selectinload(FbsOrder.product),
            selectinload(FbsOrder.product_positions),
            selectinload(FbsOrder.markings),
        )
    )


async def _load_locked_supply_orders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> list[FbsOrder]:
    result = await session.execute(_supply_orders_stmt(tenant_id, supply_id).with_for_update())
    return list(result.scalars().all())


async def _load_supply_orders_read(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> list[FbsOrder]:
    result = await session.execute(_supply_orders_stmt(tenant_id, supply_id))
    return list(result.scalars().all())


async def _get_supply_read(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    with_trbxes: bool = False,
) -> FbsSupply | None:
    stmt = select(FbsSupply).where(
        FbsSupply.id == supply_id,
        FbsSupply.tenant_id == tenant_id,
    )
    if with_trbxes:
        stmt = stmt.options(selectinload(FbsSupply.trbxes))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _order_has_sgtin_marking(order: FbsOrder) -> bool:
    return current_order_marking(list(order.markings), MARKING_KIND_SGTIN) is not None


async def _sync_supply_orders_from_wb(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
    http_client: httpx.AsyncClient,
    token: str,
    *,
    actor_user_id: uuid.UUID | None,
) -> list[FbsOrder]:
    orders = await _load_supply_orders_read(session, tenant_id, supply.id)
    if not orders:
        supply.last_wb_sync_at = datetime.now(UTC)
        await session.flush()
        return orders

    wb_ids = [int(order.wb_order_id) for order in orders]
    for batch in split_marketplace_order_id_batches(wb_ids):
        try:
            status_rows = await fetch_marketplace_orders_status(
                http_client,
                api_token=token,
                order_ids=batch,
            )
        except WildberriesClientError as exc:
            raise _shipment_error_from_wb(
                exc,
                tenant_id=tenant_id,
                seller_id=supply.seller_id,
                local_entity_id=supply.id,
                wb_supply_id=supply.wb_supply_id,
                event="fbs shipment WB supply status sync failed",
                extra_context={"wb_order_ids": batch},
            ) from exc
        by_id = {int(row["id"]): row for row in status_rows if row.get("id") is not None}
        for order in orders:
            row = by_id.get(int(order.wb_order_id))
            if row is None:
                continue
            wb_status = _wb_status_from_row(row)
            supplier_status = _supplier_status_from_row(row)
            if wb_status is not None or supplier_status is not None:
                await _apply_wb_status_to_order(
                    session,
                    order,
                    wb_status,
                    supplier_status=supplier_status,
                    actor_user_id=actor_user_id,
                )

    for order in orders:
        with suppress(marking_svc.FbsMarkingError):
            await marking_svc.sync_order_marking_statuses(
                session,
                tenant_id,
                order.id,
                http_client,
                actor_user_id=actor_user_id,
            )

    supply.last_wb_sync_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(supply)
    return await _load_supply_orders_read(session, tenant_id, supply.id)


def _compute_preflight_version(
    supply: FbsSupply,
    orders: list[FbsOrder],
    *,
    cargo_qr_ready: bool,
    has_physical_boxes: bool,
    without_distribution: bool,
    unassigned_packed_order_ids: frozenset[uuid.UUID],
    composition_fingerprint: str = "",
    source_plan: source_svc.FbsShipmentSourcePlan | None = None,
) -> str:
    supply_status = (
        "blocked"
        if (supply.marketplace in {"wb", "ozon"}
            and supply.status in _DELIVER_BLOCKED_SUPPLY_STATUSES)
        else "active"
        if supply.marketplace in {"wb", "ozon"}
        else supply.status
    )
    parts = [
        str(supply.id),
        supply_status,
        supply.delivery_type,
        composition_fingerprint,
    ]
    if supply.marketplace not in {"wb", "ozon"}:
        parts.extend(
            [
                str(cargo_qr_ready),
                str(has_physical_boxes),
                str(without_distribution),
                *(str(order_id) for order_id in sorted(unassigned_packed_order_ids)),
            ]
        )
    for order in sorted(orders, key=lambda item: item.id):
        if supply.marketplace in {"wb", "ozon"}:
            # Версия WB защищает фактический состав и план списания, но не
            # advisory-факты. Переходы in_supply/assembling/packed, печать,
            # маркировка, короба и QR не имеют права породить stale_preflight.
            order_parts = [
                str(order.id),
                "terminal" if order.status in _TERMINAL_ORDER_STATUSES else "active",
            ]
        else:
            order_parts = [
                str(order.id),
                order.status,
                order.wb_status or "",
                str(order.metadata_delivery_allowed),
            ]
        parts.extend(order_parts)
    if supply.marketplace in {"wb", "ozon"}:
        # ⛔ Версия защищает то, что оператор реально видел и с чем согласился:
        # состав заказов и сам факт «уйдём в минус». Точные числа, ячейки и
        # режим списания в неё НЕ входят.
        #
        # Раньше входили — и на складе, где работают несколько человек, версия
        # менялась от любого чужого движения по тому же товару: соседний подбор,
        # проведённая приёмка, перенос короба. Оператор открывал окно, читал
        # предупреждения, жал «Передать» и получал 409 «Чек-лист устарел».
        # Чинить это ему было нечем.
        #
        # Грубого признака недостачи достаточно: если минус появился там, где
        # его не было, версия изменится и система переспросит один раз. Если
        # минус был и просто стал глубже — оператор его уже видел и подтвердил.
        parts.append("shortage" if source_plan is not None and source_plan.has_shortage else "ok")
    else:
        for item in sorted(
            source_plan.resolutions if source_plan is not None else (),
            key=lambda row: (str(row.fbs_order_id), str(row.product_id)),
        ):
            parts.extend(
                [
                    str(item.fbs_order_id),
                    str(item.product_id),
                    str(item.quantity),
                    str(item.source_warehouse_id),
                    str(item.storage_location_id),
                    item.container_kind or "",
                    str(item.container_id or ""),
                    item.source_mode,
                    str(item.positive_quantity),
                    str(item.shortage_quantity),
                    str(item.negative_quantity),
                ]
            )
    if supply.marketplace == "ozon" and source_plan is not None:
        # Same warning policy as WB: unrelated picks/packing do not stale the
        # dialog, but changed actual order quantities/products do.
        quantities: dict[tuple[str, str], int] = {}
        for item in source_plan.resolutions:
            key = (str(item.fbs_order_id), str(item.product_id))
            quantities[key] = quantities.get(key, 0) + item.quantity
        for (order_id, product_id), quantity in sorted(quantities.items()):
            parts.extend([order_id, product_id, str(quantity)])
    raw = "|".join(parts).encode()
    return hashlib.sha256(raw).hexdigest()


def _build_delivery_checks(
    supply: FbsSupply,
    orders: list[FbsOrder],
    *,
    cargo_qr_ready: bool,
    boxes_required: bool = True,
    has_physical_boxes: bool = True,
    without_distribution: bool = False,
    unassigned_packed_order_ids: frozenset[uuid.UUID] = frozenset(),
    discrepancies: tuple[composition_svc.SupplyCompositionDiscrepancy, ...] = (),
    source_plan: source_svc.FbsShipmentSourcePlan | None = None,
) -> list[DeliveryCheck]:
    # «Сдать без Честного знака» снимает НАШЕ требование маркировки по поставке.
    # Требование самого Wildberries, записанное в required_meta_json заказа, этим
    # флагом не отменяется: такой заказ по-прежнему не уедет, и это правильно.
    honest_sign_skipped = supply.honest_sign_skipped_at is not None
    # Складской прогресс остаётся предупреждением для обеих площадок.
    # Требование Ozon собрать отправления проверяется отдельно по ответу /ship.
    soft = CHECK_WARNING
    checks: list[DeliveryCheck] = []

    if supply.status in _DELIVER_BLOCKED_SUPPLY_STATUSES:
        checks.append(
            DeliveryCheck(
                code="supply_bad_status",
                message="Поставка уже передана или закрыта.",
                ok=False,
                severity=CHECK_BLOCKER,
            )
        )

    if not orders:
        checks.append(
            DeliveryCheck(
                code="supply_empty",
                message="Поставка пуста — нет заказов.",
                ok=False,
                severity=CHECK_BLOCKER,
            )
        )

    for discrepancy in discrepancies:
        missing_from_wb = discrepancy.code == "local_order_not_in_wb"
        terminal_wb_order = supply.marketplace == "wb" and discrepancy.code in {
            "terminal_order",
            "terminal_local_order",
        }
        ignored = missing_from_wb or terminal_wb_order
        checks.append(
            DeliveryCheck(
                code=(
                    "local_order_not_in_wb_ignored"
                    if missing_from_wb
                    else (
                        "wb_terminal_order_ignored"
                        if terminal_wb_order
                        else "wb_supply_composition_discrepancy"
                    )
                ),
                message=(
                    f"Заказ WB {discrepancy.wb_order_id} отсутствует в фактическом составе "
                    "и не будет списан."
                    if missing_from_wb
                    else (
                        f"Заказ WB {discrepancy.wb_order_id} уже отменён или закрыт; "
                        "он исключён из списания и не блокирует передачу поставки."
                        if terminal_wb_order
                        else f"Заказ WB {discrepancy.wb_order_id}: {discrepancy.code}."
                    )
                ),
                # Keep a visible warning for a terminal WB order, but never make
                # the operator repair marketplace history before dispatching the
                # remaining active orders. Reconciliation already excludes this
                # order from source planning, write-off and local delivery state.
                ok=ignored and not terminal_wb_order,
                severity=(
                    CHECK_INFO
                    if (ignored and not terminal_wb_order)
                    else CHECK_WARNING
                    if terminal_wb_order
                    else CHECK_BLOCKER
                ),
                order_id=discrepancy.local_order_id,
            )
        )

    for order in orders:
        if order.status in _TERMINAL_ORDER_STATUSES:
            checks.append(
                DeliveryCheck(
                    code="order_terminal",
                    message="Заказ из фактического состава уже отменён или закрыт.",
                    ok=False,
                    severity=CHECK_BLOCKER,
                    order_id=order.id,
                )
            )

        if supply.marketplace == "wb":
            if (
                order.sticker_status not in _DELIVER_READY_STICKER_STATUSES
                or not order.sticker_file
            ):
                checks.append(
                    DeliveryCheck(
                        code="order_sticker_not_ready",
                        message="Стикер заказа WB ещё не подготовлен.",
                        ok=False,
                        severity=CHECK_WARNING,
                        order_id=order.id,
                    )
                )
            else:
                checks.append(
                    DeliveryCheck(
                        code="order_sticker_ready",
                        message="Стикер заказа WB готов.",
                        ok=True,
                        severity=CHECK_INFO,
                        order_id=order.id,
                    )
                )

        if supply.marketplace == "wb" and order.product_id is None:
            checks.append(
                DeliveryCheck(
                    code="order_product_not_mapped",
                    message=(
                        "Товар заказа не сопоставлен с карточкой в WMS — "
                        "со склада он списан не будет. Передаче не мешает."
                    ),
                    ok=False,
                    severity=CHECK_WARNING,
                    order_id=order.id,
                )
            )

        product = order.product
        if (
            product is not None
            and product.requires_honest_sign
            and not _order_has_sgtin_marking(order)
            and not honest_sign_skipped
        ):
            checks.append(
                DeliveryCheck(
                    code="marking_required",
                    message=(
                        "Честный знак не нанесён. Передаче не мешает, нанести можно и после неё."
                    ),
                    ok=False,
                    severity=soft,
                    order_id=order.id,
                )
            )
        elif not marking_svc.compute_delivery_allowed(order, list(order.markings)):
            checks.append(
                DeliveryCheck(
                    code="marking_not_allowed",
                    message=marking_svc.delivery_marking_message(order, list(order.markings)),
                    ok=False,
                    severity=soft,
                    order_id=order.id,
                )
            )
        elif order.required_meta_json:
            checks.append(
                DeliveryCheck(
                    code="marking_allowed",
                    message=marking_svc.delivery_marking_message(order, list(order.markings)),
                    ok=True,
                    severity=CHECK_INFO,
                    order_id=order.id,
                )
            )

    if supply.delivery_type == FBS_DELIVERY_TYPE_PVZ and has_physical_boxes:
        if not supply.trbxes:
            checks.append(
                DeliveryCheck(
                    code="box_qr_not_ready",
                    message=(
                        "QR коробов ПВЗ ещё не созданы. "
                        "Передаче не мешает, напечатать можно и после неё."
                    ),
                    ok=False,
                    severity=soft,
                )
            )
        elif not cargo_qr_ready:
            checks.append(
                DeliveryCheck(
                    code="cargo_place_qr_not_ready",
                    message=(
                        "QR грузомест не напечатаны. "
                        "Передаче не мешает, напечатать можно и после неё."
                    ),
                    ok=False,
                    severity=soft,
                )
            )
        else:
            checks.append(
                DeliveryCheck(
                    code="cargo_places_ready",
                    message="Грузоместа и QR готовы.",
                    ok=True,
                    severity=CHECK_INFO,
                )
            )

    if boxes_required and not has_physical_boxes:
        checks.append(
            DeliveryCheck(
                code="physical_boxes_required",
                message="В поставке пока нет коробов.",
                ok=False,
                severity=soft,
            )
        )
    if boxes_required and without_distribution and has_physical_boxes:
        checks.append(
            DeliveryCheck(
                code="boxes_without_distribution",
                message="Короба созданы без распределения товаров.",
                ok=True,
                severity=CHECK_INFO,
            )
        )
    else:
        for order_id in sorted(unassigned_packed_order_ids):
            checks.append(
                DeliveryCheck(
                    code="packed_order_unassigned",
                    message="Для заказа не указан короб.",
                    ok=False,
                    severity=soft,
                    order_id=order_id,
                )
            )

    if source_plan is not None:
        for resolution in source_plan.resolutions:
            if resolution.shortage_quantity:
                checks.append(
                    DeliveryCheck(
                        code="negative_stock",
                        message=(
                            f"Не хватает {resolution.shortage_quantity} шт.; после "
                            "подтверждения остаток будет списан в минус."
                        ),
                        ok=False,
                        severity=CHECK_WARNING,
                        order_id=resolution.fbs_order_id,
                    )
                )

    return _apply_wb_blocker_policy(checks, supply.marketplace)


def _apply_wb_blocker_policy(
    checks: list[DeliveryCheck], marketplace: str | None
) -> list[DeliveryCheck]:
    """Страховка от повторного появления внутренних блокировок WB.

    Даже если кто-то заведёт новую проверку и по привычке пометит её блокером,
    для Wildberries она станет предупреждением — кроме кодов из
    WB_ALLOWED_BLOCKER_CODES. Чтобы сделать проверку WB блокирующей, придётся
    осознанно дописать её в этот список, а список заморожен тестом.
    """
    if marketplace != "wb":
        return checks
    return [
        check
        if check.severity != CHECK_BLOCKER or check.code in WB_ALLOWED_BLOCKER_CODES
        else replace(check, severity=CHECK_WARNING)
        for check in checks
    ]


def _checks_to_payload(checks: list[DeliveryCheck]) -> list[dict[str, Any]]:
    return [
        {
            "code": check.code,
            "message": check.message,
            "ok": check.ok,
            "severity": check.severity,
            "order_id": str(check.order_id) if check.order_id is not None else None,
        }
        for check in checks
    ]


def _validate_checks_pass(checks: list[DeliveryCheck]) -> None:
    for check in checks:
        if check.severity == CHECK_BLOCKER:
            if check.code in {
                "wb_supply_composition_discrepancy",
                "order_terminal",
                "fbs_shipment_source_missing",
            }:
                raise FbsShipmentError(
                    check.code,
                    context={"order_id": str(check.order_id) if check.order_id else None},
                    http_status=409,
                )
            raise FbsShipmentError(check.code)


def _checks_allow_delivery(checks: list[DeliveryCheck]) -> bool:
    return not any(check.severity == CHECK_BLOCKER for check in checks)


async def _actual_wb_orders_and_source_plan(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
    http_client: httpx.AsyncClient,
    token: str,
    *,
    actor_user_id: uuid.UUID | None,
) -> tuple[
    list[FbsOrder],
    composition_svc.SupplyCompositionResult,
    source_svc.FbsShipmentSourcePlan,
]:
    try:
        composition = await composition_svc.reconcile_actual_wb_supply_composition(
            session,
            tenant_id,
            supply.id,
            http_client=http_client,
            api_token=token,
        )
    except WildberriesClientError as exc:
        raise _shipment_error_from_wb(
            exc,
            tenant_id=tenant_id,
            seller_id=supply.seller_id,
            local_entity_id=supply.id,
            wb_supply_id=supply.wb_supply_id,
            event="fbs shipment WB composition read failed",
            retryable=True,
            http_status=502,
        ) from exc
    except composition_svc.FbsSupplyCompositionError as exc:
        raise FbsShipmentError(exc.code, http_status=409) from exc
    await _sync_supply_orders_from_wb(
        session,
        tenant_id,
        supply,
        http_client,
        token,
        actor_user_id=actor_user_id,
    )
    orders = [
        order for order in composition.active_orders if order.status not in _TERMINAL_ORDER_STATUSES
    ]
    # ⛔ Раньше здесь падало 409 на первом же заказе без сопоставленного товара,
    # причём ДО того, как соберётся список проверок. То есть вся защита от
    # блокировок проходила мимо: один заказ с незнакомым артикулом — и поставка
    # не уезжала, а кнопка была мертва. Поймать это легко: продавец добавил в
    # поставку в своём кабинете товар, которого нет в нашем каталоге.
    #
    # Теперь такой заказ ведёт себя как отменённый: он исключается из списания
    # со склада, показывается предупреждением и передаче не мешает. Списать
    # товар, которого мы не знаем, всё равно невозможно, а держать из-за него
    # весь склад — нельзя.
    plan = await source_svc.plan_fbs_shipment_sources(
        session,
        tenant_id=tenant_id,
        supply_warehouse_id=supply.warehouse_id,
        requests=[
            source_svc.FbsShipmentSourceRequest(
                fbs_order_id=order.id,
                product_id=order.product_id,
                quantity=1,
            )
            for order in orders
            if order.product_id is not None
        ],
    )
    return orders, composition, plan


async def _sync_and_validate_deliver(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
    http_client: httpx.AsyncClient,
    token: str,
    *,
    confirmed_preflight_version: str | None = None,
    actor_user_id: uuid.UUID | None,
) -> tuple[list[FbsOrder], bool, source_svc.FbsShipmentSourcePlan]:
    orders, composition, source_plan = await _actual_wb_orders_and_source_plan(
        session, tenant_id, supply, http_client, token, actor_user_id=actor_user_id
    )
    cargo_qr_ready = True
    if supply.delivery_type == FBS_DELIVERY_TYPE_PVZ:
        cargo_qr_ready = await pvz_svc.supply_has_ready_cargo_place_qrs(session, tenant_id, supply)
    box_readiness = await packing_box_svc.get_delivery_box_readiness(
        session, tenant_id, supply.id, orders
    )
    if confirmed_preflight_version is not None:
        current_version = _compute_preflight_version(
            supply,
            orders,
            cargo_qr_ready=cargo_qr_ready,
            has_physical_boxes=box_readiness.has_physical_boxes,
            without_distribution=box_readiness.without_distribution,
            unassigned_packed_order_ids=box_readiness.unassigned_packed_order_ids,
            composition_fingerprint=composition.wb_order_fingerprint,
            source_plan=source_plan,
        )
        if current_version != confirmed_preflight_version:
            raise FbsShipmentError(
                "stale_preflight",
                message=_STALE_PREFLIGHT_MESSAGE,
                context={
                    "current_version": current_version,
                    "confirmed_preflight_version": confirmed_preflight_version,
                },
                http_status=409,
            )
    checks = _build_delivery_checks(
        supply,
        orders,
        cargo_qr_ready=cargo_qr_ready,
        has_physical_boxes=box_readiness.has_physical_boxes,
        without_distribution=box_readiness.without_distribution,
        unassigned_packed_order_ids=box_readiness.unassigned_packed_order_ids,
        discrepancies=composition.discrepancies,
        source_plan=source_plan,
    )
    _validate_checks_pass(checks)
    current_version = _compute_preflight_version(
        supply,
        orders,
        cargo_qr_ready=cargo_qr_ready,
        has_physical_boxes=box_readiness.has_physical_boxes,
        without_distribution=box_readiness.without_distribution,
        unassigned_packed_order_ids=box_readiness.unassigned_packed_order_ids,
        composition_fingerprint=composition.wb_order_fingerprint,
        source_plan=source_plan,
    )
    if source_plan.has_shortage and confirmed_preflight_version != current_version:
        raise FbsShipmentError(
            "negative_stock_confirmation_required",
            message=(
                "Проверки не подтверждены, а остатка не хватает. Закройте окно "
                "передачи и откройте заново — система покажет, какой заказ "
                "уйдёт в минус, и спросит подтверждение."
            ),
            context={"current_version": current_version},
            http_status=409,
        )
    return orders, cargo_qr_ready, source_plan


def _meta_validation_context(exc: WildberriesBusinessError) -> list[dict[str, Any]]:
    return [
        {
            "order_id": item.order_id,
            "key": item.key,
            "value": item.value,
            "decision": item.decision,
            "reason": item.reason,
        }
        for item in exc.meta_validation
    ]


async def preflight_delivery(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    *,
    actor_user_id: uuid.UUID | None,
) -> DeliveryPreflightResult:
    supply = await _get_supply_read(session, tenant_id, supply_id, with_trbxes=True)
    if supply is None:
        raise FbsShipmentError("supply_not_found")
    if supply.delivery_type not in _DELIVER_ALLOWED_DELIVERY_TYPES:
        raise FbsShipmentError("wrong_delivery_type")

    if supply.marketplace == "ozon":
        await _ozon_credentials(session, tenant_id, supply.seller_id)
        orders = await _load_supply_orders_read(session, tenant_id, supply.id)
        try:
            source_plan = await plan_ozon_shipment_sources(
                session, tenant_id=tenant_id, warehouse_id=supply.warehouse_id, orders=orders,
            )
        except OzonPackagingError as exc:
            raise FbsShipmentError(str(exc), http_status=409) from exc
        checks = _build_delivery_checks(
            supply,
            orders,
            cargo_qr_ready=True,
            boxes_required=False,
            source_plan=source_plan,
        )
        checked_at = datetime.now(UTC)
        version = _compute_preflight_version(
            supply,
            orders,
            cargo_qr_ready=True,
            has_physical_boxes=False,
            without_distribution=False,
            unassigned_packed_order_ids=frozenset(),
            source_plan=source_plan,
        )
        return DeliveryPreflightResult(
            can_deliver=_checks_allow_delivery(checks),
            version=version,
            checked_at=checked_at,
            checks=tuple(checks),
        )

    token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
    orders, composition, source_plan = await _actual_wb_orders_and_source_plan(
        session, tenant_id, supply, http_client, token, actor_user_id=actor_user_id
    )
    cargo_qr_ready = True
    if supply.delivery_type == FBS_DELIVERY_TYPE_PVZ:
        cargo_qr_ready = await pvz_svc.supply_has_ready_cargo_place_qrs(session, tenant_id, supply)
    box_readiness = await packing_box_svc.get_delivery_box_readiness(
        session, tenant_id, supply.id, orders
    )

    checks = _build_delivery_checks(
        supply,
        orders,
        cargo_qr_ready=cargo_qr_ready,
        has_physical_boxes=box_readiness.has_physical_boxes,
        without_distribution=box_readiness.without_distribution,
        unassigned_packed_order_ids=box_readiness.unassigned_packed_order_ids,
        discrepancies=composition.discrepancies,
        source_plan=source_plan,
    )
    checked_at = datetime.now(UTC)
    version = _compute_preflight_version(
        supply,
        orders,
        cargo_qr_ready=cargo_qr_ready,
        has_physical_boxes=box_readiness.has_physical_boxes,
        without_distribution=box_readiness.without_distribution,
        unassigned_packed_order_ids=box_readiness.unassigned_packed_order_ids,
        composition_fingerprint=composition.wb_order_fingerprint,
        source_plan=source_plan,
    )
    can_deliver = _checks_allow_delivery(checks)
    return DeliveryPreflightResult(
        can_deliver=can_deliver,
        version=version,
        checked_at=checked_at,
        checks=tuple(checks),
    )


def delivery_preflight_to_dict(result: DeliveryPreflightResult) -> dict[str, Any]:
    return {
        "can_deliver": result.can_deliver,
        "version": result.version,
        "checked_at": result.checked_at.isoformat(),
        "checks": _checks_to_payload(list(result.checks)),
    }


async def _apply_local_delivered(
    session: AsyncSession,
    supply: FbsSupply,
    orders: list[FbsOrder],
    actor_user_id: uuid.UUID | None,
    source_plan: source_svc.FbsShipmentSourcePlan | None,
    operation: Any,
) -> None:
    await _write_off_delivered_orders_once(
        session,
        supply,
        orders,
        actor_user_id,
        source_plan=source_plan,
        operation=operation,
    )
    now = datetime.now(UTC)
    supply.status = FBS_SUPPLY_STATUS_IN_DELIVERY
    supply.delivered_at = now
    for order in orders:
        if order.status not in _TERMINAL_ORDER_STATUSES:
            order.status = FBS_ORDER_STATUS_IN_DELIVERY
    await session.flush()


async def _write_off_delivered_orders_once(
    session: AsyncSession,
    supply: FbsSupply,
    orders: list[FbsOrder],
    actor_user_id: uuid.UUID | None,
    *,
    source_plan: source_svc.FbsShipmentSourcePlan | None,
    operation: Any,
) -> None:
    """Create exactly one physical write-off recipe per confirmed FBS order."""
    active_orders = [
        order
        for order in orders
        if order.status != FBS_ORDER_STATUS_CANCELLED
        and (order.product_id is not None or order.marketplace == "ozon")
    ]
    order_ids = [order.id for order in active_orders]
    existing_ledgers = {
        ledger.fbs_order_id: ledger
        for ledger in (
            (
                await session.execute(
                    select(FbsShipmentReversalLedger)
                    .where(
                        FbsShipmentReversalLedger.tenant_id == supply.tenant_id,
                        FbsShipmentReversalLedger.fbs_order_id.in_(order_ids),
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
    }
    resolutions = {
        item.fbs_order_id: item
        for item in (source_plan.resolutions if source_plan is not None else ())
    }

    for order in active_orders:
        ledger = existing_ledgers.get(order.id)
        if order.marketplace == "ozon" and (
            ledger is None or (ledger.shipment_movement_id is None and ledger.ozon_positions_json)
        ):
            try:
                ledger = await write_off_ozon_order(
                    session,
                    tenant_id=supply.tenant_id,
                    order=order,
                    actor_user_id=actor_user_id,
                    ledger=ledger,
                )
            except OzonPackagingError as exc:
                raise FbsShipmentError(str(exc), http_status=409) from exc
            existing_ledgers[order.id] = ledger
        if ledger is None:
            if order.product_id is None:
                # Сюда доходит только Ozon: заказы WB без сопоставленного товара
                # отсеяны фильтром active_orders выше — для них решение владельца
                # уже применено, они уезжают с предупреждением и без списания.
                #
                # У Ozon такого решения нет, и молча отпускать поставку без
                # списания нельзя: товар уедет физически, а в системе останется,
                # и найти это расхождение будет нечем — ledger не создаётся.
                raise FbsShipmentError("fbs_shipment_product_missing", http_status=409)
            resolution = resolutions.get(order.id)
            if resolution is None and order.marketplace == "ozon":
                sorting = await get_or_create_sorting_location(
                    session,
                    supply.tenant_id,
                    supply.warehouse_id,
                )
                ledger = FbsShipmentReversalLedger(
                    tenant_id=supply.tenant_id,
                    fbs_order_id=order.id,
                    product_id=order.product_id,
                    storage_location_id=sorting.id,
                    source_warehouse_id=supply.warehouse_id,
                    source_mode="legacy_sorting",
                    quantity=1,
                    wb_operation_id=operation.id,
                    written_off_by_user_id=actor_user_id,
                )
                session.add(ledger)
                await session.flush()
                existing_ledgers[order.id] = ledger
            elif resolution is None:
                raise FbsShipmentError("fbs_shipment_source_missing", http_status=409)
            else:
                ledger = FbsShipmentReversalLedger(
                    tenant_id=supply.tenant_id,
                    fbs_order_id=order.id,
                    product_id=order.product_id,
                    storage_location_id=resolution.storage_location_id,
                    source_warehouse_id=resolution.source_warehouse_id,
                    container_kind=resolution.container_kind,
                    container_id=resolution.container_id,
                    source_mode=resolution.source_mode,
                    quantity=1,
                    shortage_quantity=resolution.shortage_quantity,
                    negative_quantity=resolution.negative_quantity,
                    wb_operation_id=operation.id,
                    written_off_by_user_id=actor_user_id,
                )
                session.add(ledger)
                await session.flush()
                existing_ledgers[order.id] = ledger

        if ledger.reversed_at is not None:
            raise FbsShipmentError("fbs_shipment_already_reversed", http_status=409)
        resolution = resolutions.get(order.id)
        if ledger.shipment_movement_id is not None and ledger.source_mode is None:
            # A pre-migration ledger already points at the place actually written
            # off.  Do not decorate it with a newly recalculated container/source.
            ledger.source_mode = "legacy_ledger"
        if ledger.wb_operation_id is None:
            ledger.wb_operation_id = operation.id
        if ledger.written_off_by_user_id is None:
            ledger.written_off_by_user_id = actor_user_id
        if ledger.written_off_at is None and ledger.shipment_movement_id is not None:
            ledger.written_off_at = datetime.now(UTC)
        if ledger.shipment_movement_id is None:
            staged_source = (
                ledger.source_mode is not None and ledger.source_warehouse_id is not None
            )
            if not staged_source and resolution is None:
                raise FbsShipmentError("fbs_shipment_source_missing", http_status=409)
            if not staged_source:
                assert resolution is not None
                ledger.product_id = resolution.product_id
                ledger.storage_location_id = resolution.storage_location_id
                ledger.source_warehouse_id = resolution.source_warehouse_id
                ledger.container_kind = resolution.container_kind
                ledger.container_id = resolution.container_id
                ledger.source_mode = resolution.source_mode
                ledger.shortage_quantity = resolution.shortage_quantity
                ledger.negative_quantity = resolution.negative_quantity
            allow_negative = int(ledger.negative_quantity) > 0
            container_kind = cast(ContainerKind | None, ledger.container_kind)
            try:
                async with session.begin_nested():
                    movement = await inventory_svc.apply_fbs_supply_write_off(
                        session,
                        fbs_order_id=order.id,
                        tenant_id=supply.tenant_id,
                        product_id=ledger.product_id,
                        storage_location_id=ledger.storage_location_id,
                        quantity=int(ledger.quantity),
                        actor_user_id=actor_user_id,
                        allow_negative=allow_negative,
                        container_kind=container_kind,
                        container_id=ledger.container_id,
                    )
            except ValueError as exc:
                if allow_negative or str(exc) != "insufficient stock":
                    raise
                movement = await inventory_svc.apply_fbs_supply_write_off(
                    session,
                    fbs_order_id=order.id,
                    tenant_id=supply.tenant_id,
                    product_id=ledger.product_id,
                    storage_location_id=ledger.storage_location_id,
                    quantity=int(ledger.quantity),
                    actor_user_id=actor_user_id,
                    allow_negative=True,
                    container_kind=container_kind,
                    container_id=ledger.container_id,
                )
                ledger.shortage_quantity = int(ledger.quantity)
                ledger.negative_quantity = int(ledger.quantity)
            await session.flush()
            ledger.shipment_movement_id = movement.id
            ledger.wb_operation_id = operation.id
            ledger.written_off_by_user_id = actor_user_id
            ledger.written_off_at = datetime.now(UTC)
        await _release_reservation(session, order)
    await session.flush()


async def _stage_wb_shipment_sources(
    session: AsyncSession,
    supply: FbsSupply,
    orders: list[FbsOrder],
    source_plan: source_svc.FbsShipmentSourcePlan,
    operation: Any,
    actor_user_id: uuid.UUID | None,
) -> None:
    """Durably snapshot an attempt and prepare the physical write-off ledger."""
    resolutions = {item.fbs_order_id: item for item in source_plan.resolutions}
    active_orders = [
        order
        for order in orders
        if order.status not in _TERMINAL_ORDER_STATUSES and order.product_id is not None
    ]
    # ⛔ Раньше здесь стоял ранний выход: нет заказов со сопоставленным товаром —
    # чек-пойнт не пишем. А дальше передача этот чек-пойнт читает, не находит и
    # падает с «не удалось восстановить план списания». Поставка из одного
    # заказа с незнакомым артикулом — обычное дело, когда состав собрал сам
    # продавец, — упиралась в мёртвую кнопку навсегда.
    #
    # Пустой план списания — законное состояние: списывать нечего, но передать
    # надо. Пишем чек-пойнт с пустым списком и уходим.
    checkpoint_source_plan = {
        "supply_warehouse_id": str(source_plan.supply_warehouse_id),
        "resolutions": [
            {
                "fbs_order_id": str(item.fbs_order_id),
                "product_id": str(item.product_id),
                "quantity": item.quantity,
                "source_warehouse_id": str(item.source_warehouse_id),
                "storage_location_id": str(item.storage_location_id),
                "container_kind": item.container_kind,
                "container_id": str(item.container_id) if item.container_id else None,
                "source_mode": item.source_mode,
                "positive_quantity": item.positive_quantity,
                "shortage_quantity": item.shortage_quantity,
                "negative_quantity": item.negative_quantity,
            }
            for item in sorted(source_plan.resolutions, key=lambda row: str(row.fbs_order_id))
        ],
    }
    summary = dict(operation.request_summary_json or {})
    previous_checkpoint = summary.get("checkpoint_source_plan")
    if previous_checkpoint is not None and previous_checkpoint != checkpoint_source_plan:
        raise FbsShipmentError(
            "stale_preflight",
            message=_STALE_PREFLIGHT_MESSAGE,
            http_status=409,
        )
    summary["checkpoint_source_plan"] = checkpoint_source_plan
    operation.request_summary_json = summary
    existing = {
        ledger.fbs_order_id: ledger
        for ledger in (
            (
                await session.execute(
                    select(FbsShipmentReversalLedger)
                    .where(
                        FbsShipmentReversalLedger.tenant_id == supply.tenant_id,
                        FbsShipmentReversalLedger.fbs_order_id.in_(
                            [order.id for order in active_orders]
                        ),
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
    }
    for order in active_orders:
        resolution = resolutions.get(order.id)
        if resolution is None:
            raise FbsShipmentError("fbs_shipment_source_missing", http_status=409)
        ledger = existing.get(order.id)
        if ledger is None:
            ledger = FbsShipmentReversalLedger(
                tenant_id=supply.tenant_id,
                fbs_order_id=order.id,
                product_id=resolution.product_id,
                storage_location_id=resolution.storage_location_id,
                source_warehouse_id=resolution.source_warehouse_id,
                container_kind=resolution.container_kind,
                container_id=resolution.container_id,
                source_mode=resolution.source_mode,
                quantity=resolution.quantity,
                shortage_quantity=resolution.shortage_quantity,
                negative_quantity=resolution.negative_quantity,
                wb_operation_id=operation.id,
                written_off_by_user_id=actor_user_id,
            )
            session.add(ledger)
        elif ledger.shipment_movement_id is None:
            # The immutable audit checkpoint lives in operation.request_summary.
            # This single per-order ledger is the eventual physical write-off
            # row, so a new definitive attempt prepares it from its own frozen
            # snapshot without changing any prior operation's snapshot.
            ledger.product_id = resolution.product_id
            ledger.storage_location_id = resolution.storage_location_id
            ledger.source_warehouse_id = resolution.source_warehouse_id
            ledger.container_kind = resolution.container_kind
            ledger.container_id = resolution.container_id
            ledger.source_mode = resolution.source_mode
            ledger.quantity = resolution.quantity
            ledger.shortage_quantity = resolution.shortage_quantity
            ledger.negative_quantity = resolution.negative_quantity
            ledger.wb_operation_id = operation.id
        elif ledger.wb_operation_id is None:
            ledger.wb_operation_id = operation.id
        if ledger.written_off_by_user_id is None:
            ledger.written_off_by_user_id = actor_user_id
    await session.flush()


async def _load_checkpointed_wb_delivery(
    session: AsyncSession,
    supply: FbsSupply,
    operation: Any,
) -> tuple[list[FbsOrder], source_svc.FbsShipmentSourcePlan] | None:
    """Load the durable WB source plan after marketplace confirmation."""
    summary = operation.request_summary_json or {}
    checkpoint_source_plan = summary.get("checkpoint_source_plan")
    if isinstance(checkpoint_source_plan, dict):
        raw_resolutions = checkpoint_source_plan.get("resolutions")
        # Пустой список — это «списывать нечего», а не битый чек-пойнт. Так
        # выглядит поставка, в которой ни один заказ не сопоставлен с карточкой
        # товара: уехать она обязана, движений по складу не создаст.
        if not isinstance(raw_resolutions, list):
            raise FbsShipmentError("fbs_shipment_checkpoint_incomplete", http_status=409)
        orders = await _load_locked_supply_orders(session, supply.tenant_id, supply.id)
        orders_by_id = {order.id: order for order in orders}
        snapshot_orders: list[FbsOrder] = []
        snapshot_resolutions: list[source_svc.FbsShipmentSourceResolution] = []
        try:
            supply_warehouse_id = uuid.UUID(str(checkpoint_source_plan["supply_warehouse_id"]))
            for raw in raw_resolutions:
                if not isinstance(raw, dict):
                    raise ValueError("invalid checkpoint row")
                order_id = uuid.UUID(str(raw["fbs_order_id"]))
                # Заказ должен быть в поставке, но само его присутствие тут
                # больше не решает, какие заказы считать уехавшими: список «что
                # уехало» и список «что списываем» — разные вещи.
                orders_by_id[order_id]
                snapshot_resolutions.append(
                    source_svc.FbsShipmentSourceResolution(
                        fbs_order_id=order_id,
                        product_id=uuid.UUID(str(raw["product_id"])),
                        quantity=int(raw["quantity"]),
                        source_warehouse_id=uuid.UUID(str(raw["source_warehouse_id"])),
                        storage_location_id=uuid.UUID(str(raw["storage_location_id"])),
                        container_kind=cast(ContainerKind | None, raw.get("container_kind")),
                        container_id=(
                            uuid.UUID(str(raw["container_id"])) if raw.get("container_id") else None
                        ),
                        source_mode=cast(source_svc.FbsShipmentSourceMode, raw["source_mode"]),
                        positive_quantity=int(raw["positive_quantity"]),
                        shortage_quantity=int(raw["shortage_quantity"]),
                        negative_quantity=int(raw["negative_quantity"]),
                    )
                )
        except (KeyError, TypeError, ValueError):
            raise FbsShipmentError("fbs_shipment_checkpoint_incomplete", http_status=409) from None
        # Уехало всё, что лежало в поставке и не отменено, — включая заказы без
        # сопоставленного товара, по которым списывать нечего. Раньше сюда
        # попадали только строки плана списания, и несопоставленный заказ
        # оставался «упакован» внутри уже переданной поставки: оператор не мог
        # понять, уехал он или нет. Хуже того, при повторном подтверждении план
        # пересчитывался заново и тот же заказ статус получал — одно и то же
        # вело себя по-разному в зависимости от пути.
        snapshot_orders = [
            order for order in orders if order.status not in _TERMINAL_ORDER_STATUSES
        ]
        return snapshot_orders, source_svc.FbsShipmentSourcePlan(
            tenant_id=supply.tenant_id,
            supply_warehouse_id=supply_warehouse_id,
            resolutions=tuple(snapshot_resolutions),
        )

    # Backward compatibility for operations created before journal snapshots.
    ledgers = list(
        (
            await session.execute(
                select(FbsShipmentReversalLedger).where(
                    FbsShipmentReversalLedger.tenant_id == supply.tenant_id,
                    FbsShipmentReversalLedger.wb_operation_id == operation.id,
                )
            )
        )
        .scalars()
        .all()
    )
    if not ledgers:
        return None
    orders = await _load_locked_supply_orders(session, supply.tenant_id, supply.id)
    orders_by_id = {order.id: order for order in orders}
    checkpointed_orders: list[FbsOrder] = []
    resolutions: list[source_svc.FbsShipmentSourceResolution] = []
    for ledger in ledgers:
        ledger_order = orders_by_id.get(ledger.fbs_order_id)
        source_warehouse_id = ledger.source_warehouse_id
        source_mode = ledger.source_mode
        if ledger.shipment_movement_id is not None and source_warehouse_id is None:
            source_warehouse_id = await session.scalar(
                select(StorageLocation.warehouse_id).where(
                    StorageLocation.id == ledger.storage_location_id,
                    StorageLocation.tenant_id == supply.tenant_id,
                )
            )
            source_mode = source_mode or "legacy_ledger"
        if ledger_order is None or source_warehouse_id is None or source_mode is None:
            raise FbsShipmentError(
                "fbs_shipment_checkpoint_incomplete",
                context={"order_id": str(ledger.fbs_order_id)},
                http_status=409,
            )
        checkpointed_orders.append(ledger_order)
        quantity = int(ledger.quantity)
        shortage = int(ledger.shortage_quantity)
        resolutions.append(
            source_svc.FbsShipmentSourceResolution(
                fbs_order_id=ledger.fbs_order_id,
                product_id=ledger.product_id,
                quantity=quantity,
                source_warehouse_id=source_warehouse_id,
                storage_location_id=ledger.storage_location_id,
                container_kind=cast(ContainerKind | None, ledger.container_kind),
                container_id=ledger.container_id,
                source_mode=cast(source_svc.FbsShipmentSourceMode, source_mode),
                positive_quantity=max(0, quantity - shortage),
                shortage_quantity=shortage,
                negative_quantity=int(ledger.negative_quantity),
            )
        )
    return checkpointed_orders, source_svc.FbsShipmentSourcePlan(
        tenant_id=supply.tenant_id,
        supply_warehouse_id=supply.warehouse_id,
        resolutions=tuple(resolutions),
    )


async def _fetch_supply_qr_after_deliver(
    session: AsyncSession,
    supply: FbsSupply,
    http_client: httpx.AsyncClient,
    token: str,
) -> None:
    # WB issues a supply QR (GET /api/v3/supplies/{id}/barcode) regardless of
    # delivery_type — verified against the WB API for both warehouse_sc and pvz
    # supplies on 2026-08-17. Do not re-add a delivery_type gate here.
    if supply.barcode_file and supply.barcode_asset_id:
        return
    try:
        png_bytes = await fetch_marketplace_supply_barcode(
            http_client,
            api_token=token,
            supply_id=supply.wb_supply_id,
        )
    except WildberriesClientError as exc:
        raise _shipment_error_from_wb(
            exc,
            tenant_id=supply.tenant_id,
            seller_id=supply.seller_id,
            local_entity_id=supply.id,
            wb_supply_id=supply.wb_supply_id,
            event="fbs shipment WB supply QR fetch failed",
        ) from exc
    supply.barcode_file = _save_barcode_png(supply.id, png_bytes)
    try:
        await upsert_supply_qr_asset_from_bytes(
            session,
            tenant_id=supply.tenant_id,
            supply=supply,
            png_bytes=png_bytes,
        )
    except FbsPrintAssetStorageError as exc:
        raise FbsShipmentError(exc.code) from exc
    await session.flush()


async def _persist_confirmed_delivery(
    session: AsyncSession,
    supply: FbsSupply,
    orders: list[FbsOrder],
    operation: Any,
    actor_user_id: uuid.UUID | None,
    source_plan: source_svc.FbsShipmentSourcePlan | None = None,
) -> None:
    """Persist marketplace confirmation and the matching local stock result."""
    if source_plan is None:
        # Ozon still uses its packaging write-off ledger.  Keep the established
        # atomic order here: its idempotent retry path returns an already
        # confirmed operation and does not replay unfinished local stock work.
        await _apply_local_delivered(session, supply, orders, actor_user_id, source_plan, operation)
        await mark_deliver_operation_confirmed(
            session,
            operation,
            wb_supply_id=supply.wb_supply_id,
            local_supply_id=supply.id,
        )
        await session.commit()
        return

    # WB delivery cannot be rolled back.  Persist that fact first so any later
    # inventory/container failure is recoverable by retrying the same
    # idempotency key without ever sending a second deliver mutation to WB.
    await _stage_wb_shipment_sources(
        session,
        supply,
        orders,
        source_plan,
        operation,
        actor_user_id,
    )
    await mark_deliver_operation_confirmed(
        session,
        operation,
        wb_supply_id=supply.wb_supply_id,
        local_supply_id=supply.id,
    )
    await session.commit()
    await _apply_local_delivered(session, supply, orders, actor_user_id, source_plan, operation)
    # The optional QR fetch happens after this second checkpoint as well.
    await session.commit()


async def _ozon_credentials(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> tuple[str, str]:
    try:
        return await MarketplaceAccountService(session).stored_credentials(
            tenant_id,
            seller_id,
        )
    except MarketplaceAccountError as exc:
        raise FbsShipmentError(
            exc.code,
            message="Кабинет Ozon не подключён.",
            http_status=409,
        ) from exc


async def _store_ozon_supply_qr(
    session: AsyncSession,
    supply: FbsSupply,
    provider: OzonMarketplaceProvider,
    *,
    client_id: str,
    api_key: str,
) -> bytes:
    external_supply_id = supply.external_supply_id or supply.wb_supply_id
    try:
        png_bytes = await provider.fetch_supply_qr(
            client_id=client_id,
            api_key=api_key,
            supply_id=external_supply_id,
        )
    except MarketplaceProviderError as exc:
        raise FbsShipmentError(
            exc.code,
            message=provider_error_message(exc),
            retryable=exc.status_code in {429, 500, 502, 503, 504},
            http_status=exc.status_code or 502,
        ) from exc
    if not png_bytes:
        raise FbsShipmentError(
            "ozon_supply_qr_missing",
            message="Ozon не вернул QR поставки.",
            http_status=502,
        )
    try:
        await upsert_supply_qr_asset_from_bytes(
            session,
            tenant_id=supply.tenant_id,
            supply=supply,
            png_bytes=png_bytes,
        )
    except FbsPrintAssetStorageError as exc:
        raise FbsShipmentError(exc.code) from exc
    await session.flush()
    return png_bytes


# Ключ снимка передачи Ozon в журнале операции. Рядом лежит вайлдберрисовский
# `checkpoint_source_plan` — они не пересекаются: у каждого маркетплейса своя
# точка сохранения и свой смысл «что уже необратимо сделано».
OZON_HANDOFF_PROGRESS_KEY = "ozon_handoff_progress"


async def _save_ozon_handoff_progress(
    session: AsyncSession,
    operation: Any,
    progress: OzonHandoffProgress,
) -> None:
    """Сделать снимок передачи Ozon долговечным.

    Коммит здесь обязателен и он же — весь смысл функции. Без него снимок
    живёт только внутри открытой транзакции, а она при ошибке откатывается
    целиком: то есть ровно в тот момент, ради которого снимок и заводился, он
    исчезает.
    """
    summary = dict(operation.request_summary_json or {})
    summary[OZON_HANDOFF_PROGRESS_KEY] = progress.to_json()
    operation.request_summary_json = summary
    await session.commit()


async def _fail_ozon_deliver_operation(
    session: AsyncSession,
    operation: Any,
    *,
    error_code: str,
    supply_id: uuid.UUID,
    discard_local_changes: bool = False,
) -> None:
    """Записать отказ передачи Ozon так, чтобы он пережил откат запроса.

    Раньше отказ помечался только `flush`, а коммита для озоновских кодов не
    делал никто: запись операции пропадала вместе с транзакцией, и следующая
    попытка не знала ни что уже уехало в кабинет, ни что предыдущая падала.

    `discard_local_changes` нужен там, где в сессии висит наполовину сделанная
    локальная работа — списание, движения по складу, печатные активы. Такое
    закоммитить вместе с отметкой об отказе нельзя: получится поставка,
    списанная наполовину. Состояния самой передачи это не теряет — все её шаги
    уже закоммичены снимками.
    """
    if discard_local_changes:
        with suppress(SQLAlchemyError):
            await session.rollback()
        refreshed = await session.get(FbsWbOperation, operation.id)
        if refreshed is None:
            return
        operation = refreshed
    try:
        await mark_operation_failed(
            session,
            operation,
            error_code=error_code,
            local_supply_id=supply_id,
        )
        await session.commit()
        return
    except SQLAlchemyError:
        logger.exception(
            "ozon deliver failure could not be journalled in place",
            extra={"supply_id": str(supply_id), "error_code": error_code},
        )
    # Транзакция могла умереть вместе с исходной ошибкой. Тогда единственный
    # способ сохранить отказ — начать чистую и перечитать саму операцию.
    try:
        await session.rollback()
        fresh = await session.get(FbsWbOperation, operation.id)
        if fresh is None:
            return
        await mark_operation_failed(
            session,
            fresh,
            error_code=error_code,
            local_supply_id=supply_id,
        )
        await session.commit()
    except SQLAlchemyError:
        logger.exception(
            "ozon deliver failure could not be journalled at all",
            extra={"supply_id": str(supply_id), "error_code": error_code},
        )


async def _deliver_ozon_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    idempotency_key: str,
    request_hash: str,
    confirmed_preflight_version: str | None,
    existing: Any,
    provider: OzonMarketplaceProvider | None,
    actor_user_id: uuid.UUID | None,
) -> FbsSupply:
    supply = await _get_supply_read(session, tenant_id, supply_id)
    if supply is None:
        raise FbsShipmentError("supply_not_found")
    # Keep the advisory lock on its own connection: checkpoints commit the
    # business session and release its transaction/connection. A dead worker
    # releases this lock automatically, so persisted PENDING is resumable.
    async with (
        AsyncSession(bind=session.bind) as lock_session,
        marketplace_seller_lock(lock_session, supply.seller_id, "ozon-delivery") as acquired,
    ):
        if not acquired:
            raise FbsShipmentError(
                "operation_in_progress",
                message="Передача в Ozon уже выполняется.",
                retryable=True,
                http_status=503,
            )
        if existing is not None:
            await session.refresh(existing)
        await session.refresh(supply)
        return await _deliver_ozon_supply_locked(
            session, tenant_id, supply_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            confirmed_preflight_version=confirmed_preflight_version,
            existing=existing,
            provider=provider,
            actor_user_id=actor_user_id,
        )


async def _deliver_ozon_supply_locked(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    idempotency_key: str,
    request_hash: str,
    confirmed_preflight_version: str | None,
    existing: Any,
    provider: OzonMarketplaceProvider | None,
    actor_user_id: uuid.UUID | None,
) -> FbsSupply:
    supply = await _get_supply_for_update(
        session,
        tenant_id,
        supply_id,
        with_trbxes=True,
    )
    if supply is None:
        raise FbsShipmentError("supply_not_found")
    if supply.delivery_type not in _DELIVER_ALLOWED_DELIVERY_TYPES:
        raise FbsShipmentError("wrong_delivery_type")

    client_id, api_key = await _ozon_credentials(
        session,
        tenant_id,
        supply.seller_id,
    )
    if existing is not None:
        if existing.request_hash and existing.request_hash != request_hash:
            raise FbsShipmentError("idempotency_key_reused", http_status=409)
        if existing.state == WB_OPERATION_STATE_CONFIRMED:
            return supply

    if supply.status in _DELIVER_BLOCKED_SUPPLY_STATUSES:
        raise FbsShipmentError("supply_bad_status", http_status=409)
    orders = await _load_locked_supply_orders(session, tenant_id, supply.id)
    _validate_checks_pass(
        _build_delivery_checks(
            supply,
            orders,
            cargo_qr_ready=True,
            boxes_required=False,
        )
    )
    # Снимок собираем по всем попыткам этой поставки, а не по ключу
    # идемпотентности: браузер после отказа обычно присылает новый ключ, и
    # привязка только к нему потеряла бы всё, что уже сделано в кабинете.
    progress = OzonHandoffProgress()
    for attempt in await list_deliver_operations_for_supply(
        session,
        tenant_id=tenant_id,
        seller_id=supply.seller_id,
        local_supply_id=supply.id,
    ):
        if existing is None or attempt.id != existing.id:
            if attempt.state == WB_OPERATION_STATE_CONFIRMED:
                return supply
            if attempt.state in {
                WB_OPERATION_STATE_PENDING,
                WB_OPERATION_STATE_PENDING_CONFIRMATION,
            }:
                # No live owner holds the advisory lock. Reuse the original
                # operation even when the browser supplied a fresh retry key.
                if attempt.request_hash and attempt.request_hash != request_hash:
                    raise FbsShipmentError("idempotency_key_reused", http_status=409)
                existing = attempt
        progress.absorb(
            OzonHandoffProgress.from_json(
                (attempt.request_summary_json or {}).get(OZON_HANDOFF_PROGRESS_KEY)
            )
        )
    try:
        source_plan = await plan_ozon_shipment_sources(
            session, tenant_id=tenant_id, warehouse_id=supply.warehouse_id, orders=orders,
        )
        # A confirmed/ambiguous external handoff must finish local recovery;
        # do not ask a new approval after the irreversible operation.
        if not (progress.carriage_create_started or progress.carriage_id is not None
                or progress.used_fallback):
            current_version = _compute_preflight_version(
                supply, orders, cargo_qr_ready=True, has_physical_boxes=False,
                without_distribution=False, unassigned_packed_order_ids=frozenset(),
                source_plan=source_plan,
            )
            if (confirmed_preflight_version is not None
                    and confirmed_preflight_version != current_version):
                raise FbsShipmentError(
                    "stale_preflight", message=_STALE_PREFLIGHT_MESSAGE,
                    context={"current_version": current_version,
                             "confirmed_preflight_version": confirmed_preflight_version},
                    http_status=409,
                )
            if source_plan.has_shortage and confirmed_preflight_version != current_version:
                raise FbsShipmentError(
                    "negative_stock_confirmation_required",
                    message="Остатка не хватает. Откройте окно передачи, проверьте "
                            "предупреждение о минусе и подтвердите передачу.",
                    context={"current_version": current_version}, http_status=409,
                )
        await prepare_ozon_shipment_sources(
            session, tenant_id=tenant_id, warehouse_id=supply.warehouse_id, orders=orders,
            source_plan=source_plan,
        )
    except OzonPackagingError as exc:
        raise FbsShipmentError(str(exc), http_status=409) from exc
    if existing is not None:
        operation = existing
        operation.state = WB_OPERATION_STATE_PENDING
        operation.error_code = None
        operation.error_context_json = None
        operation.failed_at = None
    else:
        operation = await create_pending_deliver_operation(
            session,
            tenant_id=tenant_id,
            seller_id=supply.seller_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            local_supply_id=supply.id,
            confirmed_preflight_version=confirmed_preflight_version,
        )
    # Провайдер приходит из теста или из боевой настройки. Пока живой транспорт
    # выключен, локальная операция сохраняется, а передача честно не выполняется:
    # придумывать успех, которого не было, нельзя — товар физически не уехал.
    if provider is None and ozon_live_api_enabled():
        provider = build_ozon_provider()
    if provider is None:
        await _fail_ozon_deliver_operation(
            session,
            operation,
            error_code="ozon_live_handoff_blocked",
            supply_id=supply.id,
        )
        raise FbsShipmentError(
            "ozon_live_handoff_blocked",
            message=(
                "Передача в Ozon выключена настройкой: боевой транспорт Ozon не включён. "
                "Локальная складская операция сохранена."
            ),
            http_status=503,
        )

    async def _checkpoint(state: OzonHandoffProgress) -> None:
        await _save_ozon_handoff_progress(session, operation, state)

    # Первая долговечная точка — до любой мутации в кабинете. Без неё падение
    # процесса стёрло бы саму запись о том, что передача начиналась.
    await _checkpoint(progress)
    try:
        result = await handoff_supply(
            session,
            supply=supply,
            orders=orders,
            provider=provider,
            client_id=client_id,
            api_key=api_key,
            progress=progress,
            checkpoint=_checkpoint,
        )
    except OzonFbsProcessError as exc:
        await _fail_ozon_deliver_operation(
            session,
            operation,
            error_code=exc.code,
            supply_id=supply.id,
        )
        raise FbsShipmentError(
            exc.code,
            message=exc.message,
            retryable=False,
            http_status=exc.status_code or 502,
        ) from exc
    except MarketplaceProviderError as exc:
        await _fail_ozon_deliver_operation(
            session,
            operation,
            error_code=exc.code,
            supply_id=supply.id,
        )
        raise FbsShipmentError(
            exc.code,
            message=provider_error_message(exc),
            retryable=exc.status_code in {429, 500, 502, 503, 504},
            http_status=exc.status_code or 502,
        ) from exc

    try:
        return await _finish_ozon_delivery(
            session,
            supply=supply,
            orders=orders,
            operation=operation,
            result=result,
            actor_user_id=actor_user_id,
        )
    except Exception as exc:
        # Передача в кабинете уже состоялась, а локальная часть сорвалась.
        # Отметить отказ обязательно: иначе операция навсегда остаётся
        # «выполняется» и повтор упирается в 503, хотя продолжить можно.
        await _fail_ozon_deliver_operation(
            session,
            operation,
            error_code=getattr(exc, "code", None) or "ozon_local_delivery_failed",
            supply_id=supply.id,
            discard_local_changes=True,
        )
        raise


async def _finish_ozon_delivery(
    session: AsyncSession,
    *,
    supply: FbsSupply,
    orders: list[FbsOrder],
    operation: Any,
    result: OzonHandoffResult,
    actor_user_id: uuid.UUID | None,
) -> FbsSupply:
    """Локальная часть уже состоявшейся передачи Ozon."""
    supply.external_supply_id = str(result.carriage_id) if result.carriage_id is not None else None
    supply.document_number = str(result.carriage_id) if result.carriage_id is not None else None
    supply.display_number = result.barcode_text
    if result.shipping_list_bytes:
        # Лист отгрузки Ozon приходит в PDF, а хранилище печатных активов
        # принимает только PNG, поэтому показать его оператору сегодня негде.
        # Молча выбрасывать документ, за которым ехали в Ozon, нельзя —
        # пусть его получение хотя бы видно в журнале.
        logger.info(
            "ozon shipping list received but not stored: no PDF surface yet",
            extra={
                "supply_id": str(supply.id),
                "carriage_id": result.carriage_id,
                "bytes": len(result.shipping_list_bytes),
            },
        )
    if result.barcode_bytes:
        try:
            await upsert_supply_qr_asset_from_bytes(
                session,
                tenant_id=supply.tenant_id,
                supply=supply,
                png_bytes=result.barcode_bytes,
            )
        except FbsPrintAssetStorageError as exc:
            raise FbsShipmentError(exc.code) from exc
    await _persist_confirmed_delivery(session, supply, orders, operation, actor_user_id)
    return supply


async def deliver_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    *,
    idempotency_key: str,
    actor_user_id: uuid.UUID | None,
    confirmed_preflight_version: str | None = None,
    ozon_provider: OzonMarketplaceProvider | None = None,
) -> FbsSupply:
    if not idempotency_key.strip():
        raise FbsShipmentError("missing_idempotency_key")

    supply_read = await _get_supply_read(session, tenant_id, supply_id, with_trbxes=True)
    if supply_read is None:
        raise FbsShipmentError("supply_not_found")

    request_hash = request_hash_for_deliver(
        supply_id=supply_id,
        confirmed_preflight_version=confirmed_preflight_version,
    )
    existing_by_key = await get_deliver_operation_by_idempotency(
        session, supply_read.seller_id, idempotency_key
    )
    if (
        existing_by_key is not None
        and existing_by_key.local_entity_type == "fbs_supply"
        and existing_by_key.local_entity_id is not None
        and existing_by_key.local_entity_id != supply_id
    ):
        raise FbsShipmentError("idempotency_key_reused", http_status=409)
    existing = existing_by_key
    if supply_read.marketplace == "ozon":
        return await _deliver_ozon_supply(
            session,
            tenant_id,
            supply_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            confirmed_preflight_version=confirmed_preflight_version,
            existing=existing,
            provider=ozon_provider,
            actor_user_id=actor_user_id,
        )
    if existing_by_key is not None and existing_by_key.state == WB_OPERATION_STATE_FAILED:
        # A closed client key has no authority over a newer supply-scoped
        # attempt. Reject it before resolving the active operation, otherwise
        # a stale tab could fail or reconcile another key's durable journal.
        raise FbsShipmentError("idempotency_key_reused", http_status=409)
    resumable_operation: Any | None = None
    if existing is None or existing.state == WB_OPERATION_STATE_FAILED:
        active_for_supply = await get_active_deliver_operation_for_supply(
            session,
            tenant_id=tenant_id,
            seller_id=supply_read.seller_id,
            local_supply_id=supply_id,
        )
        if active_for_supply is not None:
            existing = active_for_supply
    if existing is not None:
        if (
            existing_by_key is not None
            and existing.id == existing_by_key.id
            and existing.request_hash
            and existing.request_hash != request_hash
        ):
            raise FbsShipmentError("idempotency_key_reused", http_status=409)
        if (
            existing_by_key is not None
            and existing.id == existing_by_key.id
            and existing.state == WB_OPERATION_STATE_FAILED
        ):
            raise FbsShipmentError("idempotency_key_reused", http_status=409)
        if existing.state == WB_OPERATION_STATE_CONFIRMED:
            confirmed_supply = await _get_supply_for_update(
                session, tenant_id, supply_id, with_trbxes=True
            )
            if confirmed_supply is not None:
                token = await _require_marketplace_token(
                    session, tenant_id, confirmed_supply.seller_id
                )
                checkpointed = await _load_checkpointed_wb_delivery(
                    session, confirmed_supply, existing
                )
                if checkpointed is None:
                    orders, _, source_plan = await _actual_wb_orders_and_source_plan(
                        session,
                        tenant_id,
                        confirmed_supply,
                        http_client,
                        token,
                        actor_user_id=actor_user_id,
                    )
                else:
                    orders, source_plan = checkpointed
                await _persist_confirmed_delivery(
                    session,
                    confirmed_supply,
                    orders,
                    existing,
                    actor_user_id,
                    source_plan,
                )
                # A prior QR failure is recoverable through the same idempotent
                # request and must never trigger another WB deliver mutation.
                await _fetch_supply_qr_after_deliver(session, confirmed_supply, http_client, token)
                return confirmed_supply
        if existing.state in {
            WB_OPERATION_STATE_PENDING,
            WB_OPERATION_STATE_PENDING_CONFIRMATION,
        }:
            observed_operation_state = existing.state
            token = await _require_marketplace_token(session, tenant_id, supply_read.seller_id)
            reconcile_state = await reconcile_supply_delivered(
                http_client,
                api_token=token,
                wb_supply_id=supply_read.wb_supply_id,
            )
            supply = await _get_supply_for_update(session, tenant_id, supply_id, with_trbxes=True)
            if supply is None:
                raise FbsShipmentError("supply_not_found")
            # Reconcile happened before the supply lock.  Another request may
            # have completed the same durable operation while this request was
            # waiting.  Refresh under the lock so an old observation can never
            # overwrite a definitive FAILED/CONFIRMED state.
            await session.refresh(existing)
            if existing.state == WB_OPERATION_STATE_FAILED:
                failed_code = existing.error_code or "wb_delivery_failed"
                await session.rollback()
                raise FbsShipmentError(
                    failed_code,
                    message=(
                        "Параллельная попытка уже получила окончательный ответ WB. "
                        "Повторите передачу отдельной попыткой."
                    ),
                    context={"operation_state": "failed"},
                    retryable=False,
                    http_status=409,
                )
            if existing.state == WB_OPERATION_STATE_CONFIRMED:
                reconcile_state = WB_OPERATION_STATE_CONFIRMED
            if (
                existing.state == WB_OPERATION_STATE_PENDING_CONFIRMATION
                and observed_operation_state != WB_OPERATION_STATE_PENDING_CONFIRMATION
                and reconcile_state != WB_OPERATION_STATE_CONFIRMED
            ):
                # The readback was made before another request recorded an
                # ambiguous WB mutation.  Its earlier done=false observation
                # is stale and cannot authorize a second external call.
                await session.rollback()
                raise FbsShipmentError(
                    "wb_pending_confirmation",
                    message="WB пока не подтвердил передачу; слепой повтор запрещён.",
                    context={"operation_state": "pending_confirmation"},
                    retryable=True,
                    http_status=504,
                )
            if reconcile_state == WB_OPERATION_STATE_CONFIRMED:
                checkpointed = await _load_checkpointed_wb_delivery(session, supply, existing)
                if checkpointed is None:
                    orders, _, source_plan = await _actual_wb_orders_and_source_plan(
                        session,
                        tenant_id,
                        supply,
                        http_client,
                        token,
                        actor_user_id=actor_user_id,
                    )
                else:
                    orders, source_plan = checkpointed
                await _persist_confirmed_delivery(
                    session, supply, orders, existing, actor_user_id, source_plan
                )
                await _fetch_supply_qr_after_deliver(session, supply, http_client, token)
                return supply

            if reconcile_state == WB_RECONCILE_NOT_DELIVERED:
                if existing.idempotency_key == idempotency_key:
                    # WB definitively reports `done=false`; the same durable
                    # attempt can safely continue from its frozen checkpoint.
                    resumable_operation = existing
                else:
                    # A different client key means an explicit new attempt.
                    # Close the old prepared attempt, then let the new key take
                    # its own current preflight/source snapshot.
                    await mark_operation_failed(
                        session,
                        existing,
                        error_code="wb_not_delivered",
                        wb_supply_id=supply_read.wb_supply_id,
                        local_supply_id=supply_id,
                    )
                    await session.commit()
                    if (
                        existing_by_key is not None
                        and existing_by_key.state == WB_OPERATION_STATE_FAILED
                    ):
                        raise FbsShipmentError("idempotency_key_reused", http_status=409)
                    return await deliver_supply(
                        session,
                        tenant_id,
                        supply_id,
                        http_client,
                        idempotency_key=idempotency_key,
                        actor_user_id=actor_user_id,
                        confirmed_preflight_version=confirmed_preflight_version,
                        ozon_provider=ozon_provider,
                    )
            else:
                await mark_operation_pending_confirmation(
                    session,
                    existing,
                    wb_supply_id=supply_read.wb_supply_id,
                    local_supply_id=supply_id,
                    error_code="wb_pending_confirmation",
                )
                await session.commit()
                raise FbsShipmentError(
                    "wb_pending_confirmation",
                    message="WB пока не подтвердил передачу; слепой повтор запрещён.",
                    context={"operation_state": "pending_confirmation"},
                    retryable=True,
                    http_status=504,
                )

    supply = await _get_supply_for_update(
        session,
        tenant_id,
        supply_id,
        with_trbxes=True,
    )
    if supply is None:
        raise FbsShipmentError("supply_not_found")

    # Two tabs can arrive with different client keys before either one creates
    # its journal row.  The supply row serializes that race; re-check under the
    # lock and hand recovery to the already durable operation instead of ever
    # issuing a second WB deliver mutation.
    raced_operation = await get_active_deliver_operation_for_supply(
        session,
        tenant_id=tenant_id,
        seller_id=supply.seller_id,
        local_supply_id=supply.id,
    )
    if raced_operation is not None and (existing is None or raced_operation.id != existing.id):
        await session.rollback()
        return await deliver_supply(
            session,
            tenant_id,
            supply_id,
            http_client,
            idempotency_key=idempotency_key,
            actor_user_id=actor_user_id,
            confirmed_preflight_version=confirmed_preflight_version,
            ozon_provider=ozon_provider,
        )
    if supply.delivery_type not in _DELIVER_ALLOWED_DELIVERY_TYPES:
        raise FbsShipmentError("wrong_delivery_type")
    if supply.status in _DELIVER_BLOCKED_SUPPLY_STATUSES:
        raise FbsShipmentError("supply_bad_status", http_status=409)

    operation = resumable_operation
    if operation is None:
        token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
        orders, _, source_plan = await _sync_and_validate_deliver(
            session,
            tenant_id,
            supply,
            http_client,
            token,
            confirmed_preflight_version=confirmed_preflight_version,
            actor_user_id=actor_user_id,
        )
        operation = await create_pending_deliver_operation(
            session,
            tenant_id=tenant_id,
            seller_id=supply.seller_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            local_supply_id=supply.id,
            confirmed_preflight_version=confirmed_preflight_version,
            created_by_user_id=actor_user_id,
        )
    else:
        token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
        checkpointed = await _load_checkpointed_wb_delivery(session, supply, operation)
        if checkpointed is None:
            raise FbsShipmentError("fbs_shipment_checkpoint_incomplete", http_status=409)
        orders, source_plan = checkpointed

    # Сначала сохраняем операцию и точный план источников, затем выполняем
    # необратимый запрос WB. Если процесс умрёт после WB 2xx, повтор найдёт
    # pending-операцию, сверится с WB и закончит локальное списание без второго
    # вызова deliver.
    await _stage_wb_shipment_sources(
        session,
        supply,
        orders,
        source_plan,
        operation,
        actor_user_id,
    )
    await session.commit()

    # Commit выше делает checkpoint долговечным, но снимает row lock. Сразу
    # берём поставку под блокировку снова и держим её до результата WB, чтобы
    # параллельная вкладка не выполнила вторую внешнюю передачу.
    locked_supply = await _get_supply_for_update(
        session,
        tenant_id,
        supply_id,
        with_trbxes=True,
    )
    if locked_supply is None:
        raise FbsShipmentError("supply_not_found")
    supply = locked_supply
    # Another request may have completed this operation between our durable
    # checkpoint commit and reacquiring the supply lock.  The supply lock
    # serializes the external mutation; refresh the journal under that lock so
    # a stale in-memory PENDING object can never issue or overwrite a second
    # WB call.
    await session.refresh(operation)
    if operation.state == WB_OPERATION_STATE_CONFIRMED:
        checkpointed = await _load_checkpointed_wb_delivery(session, supply, operation)
        if checkpointed is None:
            raise FbsShipmentError("fbs_shipment_checkpoint_incomplete", http_status=409)
        orders, source_plan = checkpointed
        await _persist_confirmed_delivery(
            session, supply, orders, operation, actor_user_id, source_plan
        )
        await _fetch_supply_qr_after_deliver(session, supply, http_client, token)
        return supply
    if operation.state == WB_OPERATION_STATE_FAILED:
        failed_code = operation.error_code or "wb_delivery_failed"
        await session.rollback()
        raise FbsShipmentError(
            failed_code,
            message="Параллельная попытка уже получила окончательный отказ WB.",
            context={"operation_state": "failed"},
            retryable=False,
            http_status=409,
        )
    if operation.state == WB_OPERATION_STATE_PENDING_CONFIRMATION:
        await session.rollback()
        raise FbsShipmentError(
            "wb_pending_confirmation",
            message="WB пока не подтвердил передачу; слепой повтор запрещён.",
            context={"operation_state": "pending_confirmation"},
            retryable=True,
            http_status=504,
        )
    if supply.status in _DELIVER_BLOCKED_SUPPLY_STATUSES:
        await mark_operation_failed(
            session,
            operation,
            error_code="supply_bad_status",
            wb_supply_id=supply.wb_supply_id,
            local_supply_id=supply.id,
        )
        await session.commit()
        raise FbsShipmentError("supply_bad_status", http_status=409)
    checkpointed = await _load_checkpointed_wb_delivery(session, supply, operation)
    if checkpointed is None:
        raise FbsShipmentError("fbs_shipment_checkpoint_incomplete", http_status=409)
    orders, source_plan = checkpointed

    try:
        await deliver_marketplace_supply(
            http_client,
            api_token=token,
            supply_id=supply.wb_supply_id,
        )
    except WildberriesBusinessError as exc:
        meta_context = _meta_validation_context(exc)
        message, retryable = _meta_validation_message(exc)
        await mark_operation_failed(
            session,
            operation,
            error_code="meta_validation_fail",
            # ⛔ Сырой ответ WB сохраняем обязательно.
            #
            # 02.09.2026 склад шесть раз подряд получил «повторите через минуту»
            # и встал. В базе от этих попыток остался пустой список
            # meta_validation и больше ничего: что именно сказал Wildberries,
            # восстановить было нечем — ни в логах, ни в операции. Разбор
            # занял час и потребовал лезть на боевой сервер.
            error_context={
                "meta_validation": meta_context,
                "wb_code": exc.wb_code,
                "wb_message": exc.message,
                "wb_response_body": truncate_wb_response_body(exc.response_body),
                "wb_endpoint": exc.endpoint,
            },
            wb_supply_id=supply.wb_supply_id,
            local_supply_id=supply.id,
        )
        await session.commit()
        raise FbsShipmentError(
            "meta_validation_fail",
            message=message,
            context={"meta_validation": meta_context},
            retryable=retryable,
            http_status=409,
        ) from exc
    except WildberriesClientError as exc:
        if exc.code == "transport_error":
            ref = wb_error_ref()
            log_wb_client_error(
                logger,
                "fbs shipment WB deliver timeout",
                exc,
                tenant_id=tenant_id,
                seller_id=supply.seller_id,
                local_entity_id=supply.id,
                wb_object_id=supply.wb_supply_id,
                ref=ref,
            )
            await mark_operation_pending_confirmation(
                session,
                operation,
                wb_supply_id=supply.wb_supply_id,
                local_supply_id=supply.id,
                error_code="wb_timeout",
            )
            await session.commit()
            raise FbsShipmentError(
                "wb_timeout",
                message="WB не подтвердил передачу — повторите операцию.",
                context={"operation_state": "pending_confirmation"},
                retryable=True,
                http_status=504,
            ) from exc
        error = _shipment_error_from_wb(
            exc,
            tenant_id=tenant_id,
            seller_id=supply.seller_id,
            local_entity_id=supply.id,
            wb_supply_id=supply.wb_supply_id,
            event="fbs shipment WB deliver failed",
            retryable=False,
            http_status=502,
        )
        await mark_operation_failed(
            session,
            operation,
            error_code=error.code,
            error_context=error.context,
            wb_supply_id=supply.wb_supply_id,
            local_supply_id=supply.id,
        )
        await session.commit()
        raise error from exc

    await _persist_confirmed_delivery(
        session, supply, orders, operation, actor_user_id, source_plan
    )
    await _fetch_supply_qr_after_deliver(session, supply, http_client, token)
    return supply


async def get_supply_barcode(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    *,
    type: str = "png",
) -> bytes:
    supply = await _get_supply_read(session, tenant_id, supply_id)
    if supply is None:
        raise FbsShipmentError("supply_not_found")
    if supply.status not in {FBS_SUPPLY_STATUS_IN_DELIVERY, FBS_SUPPLY_STATUS_DONE}:
        raise FbsShipmentError("supply_bad_status", http_status=409)

    if supply.barcode_file:
        cached = _resolve_barcode_path(supply.barcode_file)
        if cached.is_file():
            return cached.read_bytes()

    if supply.marketplace == "ozon":
        client_id, api_key = await _ozon_credentials(
            session,
            tenant_id,
            supply.seller_id,
        )
        provider = build_ozon_provider()
        png_bytes = await _store_ozon_supply_qr(
            session,
            supply,
            provider,
            client_id=client_id,
            api_key=api_key,
        )
        supply.barcode_file = _save_barcode_png(supply.id, png_bytes)
        await session.flush()
        return png_bytes

    token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
    try:
        png_bytes = await fetch_marketplace_supply_barcode(
            http_client,
            api_token=token,
            supply_id=supply.wb_supply_id,
            type=type,
        )
    except WildberriesClientError as exc:
        raise _shipment_error_from_wb(
            exc,
            tenant_id=tenant_id,
            seller_id=supply.seller_id,
            local_entity_id=supply.id,
            wb_supply_id=supply.wb_supply_id,
            event="fbs shipment WB supply barcode fetch failed",
        ) from exc

    supply.barcode_file = _save_barcode_png(supply.id, png_bytes)
    await session.flush()
    return png_bytes


async def retry_supply_qr(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> FbsSupply:
    """Safely fetch a missing supply QR after WB delivery was confirmed (any delivery_type)."""
    supply = await _get_supply_for_update(session, tenant_id, supply_id, with_trbxes=True)
    if supply is None:
        raise FbsShipmentError("supply_not_found")
    if supply.status not in {FBS_SUPPLY_STATUS_IN_DELIVERY, FBS_SUPPLY_STATUS_DONE}:
        raise FbsShipmentError("supply_bad_status", http_status=409)

    if supply.marketplace == "ozon":
        client_id, api_key = await _ozon_credentials(
            session,
            tenant_id,
            supply.seller_id,
        )
        await _store_ozon_supply_qr(
            session,
            supply,
            build_ozon_provider(),
            client_id=client_id,
            api_key=api_key,
        )
        return supply

    token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
    await _fetch_supply_qr_after_deliver(session, supply, http_client, token)
    return supply
