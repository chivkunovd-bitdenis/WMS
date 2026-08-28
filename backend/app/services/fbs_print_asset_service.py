"""FBS print assets: batch fetch, binary content, applied confirmation."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_order import (
    FBS_ORDER_STATUS_CANCELLED,
    STICKER_STATUS_APPLIED,
    STICKER_STATUS_ERROR,
    STICKER_STATUS_PRINT_OPENED,
    STICKER_STATUS_READY,
    STICKER_STATUS_REQUESTING,
    FbsOrder,
)
from app.models.fbs_print_asset import (
    FBS_PRINT_ASSET_KINDS,
    PRINT_ASSET_KIND_CARGO_PLACE_QR,
    PRINT_ASSET_KIND_ORDER_STICKER,
    PRINT_ASSET_KIND_SUPPLY_QR,
    PRINT_ASSET_STATUS_ERROR,
    PRINT_ASSET_STATUS_READY,
    PRINT_ASSET_STATUS_REQUESTING,
    FbsPrintAsset,
)
from app.models.fbs_supply import FbsSupply
from app.models.fbs_trbx import FbsTrbx
from app.services.fbs_cancelled_after_pack_service import (
    cancelled_operation_message,
    order_belonged_to_supply,
)
from app.services.fbs_print_asset_storage import (
    ORDER_STICKER_CONTENT_TYPE,
    ORDER_STICKER_HEIGHT_MM,
    ORDER_STICKER_WIDTH_MM,
    FbsPrintAssetStorageError,
    cargo_qr_relative_path,
    decode_png_payload,
    order_sticker_relative_path,
    read_png,
    resolve_existing_storage_path,
    save_png,
    sha256_checksum,
    supply_qr_relative_path,
)
from app.services.fbs_sticker_code_service import (
    sticker_barcode_from_wb_row,
    sticker_code_from_wb_row,
)
from app.services.marketplace_provider import (
    FakeMarketplaceTransport,
    MarketplaceProviderError,
    OzonMarketplaceProvider,
    provider_error_message,
)
from app.services.wildberries_client import (
    WildberriesClientError,
    fetch_marketplace_order_stickers,
    fetch_marketplace_trbx_stickers,
)
from app.services.wildberries_credentials_service import (
    _seller_in_tenant,
    get_decrypted_marketplace_token,
)

WB_STICKER_CHUNK_SIZE = 100

OrderLabelFetch = Callable[[list[str]], Awaitable[list[dict[str, Any]]]]


async def fetch_order_label_rows_for_marketplace(
    marketplace: str,
    *,
    external_order_ids: list[str],
    wb_fetch: OrderLabelFetch,
    ozon_fetch: OrderLabelFetch,
) -> list[dict[str, Any]]:
    if marketplace == "wb":
        return await wb_fetch(external_order_ids)
    if marketplace == "ozon":
        return await ozon_fetch(external_order_ids)
    raise FbsPrintAssetError(
        "unsupported_marketplace",
        message="Маркетплейс поставки не поддерживает печать этикеток.",
    )


_FAKE_OZON_LABEL_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
    "hQGAhKmMIQAAAABJRU5ErkJggg=="
)


async def _fake_ozon_order_label_fetch(
    external_order_ids: list[str],
) -> list[dict[str, Any]]:
    provider = OzonMarketplaceProvider(
        transport=FakeMarketplaceTransport(
            order_labels=[
                {
                    "posting_number": external_order_id,
                    "file": _FAKE_OZON_LABEL_PNG_BASE64,
                    "barcode": external_order_id,
                }
                for external_order_id in external_order_ids
            ]
        )
    )
    return await provider.fetch_order_labels(
        client_id="fake",
        api_key="fake",
        posting_numbers=external_order_ids,
    )


class FbsPrintAssetSupplyError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


async def _require_marketplace_token(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> str:
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsPrintAssetSupplyError("seller_not_found")
    token = await get_decrypted_marketplace_token(session, tenant_id, seller_id)
    if not token:
        raise FbsPrintAssetSupplyError("missing_marketplace_token")
    return token


class FbsPrintAssetError(Exception):
    def __init__(
        self,
        code: str,
        *,
        message: str | None = None,
        context: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        self.code = code
        self.message = message or code
        self.context = context or {}
        self.retryable = retryable
        super().__init__(code)


@dataclass
class PrintOrderError:
    order_id: uuid.UUID
    wb_order_id: int
    code: str
    message: str


@dataclass
class PrintBatchResult:
    requested: int
    ready: int
    missing: int
    failed: int
    assets: list[FbsPrintAsset] = field(default_factory=list)
    order_errors: list[PrintOrderError] = field(default_factory=list)


def print_asset_content_url(asset_id: uuid.UUID) -> str:
    return f"/operations/fbs-print-assets/{asset_id}/content"


def map_print_asset(asset: FbsPrintAsset) -> dict[str, Any]:
    # «Готово» в базе ещё не значит, что файл на месте: 27.08.2026 выкатка стёрла
    # 1756 PNG, а карточки остались готовыми — экран обещал печать, а запрос за
    # картинкой отвечал 404. Считаем готовым только то, что реально лежит на диске.
    file_ready = _asset_file_present(asset)
    status = asset.status if file_ready or asset.status != PRINT_ASSET_STATUS_READY else (
        PRINT_ASSET_STATUS_ERROR
    )
    url = print_asset_content_url(asset.id) if file_ready else None
    error_code = asset.error_code or (None if file_ready else "file_missing")
    error_message = asset.error_message or (
        "" if file_ready else "Файл печати не найден — запросите его у WB заново."
    )
    return {
        "id": str(asset.id),
        "kind": asset.kind,
        "status": status,
        "content_type": asset.content_type,
        "width_mm": asset.width_mm,
        "height_mm": asset.height_mm,
        "preview_url": url,
        "download_url": url,
        "checksum": asset.checksum,
        "applied_at": asset.applied_at.isoformat() if asset.applied_at else None,
        "error": (
            {"code": error_code, "message": error_message}
            if error_code
            else None
        ),
    }


async def _get_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> FbsSupply:
    stmt = (
        select(FbsSupply)
        .where(FbsSupply.id == supply_id, FbsSupply.tenant_id == tenant_id)
        .options(selectinload(FbsSupply.orders))
    )
    result = await session.execute(stmt)
    supply = result.scalar_one_or_none()
    if supply is None:
        raise FbsPrintAssetError("supply_not_found", message="Поставка не найдена.")
    return supply


async def _load_asset(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    asset_id: uuid.UUID,
) -> FbsPrintAsset | None:
    stmt = select(FbsPrintAsset).where(
        FbsPrintAsset.id == asset_id,
        FbsPrintAsset.tenant_id == tenant_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _find_order_sticker_asset(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
) -> FbsPrintAsset | None:
    stmt = select(FbsPrintAsset).where(
        FbsPrintAsset.tenant_id == tenant_id,
        FbsPrintAsset.fbs_order_id == order_id,
        FbsPrintAsset.kind == PRINT_ASSET_KIND_ORDER_STICKER,
    )
    result = await session.execute(stmt)
    return result.scalars().first()


def _asset_file_present(asset: FbsPrintAsset) -> bool:
    """Есть ли файл на диске. Дешёвая проверка для списков — без чтения PNG."""
    if asset.status != PRINT_ASSET_STATUS_READY or not asset.storage_path:
        return False
    try:
        return resolve_existing_storage_path(asset.storage_path).is_file()
    except FbsPrintAssetStorageError:
        return False


def _asset_file_ready(asset: FbsPrintAsset) -> bool:
    if asset.status != PRINT_ASSET_STATUS_READY or not asset.storage_path:
        return False
    try:
        read_png(asset.storage_path, checksum=asset.checksum)
    except FbsPrintAssetStorageError:
        return False
    return True


def _mark_asset_error(
    asset: FbsPrintAsset,
    *,
    code: str,
    message: str,
) -> None:
    asset.status = PRINT_ASSET_STATUS_ERROR
    asset.error_code = code
    asset.error_message = message


def _persist_order_sticker_bytes(
    *,
    asset: FbsPrintAsset,
    order: FbsOrder,
    png_bytes: bytes,
    sticker_code: str | None,
    sticker_barcode: str | None = None,
    fetched_at: datetime,
) -> None:
    rel = order_sticker_relative_path(order.id)
    save_png(rel, png_bytes)
    asset.status = PRINT_ASSET_STATUS_READY
    asset.content_type = ORDER_STICKER_CONTENT_TYPE
    asset.storage_path = rel
    asset.checksum = sha256_checksum(png_bytes)
    asset.width_mm = ORDER_STICKER_WIDTH_MM
    asset.height_mm = ORDER_STICKER_HEIGHT_MM
    asset.wb_fetched_at = fetched_at
    asset.error_code = None
    asset.error_message = None
    order.sticker_file = rel
    if sticker_code:
        order.sticker_code = sticker_code
    if sticker_barcode:
        order.sticker_barcode = sticker_barcode
    order.sticker_status = STICKER_STATUS_READY


async def _find_cargo_qr_asset(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    trbx_id: uuid.UUID,
) -> FbsPrintAsset | None:
    stmt = select(FbsPrintAsset).where(
        FbsPrintAsset.tenant_id == tenant_id,
        FbsPrintAsset.fbs_trbx_id == trbx_id,
        FbsPrintAsset.kind == PRINT_ASSET_KIND_CARGO_PLACE_QR,
    )
    result = await session.execute(stmt)
    return result.scalars().first()


def _persist_cargo_qr_bytes(
    *,
    asset: FbsPrintAsset,
    trbx: FbsTrbx,
    png_bytes: bytes,
    fetched_at: datetime,
) -> None:
    rel = cargo_qr_relative_path(trbx.id)
    save_png(rel, png_bytes)
    asset.status = PRINT_ASSET_STATUS_READY
    asset.content_type = ORDER_STICKER_CONTENT_TYPE
    asset.storage_path = rel
    asset.checksum = sha256_checksum(png_bytes)
    asset.width_mm = ORDER_STICKER_WIDTH_MM
    asset.height_mm = ORDER_STICKER_HEIGHT_MM
    asset.wb_fetched_at = fetched_at
    asset.error_code = None
    asset.error_message = None
    trbx.qr_asset_id = asset.id
    trbx.sticker_file = rel


async def ensure_cargo_place_qr_assets(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
    http_client: httpx.AsyncClient,
    *,
    trbxes: list[FbsTrbx] | None = None,
) -> None:
    target_trbxes = trbxes if trbxes is not None else list(supply.trbxes)
    if not target_trbxes:
        return

    uncached: list[FbsTrbx] = []
    for trbx in target_trbxes:
        asset = await _find_cargo_qr_asset(session, tenant_id, trbx.id)
        if asset is not None and _asset_file_ready(asset):
            if trbx.qr_asset_id is None:
                trbx.qr_asset_id = asset.id
            continue
        uncached.append(trbx)

    if not uncached:
        await session.flush()
        return

    try:
        token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
    except FbsPrintAssetSupplyError as exc:
        raise FbsPrintAssetError(exc.code, message="Нет доступа к маркетплейсу.") from exc

    fetched_at = datetime.now(tz=UTC)
    for trbx in uncached:
        try:
            sticker_rows = await fetch_marketplace_trbx_stickers(
                http_client,
                api_token=token,
                supply_id=supply.wb_supply_id,
                trbx_ids=[trbx.wb_trbx_id],
            )
        except WildberriesClientError as exc:
            suffix = f"_{exc.status_code}" if exc.status_code else ""
            raise FbsPrintAssetError(
                f"wb_{exc.code}{suffix}",
                message="WB не вернул QR грузоместа.",
                retryable=True,
            ) from exc

        sticker_row: dict[str, Any] | None = None
        for row in sticker_rows:
            for key in ("trbxId", "trbx_id", "id"):
                wb_id = row.get(key)
                if wb_id is not None and str(wb_id) == trbx.wb_trbx_id:
                    sticker_row = row
                    break
            if sticker_row is not None:
                break
        if sticker_row is None and len(sticker_rows) == 1:
            sticker_row = sticker_rows[0]
        if sticker_row is None:
            raise FbsPrintAssetError(
                "wb_invalid_response",
                message="WB не вернул QR для грузоместа.",
            )
        png_bytes: bytes | None = None
        for key in ("file", "barcode", "image"):
            png_bytes = decode_png_payload(sticker_row.get(key))
            if png_bytes is not None:
                break
        if png_bytes is None:
            raise FbsPrintAssetError(
                "invalid_sticker_payload",
                message="Некорректные данные QR грузоместа.",
            )

        asset = await _find_cargo_qr_asset(session, tenant_id, trbx.id)
        if asset is None:
            asset = FbsPrintAsset(
                tenant_id=tenant_id,
                seller_id=supply.seller_id,
                kind=PRINT_ASSET_KIND_CARGO_PLACE_QR,
                status=PRINT_ASSET_STATUS_REQUESTING,
                fbs_trbx_id=trbx.id,
            )
            session.add(asset)
            await session.flush()
        try:
            _persist_cargo_qr_bytes(
                asset=asset,
                trbx=trbx,
                png_bytes=png_bytes,
                fetched_at=fetched_at,
            )
        except FbsPrintAssetStorageError as exc:
            _mark_asset_error(
                asset,
                code=exc.code,
                message="Не удалось сохранить QR грузоместа.",
            )
            raise FbsPrintAssetError(
                exc.code,
                message="Не удалось сохранить QR грузоместа.",
            ) from exc

    await session.flush()


async def upsert_order_sticker_asset_from_bytes(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    supply_id: uuid.UUID,
    order: FbsOrder,
    png_bytes: bytes,
    sticker_code: str | None,
    sticker_barcode: str | None = None,
    fetched_at: datetime | None = None,
) -> FbsPrintAsset:
    when = fetched_at or datetime.now(tz=UTC)
    asset = await _find_order_sticker_asset(session, tenant_id, order.id)
    if asset is None:
        asset = FbsPrintAsset(
            tenant_id=tenant_id,
            seller_id=seller_id,
            kind=PRINT_ASSET_KIND_ORDER_STICKER,
            status=PRINT_ASSET_STATUS_REQUESTING,
            fbs_order_id=order.id,
        )
        session.add(asset)
        await session.flush()
    try:
        _persist_order_sticker_bytes(
            asset=asset,
            order=order,
            png_bytes=png_bytes,
            sticker_code=sticker_code,
            sticker_barcode=sticker_barcode,
            fetched_at=when,
        )
    except FbsPrintAssetStorageError as exc:
        _mark_asset_error(asset, code=exc.code, message="Не удалось сохранить стикер.")
        order.sticker_status = STICKER_STATUS_ERROR
        raise
    return asset


async def upsert_supply_qr_asset_from_bytes(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
    png_bytes: bytes,
    fetched_at: datetime | None = None,
) -> FbsPrintAsset:
    stmt = select(FbsPrintAsset).where(
        FbsPrintAsset.tenant_id == tenant_id,
        FbsPrintAsset.fbs_supply_id == supply.id,
        FbsPrintAsset.kind == PRINT_ASSET_KIND_SUPPLY_QR,
    )
    asset = (await session.execute(stmt)).scalars().first()
    if asset is None:
        asset = FbsPrintAsset(
            tenant_id=tenant_id,
            seller_id=supply.seller_id,
            kind=PRINT_ASSET_KIND_SUPPLY_QR,
            status=PRINT_ASSET_STATUS_REQUESTING,
            fbs_supply_id=supply.id,
        )
        session.add(asset)
        await session.flush()

    rel = supply_qr_relative_path(supply.id)
    save_png(rel, png_bytes)
    asset.status = PRINT_ASSET_STATUS_READY
    asset.content_type = ORDER_STICKER_CONTENT_TYPE
    asset.storage_path = rel
    asset.checksum = sha256_checksum(png_bytes)
    asset.width_mm = ORDER_STICKER_WIDTH_MM
    asset.height_mm = ORDER_STICKER_HEIGHT_MM
    asset.wb_fetched_at = fetched_at or datetime.now(tz=UTC)
    asset.error_code = None
    asset.error_message = None
    supply.barcode_asset_id = asset.id
    await session.flush()
    return asset


async def request_supply_print_batch(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    kind: str,
    order_ids: list[uuid.UUID] | None,
    retry_missing: bool,
    http_client: httpx.AsyncClient,
) -> PrintBatchResult:
    if kind not in FBS_PRINT_ASSET_KINDS:
        raise FbsPrintAssetError("invalid_kind", message="Неизвестный тип печатного актива.")
    if kind != PRINT_ASSET_KIND_ORDER_STICKER:
        raise FbsPrintAssetError(
            "kind_not_implemented",
            message="Печать этого типа будет доступна позже.",
        )
    if order_ids is not None and not order_ids:
        raise FbsPrintAssetError("invalid_order_ids", message="Список заказов пуст.")

    supply = await _get_supply(session, tenant_id, supply_id)
    marketplace = getattr(supply, "marketplace", "wb")
    supply_orders = {order.id: order for order in supply.orders}
    blocked_orders: list[FbsOrder] = []
    if order_ids is None:
        requested_orders = list(supply.orders)
    else:
        requested_orders = []
        detached_orders = {
            order.id: order
            for order in (
                await session.execute(
                    select(FbsOrder).where(
                        FbsOrder.tenant_id == tenant_id,
                        FbsOrder.id.in_(order_ids),
                    )
                )
            ).scalars()
        }
        for oid in order_ids:
            order = supply_orders.get(oid) or detached_orders.get(oid)
            if order is None:
                raise FbsPrintAssetError(
                    "order_not_in_supply",
                    message="Заказ не входит в поставку.",
                    context={"order_id": str(oid)},
                )
            if order.id not in supply_orders and not await order_belonged_to_supply(
                session, order, supply
            ):
                raise FbsPrintAssetError(
                    "order_not_in_supply",
                    message="Заказ не входит в поставку.",
                    context={"order_id": str(oid)},
                )
            requested_orders.append(order)

    target_orders: list[FbsOrder] = []
    for order in requested_orders:
        if order.status == FBS_ORDER_STATUS_CANCELLED:
            blocked_orders.append(order)
        else:
            target_orders.append(order)

    result = PrintBatchResult(
        requested=len(requested_orders),
        ready=0,
        missing=0,
        failed=0,
    )
    result.order_errors.extend(
        PrintOrderError(
            order_id=order.id,
            wb_order_id=int(order.wb_order_id),
            code="order_cancelled",
            message=cancelled_operation_message(order, "клеить стикер нельзя"),
        )
        for order in blocked_orders
    )
    result.failed = len(result.order_errors)
    if not target_orders:
        return result

    to_fetch: list[FbsOrder] = []
    for order in target_orders:
        asset = await _find_order_sticker_asset(session, tenant_id, order.id)
        if retry_missing and asset is not None and _asset_file_ready(asset):
            continue
        if (
            asset is not None
            and asset.status == PRINT_ASSET_STATUS_READY
            and not _asset_file_ready(asset)
        ):
            _mark_asset_error(
                asset,
                code="file_missing",
                message="Файл стикера отсутствует на диске.",
            )
            order.sticker_status = STICKER_STATUS_ERROR
        to_fetch.append(order)
        order.sticker_status = STICKER_STATUS_REQUESTING

    if to_fetch:
        token: str | None = None
        if marketplace == "wb":
            try:
                token = await _require_marketplace_token(
                    session, tenant_id, supply.seller_id
                )
            except FbsPrintAssetSupplyError as exc:
                raise FbsPrintAssetError(
                    exc.code, message="Нет доступа к маркетплейсу."
                ) from exc

        async def wb_fetch(external_order_ids: list[str]) -> list[dict[str, Any]]:
            if token is None:
                raise FbsPrintAssetError(
                    "missing_marketplace_token",
                    message="Нет доступа к Wildberries.",
                )
            return await fetch_marketplace_order_stickers(
                http_client,
                api_token=token,
                order_ids=[int(order_id) for order_id in external_order_ids],
            )

        fetched_at = datetime.now(tz=UTC)
        for chunk_start in range(0, len(to_fetch), WB_STICKER_CHUNK_SIZE):
            chunk = to_fetch[chunk_start : chunk_start + WB_STICKER_CHUNK_SIZE]
            external_order_ids = [
                (
                    str(order.wb_order_id)
                    if marketplace == "wb"
                    else order.external_order_id or str(order.wb_order_id)
                )
                for order in chunk
            ]
            try:
                sticker_rows = await fetch_order_label_rows_for_marketplace(
                    marketplace,
                    external_order_ids=external_order_ids,
                    wb_fetch=wb_fetch,
                    ozon_fetch=_fake_ozon_order_label_fetch,
                )
            except WildberriesClientError as exc:
                suffix = f"_{exc.status_code}" if exc.status_code else ""
                code = f"wb_{exc.code}{suffix}"
                for order in chunk:
                    result.failed += 1
                    result.order_errors.append(
                        PrintOrderError(
                            order_id=order.id,
                            wb_order_id=int(order.wb_order_id),
                            code=code,
                            message="WB не вернул стикер.",
                        )
                    )
                    order.sticker_status = STICKER_STATUS_ERROR
                continue
            except MarketplaceProviderError as exc:
                message = provider_error_message(exc)
                for order in chunk:
                    result.failed += 1
                    result.order_errors.append(
                        PrintOrderError(
                            order_id=order.id,
                            wb_order_id=int(order.wb_order_id),
                            code=(
                                "ozon_account_blocked"
                                if exc.is_account_blocked
                                else exc.code
                            ),
                            message=message,
                        )
                    )
                    order.sticker_status = STICKER_STATUS_ERROR
                continue

            by_external_id: dict[str, dict[str, Any]] = {}
            for row in sticker_rows:
                oid_raw = (
                    row.get("orderId")
                    or row.get("order_id")
                    or row.get("posting_number")
                    or row.get("external_order_id")
                )
                if oid_raw is not None:
                    by_external_id[str(oid_raw)] = row

            for order in chunk:
                external_order_id = (
                    str(order.wb_order_id)
                    if marketplace == "wb"
                    else order.external_order_id or str(order.wb_order_id)
                )
                sticker_row = by_external_id.get(external_order_id)
                if sticker_row is None:
                    provider_name = (
                        "Ozon" if marketplace == "ozon" else "Wildberries"
                    )
                    result.failed += 1
                    result.order_errors.append(
                        PrintOrderError(
                            order_id=order.id,
                            wb_order_id=int(order.wb_order_id),
                            code=f"{marketplace}_stickers_incomplete",
                            message=f"Этикетка не найдена в ответе {provider_name}.",
                        )
                    )
                    order.sticker_status = STICKER_STATUS_ERROR
                    asset = await _find_order_sticker_asset(session, tenant_id, order.id)
                    if asset is None:
                        asset = FbsPrintAsset(
                            tenant_id=tenant_id,
                            seller_id=supply.seller_id,
                            kind=PRINT_ASSET_KIND_ORDER_STICKER,
                            status=PRINT_ASSET_STATUS_REQUESTING,
                            fbs_order_id=order.id,
                        )
                        session.add(asset)
                        await session.flush()
                    _mark_asset_error(
                        asset,
                        code=f"{marketplace}_stickers_incomplete",
                        message="Этикетка заказа не найдена в ответе маркетплейса.",
                    )
                    continue

                sticker_code = sticker_code_from_wb_row(sticker_row)
                sticker_barcode = sticker_barcode_from_wb_row(sticker_row)
                png_bytes: bytes | None = None
                for payload_key in ("file", "label", "image"):
                    png_bytes = decode_png_payload(sticker_row.get(payload_key))
                    if png_bytes is not None:
                        break
                asset = await _find_order_sticker_asset(session, tenant_id, order.id)
                if asset is None:
                    asset = FbsPrintAsset(
                        tenant_id=tenant_id,
                        seller_id=supply.seller_id,
                        kind=PRINT_ASSET_KIND_ORDER_STICKER,
                        status=PRINT_ASSET_STATUS_REQUESTING,
                        fbs_order_id=order.id,
                    )
                    session.add(asset)
                    await session.flush()

                if png_bytes is None:
                    result.failed += 1
                    result.order_errors.append(
                        PrintOrderError(
                            order_id=order.id,
                            wb_order_id=int(order.wb_order_id),
                            code="invalid_sticker_payload",
                            message="Некорректные данные стикера.",
                        )
                    )
                    _mark_asset_error(
                        asset,
                        code="invalid_sticker_payload",
                        message="Некорректные данные стикера.",
                    )
                    order.sticker_status = STICKER_STATUS_ERROR
                    continue

                try:
                    _persist_order_sticker_bytes(
                        asset=asset,
                        order=order,
                        png_bytes=png_bytes,
                        sticker_code=sticker_code,
                        sticker_barcode=sticker_barcode,
                        fetched_at=fetched_at,
                    )
                except FbsPrintAssetStorageError as exc:
                    result.failed += 1
                    result.order_errors.append(
                        PrintOrderError(
                            order_id=order.id,
                            wb_order_id=int(order.wb_order_id),
                            code=exc.code,
                            message="Не удалось сохранить стикер.",
                        )
                    )
                    _mark_asset_error(
                        asset,
                        code=exc.code,
                        message="Не удалось сохранить стикер.",
                    )
                    order.sticker_status = STICKER_STATUS_ERROR
                    continue

                result.assets.append(asset)
                result.ready += 1

    result.assets = []
    result.ready = 0
    result.failed = len(result.order_errors)
    failed_order_ids = {err.order_id for err in result.order_errors}
    for order in target_orders:
        asset = await _find_order_sticker_asset(session, tenant_id, order.id)
        if asset is not None and _asset_file_ready(asset):
            result.assets.append(asset)
            result.ready += 1
        elif order.id in failed_order_ids:
            continue
        else:
            result.missing += 1

    result.failed = len(result.order_errors)
    await session.flush()
    return result


async def get_asset_binary_content(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    asset_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    record_print_opened: bool = True,
) -> tuple[bytes, str, FbsPrintAsset]:
    asset = await _load_asset(session, tenant_id, asset_id)
    if asset is None:
        raise FbsPrintAssetError(
            "asset_not_found",
            message="Печатный актив не найден.",
        )
    if asset.fbs_order_id is not None:
        order = await session.get(FbsOrder, asset.fbs_order_id)
        if order is not None and order.status == FBS_ORDER_STATUS_CANCELLED:
            raise FbsPrintAssetError(
                "order_cancelled",
                message=cancelled_operation_message(order, "клеить стикер нельзя"),
                context={"order_id": str(order.id)},
            )
    if asset.status != PRINT_ASSET_STATUS_READY or not asset.storage_path:
        raise FbsPrintAssetError(
            "asset_not_ready",
            message="Печатный актив ещё не готов.",
            context={"asset_id": str(asset_id)},
        )
    try:
        png_bytes = read_png(asset.storage_path, checksum=asset.checksum)
    except FbsPrintAssetStorageError as exc:
        _mark_asset_error(asset, code=exc.code, message="Файл печати недоступен.")
        if asset.fbs_order_id is not None:
            order = await session.get(FbsOrder, asset.fbs_order_id)
            if order is not None:
                order.sticker_status = STICKER_STATUS_ERROR
        raise FbsPrintAssetError(
            "asset_not_ready",
            message="Файл печати недоступен.",
            context={"asset_id": str(asset_id), "reason": exc.code},
        ) from exc

    if record_print_opened and asset.print_opened_at is None:
        asset.print_opened_at = datetime.now(tz=UTC)
        if asset.fbs_order_id is not None:
            order = await session.get(FbsOrder, asset.fbs_order_id)
            if order is not None and order.sticker_status == STICKER_STATUS_READY:
                order.sticker_status = STICKER_STATUS_PRINT_OPENED

    content_type = asset.content_type or ORDER_STICKER_CONTENT_TYPE
    _ = user_id
    await session.flush()
    return png_bytes, content_type, asset


async def confirm_asset_applied(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    asset_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    idempotency_key: str,
) -> FbsPrintAsset:
    _ = idempotency_key
    asset = await _load_asset(session, tenant_id, asset_id)
    if asset is None:
        raise FbsPrintAssetError(
            "asset_not_found",
            message="Печатный актив не найден.",
        )
    if asset.fbs_order_id is not None:
        order = await session.get(FbsOrder, asset.fbs_order_id)
        if order is not None and order.status == FBS_ORDER_STATUS_CANCELLED:
            raise FbsPrintAssetError(
                "order_cancelled",
                message=cancelled_operation_message(order, "клеить стикер нельзя"),
                context={"order_id": str(order.id)},
            )
    if asset.status != PRINT_ASSET_STATUS_READY:
        raise FbsPrintAssetError(
            "asset_not_ready",
            message="Нельзя подтвердить нанесение: актив не готов.",
        )
    if not _asset_file_ready(asset):
        raise FbsPrintAssetError(
            "asset_not_ready",
            message="Нельзя подтвердить нанесение: файл недоступен.",
        )

    if asset.applied_at is None:
        now = datetime.now(tz=UTC)
        asset.applied_at = now
        asset.applied_by_user_id = user_id
        if asset.fbs_order_id is not None:
            order = await session.get(FbsOrder, asset.fbs_order_id)
            if order is not None:
                order.sticker_applied_at = now
                order.sticker_status = STICKER_STATUS_APPLIED
        if asset.fbs_trbx_id is not None and asset.kind == PRINT_ASSET_KIND_CARGO_PLACE_QR:
            trbx = await session.get(FbsTrbx, asset.fbs_trbx_id)
            if trbx is not None:
                trbx.qr_applied_at = now
                trbx.qr_applied_by_user_id = user_id
                trbx.qr_asset_id = asset.id

    await session.flush()
    return asset
