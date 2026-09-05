"""Whole-order Ozon assembly from indivisible order positions in physical boxes."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FBS_ORDER_STATUS_CANCELLED, FbsOrder, FbsOrderProduct
from app.models.fbs_packing_box import FbsPackingBox, FbsPackingBoxItem
from app.models.fbs_print_asset import FbsPrintAsset
from app.models.fbs_supply import FbsSupply
from app.schemas.ozon_fbs_api import (
    OzonFbsv4FbsPostingShipV4Request,
    OzonFbsv4FbsPostingShipV4Response,
)
from app.services.marketplace_account_service import MarketplaceAccountService
from app.services.marketplace_provider import MarketplaceProviderError, OzonMarketplaceProvider
from app.services.ozon_fbs_errors import OzonFbsProcessError
from app.services.ozon_fbs_process_service import (
    _apply_posting_readback,
    _call,
    _posting_readback,
    prepare_order_assembly,
)
from app.services.ozon_provider_factory import build_ozon_provider, ozon_live_api_enabled

ASSEMBLY_KEY = "ozon_assembly"
_SHIPPED_STATUSES = {"awaiting_deliver", "delivering", "driver_pickup", "delivered"}


async def order_packages(session: AsyncSession, order: FbsOrder) -> list[dict[str, Any]]:
    """Compare position sets before reading credentials or calling Ozon."""
    positions = list(
        (
            await session.scalars(
                select(FbsOrderProduct).where(FbsOrderProduct.order_id == order.id)
            )
        ).all()
    )
    rows = list(
        (
            await session.execute(
                select(FbsPackingBoxItem, FbsPackingBox)
                .join(FbsPackingBox, FbsPackingBox.id == FbsPackingBoxItem.box_id)
                .where(FbsPackingBoxItem.fbs_order_id == order.id)
                .order_by(FbsPackingBox.box_number, FbsPackingBoxItem.order_product_id)
            )
        ).all()
    )
    expected = {position.id for position in positions}
    assigned = [item.order_product_id for item, _ in rows]
    if (
        not expected
        or set(assigned) != expected
        or len(assigned) != len(expected)
        or any(
            box.supply_id != order.supply_id or box.tenant_id != order.tenant_id for _, box in rows
        )
    ):
        raise OzonFbsProcessError(
            "ozon_box_positions_incomplete",
            "Разложите все позиции заказа по коробам: каждая позиция должна быть в одном коробе.",
            status_code=409,
        )
    box_ids = {box.id for _, box in rows}
    foreign_order = await session.scalar(
        select(FbsPackingBoxItem.id)
        .where(
            FbsPackingBoxItem.box_id.in_(box_ids),
            FbsPackingBoxItem.fbs_order_id != order.id,
        )
        .limit(1)
    )
    if foreign_order is not None:
        raise OzonFbsProcessError(
            "ozon_box_mixed_orders",
            "В коробе Ozon могут быть позиции только одного заказа.",
            status_code=409,
        )
    by_id = {position.id: position for position in positions}
    packages: dict[uuid.UUID, list[dict[str, int]]] = {}
    for item, box in rows:
        position = by_id[item.order_product_id]
        if not position.ozon_sku or position.quantity <= 0:
            raise OzonFbsProcessError(
                "ozon_product_missing",
                "У позиции заказа нет SKU Ozon или количества.",
                status_code=409,
            )
        packages.setdefault(box.id, []).append(
            {
                "product_id": int(position.ozon_sku),
                "quantity": int(position.quantity),
            }
        )
    return [{"products": products} for products in packages.values()]


async def assemble_box_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    box_id: uuid.UUID,
    *,
    provider: OzonMarketplaceProvider | None = None,
    credentials: tuple[str, str] | None = None,
) -> uuid.UUID:
    # Same supply lock as box assignment: the package snapshot cannot change during ship.
    supply = await session.scalar(
        select(FbsSupply)
        .where(
            FbsSupply.id == supply_id,
            FbsSupply.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    if supply is None or supply.marketplace != "ozon":
        raise OzonFbsProcessError("supply_not_found", "Поставка Ozon не найдена.", status_code=404)
    box = await session.scalar(
        select(FbsPackingBox).where(
            FbsPackingBox.id == box_id,
            FbsPackingBox.supply_id == supply_id,
            FbsPackingBox.tenant_id == tenant_id,
        )
    )
    if box is None:
        raise OzonFbsProcessError("box_not_found", "Короб не найден.", status_code=404)
    order_ids = list(
        (
            await session.scalars(
                select(FbsPackingBoxItem.fbs_order_id)
                .where(
                    FbsPackingBoxItem.box_id == box_id,
                )
                .distinct()
            )
        ).all()
    )
    if len(order_ids) != 1:
        raise OzonFbsProcessError(
            "ozon_box_order_required",
            "Положите в короб позиции одного заказа Ozon.",
            status_code=409,
        )
    order = await session.scalar(
        select(FbsOrder)
        .where(
            FbsOrder.id == order_ids[0],
            FbsOrder.tenant_id == tenant_id,
            FbsOrder.supply_id == supply_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if order is None or order.status == FBS_ORDER_STATUS_CANCELLED:
        raise OzonFbsProcessError(
            "order_not_in_supply", "Заказ недоступен для сборки.", status_code=409
        )
    assembly = (order.meta_details_json or {}).get(ASSEMBLY_KEY)
    packages = await order_packages(session, order)
    if isinstance(assembly, dict) and len(assembly.get("posting_numbers") or []) == len(packages):
        return order.id
    if provider is None:
        if not ozon_live_api_enabled():
            raise OzonFbsProcessError(
                "ozon_live_handoff_blocked",
                "Обмен с Ozon выключен настройкой.",
                status_code=503,
            )
        provider = build_ozon_provider()
    client_id, api_key = credentials or await MarketplaceAccountService(session).stored_credentials(
        tenant_id,
        supply.seller_id,
    )
    posting_number = order.external_order_id or ""
    if not posting_number:
        raise OzonFbsProcessError("ozon_posting_number_missing", "Нет номера отправления Ozon.")
    posting = await _posting_readback(
        provider,
        client_id=client_id,
        api_key=api_key,
        posting_number=posting_number,
    )
    result = posting.result
    if (
        result is not None
        and result.status in _SHIPPED_STATUSES
        and result.substatus != "ship_failed"
    ):
        related = result.related_postings
        numbers = list(
            dict.fromkeys((related.related_posting_numbers or []) if related is not None else [])
        )
        if len(packages) == 1 and not numbers:
            numbers = [posting_number]
        if len(numbers) < len(packages):
            raise OzonFbsProcessError(
                "ozon_assembly_unconfirmed",
                "Ozon уже собрал заказ, но пока не вернул номера всех упаковок. "
                "Повторите QR позже.",
                status_code=409,
            )
        _apply_posting_readback(order, posting, require_shipped=False)
        order.meta_details_json = {
            **(order.meta_details_json or {}),
            ASSEMBLY_KEY: {
                "posting_numbers": numbers,
                "recovered_from_readback": True,
            },
        }
        await _invalidate_old_label(session, order)
        await session.commit()
        return order.id
    if isinstance(assembly, dict):
        raise OzonFbsProcessError(
            "ozon_assembly_unconfirmed",
            "Ответ на сборку ещё не подтверждён Ozon. "
            "Повторите QR позже: повторно заказ не отправлен.",
            status_code=409,
        )
    await prepare_order_assembly(
        session,
        order,
        provider,
        client_id=client_id,
        api_key=api_key,
        posting=posting,
    )
    # Persist intent before the irreversible request. An ambiguous timeout only permits readback.
    order.meta_details_json = {
        **(order.meta_details_json or {}),
        ASSEMBLY_KEY: {
            "posting_numbers": [],
        },
    }
    await session.commit()
    await session.scalar(select(FbsSupply.id).where(FbsSupply.id == supply_id).with_for_update())
    try:
        response = await _call(
            provider,
            client_id=client_id,
            api_key=api_key,
            path="/v4/posting/fbs/ship",
            request=OzonFbsv4FbsPostingShipV4Request.model_validate(
                {
                    "posting_number": posting_number,
                    "packages": packages,
                    "with": {"additional_data": True},
                }
            ),
            response_type=OzonFbsv4FbsPostingShipV4Response,
            read=False,
        )
    except MarketplaceProviderError as exc:
        # Explicit rejection permits correcting the contents; timeout/5xx remains uncertain.
        if exc.status_code in {400, 401, 403, 404, 409, 422, 429}:
            details = dict(order.meta_details_json or {})
            details.pop(ASSEMBLY_KEY, None)
            order.meta_details_json = details
            await session.commit()
        raise
    numbers = list(dict.fromkeys(response.result or []))
    order.meta_details_json = {
        **(order.meta_details_json or {}),
        ASSEMBLY_KEY: {
            "posting_numbers": numbers,
            "ship_response": response.model_dump(by_alias=True, exclude_none=True),
        },
    }
    await _invalidate_old_label(session, order)
    await session.commit()
    if len(numbers) != len(packages):
        raise OzonFbsProcessError(
            "ozon_assembly_unconfirmed",
            "Ozon принял запрос, но не вернул номера всех упаковок. Повторите QR позже.",
            status_code=409,
        )
    return order.id


async def _invalidate_old_label(session: AsyncSession, order: FbsOrder) -> None:
    # A previously cached parent PDF does not contain the newly split posting labels.
    await session.execute(
        update(FbsPrintAsset)
        .where(
            FbsPrintAsset.fbs_order_id == order.id,
            FbsPrintAsset.kind == "order_sticker",
        )
        .values(status="requesting")
    )
    order.sticker_status = "requesting"
