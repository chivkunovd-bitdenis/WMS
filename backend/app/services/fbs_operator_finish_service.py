"""Local operator completion after WB composition fixation and required QR printing."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_print_asset import (
    PRINT_ASSET_KIND_CARGO_PLACE_QR,
    PRINT_ASSET_KIND_SUPPLY_QR,
    PRINT_ASSET_STATUS_READY,
    FbsPrintAsset,
)
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_PVZ,
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_DONE,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FbsSupply,
)
from app.models.fbs_trbx import FbsTrbx
from app.services.fbs_workspace_service import get_supply_workspace


class FbsOperatorFinishError(Exception):
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


def _was_printed(asset: FbsPrintAsset | None) -> bool:
    return bool(
        asset is not None
        and asset.status == PRINT_ASSET_STATUS_READY
        and (asset.print_opened_at is not None or asset.applied_at is not None)
    )


async def _load_supply_for_update(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> FbsSupply | None:
    stmt = (
        select(FbsSupply)
        .where(FbsSupply.id == supply_id, FbsSupply.tenant_id == tenant_id)
        .with_for_update()
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _warehouse_supply_qr(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> FbsPrintAsset | None:
    stmt = select(FbsPrintAsset).where(
        FbsPrintAsset.tenant_id == tenant_id,
        FbsPrintAsset.fbs_supply_id == supply_id,
        FbsPrintAsset.kind == PRINT_ASSET_KIND_SUPPLY_QR,
    )
    return (await session.execute(stmt)).scalars().first()


async def _pvz_qr_readiness(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> tuple[int, list[str]]:
    trbx_rows = list(
        (
            await session.execute(
                select(FbsTrbx.id).where(
                    FbsTrbx.supply_id == supply_id,
                )
            )
        ).scalars()
    )
    if not trbx_rows:
        return 0, []
    assets = list(
        (
            await session.execute(
                select(FbsPrintAsset).where(
                    FbsPrintAsset.tenant_id == tenant_id,
                    FbsPrintAsset.fbs_trbx_id.in_(trbx_rows),
                    FbsPrintAsset.kind == PRINT_ASSET_KIND_CARGO_PLACE_QR,
                )
            )
        ).scalars()
    )
    by_trbx = {asset.fbs_trbx_id: asset for asset in assets}
    missing = [str(trbx_id) for trbx_id in trbx_rows if not _was_printed(by_trbx.get(trbx_id))]
    return len(trbx_rows), missing


async def finish_operator_work(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    idempotency_key: str,
) -> dict[str, Any]:
    """Finish local work only after the route-specific QR has been opened for print."""
    supply = await _load_supply_for_update(session, tenant_id, supply_id)
    if supply is None:
        raise FbsOperatorFinishError("supply_not_found", http_status=404)

    if supply.operator_finished_at is not None:
        return await get_supply_workspace(session, tenant_id, supply_id)

    if supply.status not in {FBS_SUPPLY_STATUS_IN_DELIVERY, FBS_SUPPLY_STATUS_DONE}:
        raise FbsOperatorFinishError(
            "supply_not_delivered",
            message="Сначала зафиксируйте состав поставки в WB и получите маршрутный QR.",
            context={"supply_status": supply.status},
            http_status=409,
        )

    if supply.delivery_type == FBS_DELIVERY_TYPE_WAREHOUSE_SC:
        asset = await _warehouse_supply_qr(session, tenant_id, supply_id)
        if not _was_printed(asset):
            raise FbsOperatorFinishError(
                "local_finish_not_ready",
                message="Сначала откройте на печать общий QR поставки.",
                context={
                    "required_print": "supply_qr",
                    "asset_id": str(asset.id) if asset is not None else None,
                },
                retryable=True,
                http_status=409,
            )
    elif supply.delivery_type == FBS_DELIVERY_TYPE_PVZ:
        cargo_places_count, missing_trbx_ids = await _pvz_qr_readiness(
            session, tenant_id, supply_id
        )
        if cargo_places_count == 0 or missing_trbx_ids:
            raise FbsOperatorFinishError(
                "local_finish_not_ready",
                message="Сначала откройте на печать QR всех грузомест.",
                context={
                    "required_print": "cargo_place_qr",
                    "cargo_places_count": cargo_places_count,
                    "missing_trbx_ids": missing_trbx_ids,
                },
                retryable=True,
                http_status=409,
            )
    else:
        raise FbsOperatorFinishError(
            "wrong_delivery_type",
            context={"delivery_type": supply.delivery_type},
            http_status=409,
        )

    supply.operator_finished_at = datetime.now(tz=UTC)
    supply.operator_finished_by_user_id = user_id
    supply.operator_finish_idempotency_key = idempotency_key.strip()
    await session.flush()
    return await get_supply_workspace(session, tenant_id, supply_id)
