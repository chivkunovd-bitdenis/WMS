"""Оборванное создание поставки не оставляет карточку пустой.

Разбор боя 20.08.2026: WB принял девять заказов, ответ до WMS не дошёл, локальная
привязка не выполнилась — и поставка висела пустой неделю. Чинить её было нечем:
фоновая синхронизация ищет заказы по их полю supplyId, а оно заполняется только
из обхода заданий; кнопка «Добавить заказы» такие заказы не принимает.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_IN_SUPPLY,
    FbsOrder,
)
from app.models.fbs_supply import FBS_SUPPLY_STATUS_DONE, FbsSupply
from app.models.fbs_wb_operation import (
    WB_OPERATION_STATE_CONFIRMED,
    WB_OPERATION_STATE_PENDING_CONFIRMATION,
    FbsWbOperation,
)
from app.services.wildberries_client import WildberriesClientError
from tests.test_fbs_supply_from_orders import (
    _create_product,
    _create_ready_order,
    _register_ff_admin,
    _setup_seller_with_token,
    enable_wb_marketplace_supplies_mock,  # noqa: F401 — фикстура используется по имени
)

WB_SUPPLY_ID = "WB-GI-REPAIR"


async def _fake_create_supply(
    client: object,
    *,
    api_token: str,
    name: str,
    marketplace_api_base: str | None = None,
) -> dict[str, str]:
    return {"id": WB_SUPPLY_ID}


async def _prepare_order(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    *,
    wb_order_id: int,
    sku: str,
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID]:
    """Готовый к сборке заказ и селлер с токеном. Возвращает (headers, tenant_id, order_id)."""
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product = await _create_product(async_client, headers, seller_id, sku=f"{sku}-{suffix[-6:]}")
    order_id = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=wb_order_id,
    )
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", False)
    monkeypatch.setattr(
        "app.services.fbs_supply_service.create_marketplace_supply",
        _fake_create_supply,
    )
    return headers, tenant_id, order_id


async def _create_supply_request(
    async_client: AsyncClient,
    headers: dict[str, str],
    order_id: uuid.UUID,
) -> httpx.Response:
    return await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": "Repair supply",
            "order_ids": [str(order_id)],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": str(uuid.uuid4()),
        },
    )


def _patch_lost_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ровно бой: запись оборвалась по сети, читка состава тоже не дошла."""

    async def transport_error_on_add(
        client: object,
        *,
        api_token: str,
        supply_id: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> None:
        raise WildberriesClientError("transport_error")

    async def reconcile_blind(
        client: object,
        *,
        api_token: str,
        wb_supply_id: str,
        expected_wb_order_ids: set[int],
    ) -> tuple[str, set[int]]:
        return WB_OPERATION_STATE_PENDING_CONFIRMATION, set()

    monkeypatch.setattr(
        "app.services.fbs_supply_service.add_orders_to_marketplace_supply",
        transport_error_on_add,
    )
    monkeypatch.setattr(
        "app.services.fbs_supply_service.reconcile_supply_orders",
        reconcile_blind,
    )


def _patch_wb_composition(monkeypatch: pytest.MonkeyPatch, wb_order_ids: list[int]) -> None:
    async def fake_order_ids(
        client: object,
        *,
        api_token: str,
        wb_supply_id: str,
        expected_order_ids: list[int] | None = None,
    ) -> list[int]:
        assert wb_supply_id == WB_SUPPLY_ID
        return list(wb_order_ids)

    monkeypatch.setattr(
        "app.services.fbs_supply_service.fetch_wb_supply_order_ids",
        fake_order_ids,
    )


@pytest.mark.asyncio
async def test_readback_lag_keeps_composition(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Запись прошла, читка отстала — состав всё равно локально привязан."""
    headers, _tenant_id, order_id = await _prepare_order(
        async_client, monkeypatch, wb_order_id=871001, sku="repair-lag"
    )

    async def add_ok(
        client: object,
        *,
        api_token: str,
        supply_id: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> None:
        return None

    async def reconcile_lagging(
        client: object,
        *,
        api_token: str,
        wb_supply_id: str,
        expected_wb_order_ids: set[int],
    ) -> tuple[str, set[int]]:
        return WB_OPERATION_STATE_PENDING_CONFIRMATION, set()

    monkeypatch.setattr(
        "app.services.fbs_supply_service.add_orders_to_marketplace_supply", add_ok
    )
    monkeypatch.setattr(
        "app.services.fbs_supply_service.reconcile_supply_orders", reconcile_lagging
    )

    resp = await _create_supply_request(async_client, headers, order_id)
    assert resp.status_code == 504, resp.text
    assert resp.json()["detail"]["code"] == "wb_pending_confirmation"

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        # До правки здесь было None и поставка оставалась пустой навсегда.
        assert order.supply_id is not None
        assert order.status == FBS_ORDER_STATUS_IN_SUPPLY


@pytest.mark.asyncio
async def test_partial_readback_binds_confirmed_orders(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Связь оборвалась, но читка показала заказ в поставке — он привязывается.

    Боевая ветка отвечает на такой случай успехом с пометкой частичного подтверждения:
    состав в WMS уже верный, и оператору незачем видеть ошибку.
    """
    headers, _tenant_id, order_id = await _prepare_order(
        async_client, monkeypatch, wb_order_id=871002, sku="repair-part"
    )

    async def transport_error_on_add(
        client: object,
        *,
        api_token: str,
        supply_id: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> None:
        raise WildberriesClientError("transport_error")

    async def reconcile_partial(
        client: object,
        *,
        api_token: str,
        wb_supply_id: str,
        expected_wb_order_ids: set[int],
    ) -> tuple[str, set[int]]:
        return WB_OPERATION_STATE_PENDING_CONFIRMATION, {871002}

    monkeypatch.setattr(
        "app.services.fbs_supply_service.add_orders_to_marketplace_supply",
        transport_error_on_add,
    )
    monkeypatch.setattr(
        "app.services.fbs_supply_service.reconcile_supply_orders", reconcile_partial
    )

    resp = await _create_supply_request(async_client, headers, order_id)
    assert resp.status_code == 201, resp.text
    accepted = resp.json()["partial_rejection"]["accepted_orders"]
    assert [item["wb_order_id"] for item in accepted] == [871002]

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.supply_id is not None
        assert order.status == FBS_ORDER_STATUS_IN_SUPPLY


@pytest.mark.asyncio
async def test_repair_endpoint_restores_composition(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ответ WB потерян целиком: состав добирается прямым запросом к WB."""
    headers, _tenant_id, order_id = await _prepare_order(
        async_client, monkeypatch, wb_order_id=871003, sku="repair-ep"
    )
    _patch_lost_response(monkeypatch)

    resp = await _create_supply_request(async_client, headers, order_id)
    assert resp.status_code == 504, resp.text
    assert resp.json()["detail"]["code"] == "wb_timeout"

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None and order.supply_id is None
        supply = await session.scalar(
            select(FbsSupply).where(FbsSupply.wb_supply_id == WB_SUPPLY_ID)
        )
        assert supply is not None
        supply_id = supply.id

    _patch_wb_composition(monkeypatch, [871003])
    repaired = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/repair-from-wb", headers=headers
    )
    assert repaired.status_code == 200, repaired.text
    assert len(repaired.json()["orders"]) == 1

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.supply_id == supply_id
        assert order.status == FBS_ORDER_STATUS_IN_SUPPLY
        # Номер поставки WB теперь есть и у заказа — штатная привязка его тоже видит.
        assert order.wb_supply_id == WB_SUPPLY_ID
        operation = await session.scalar(
            select(FbsWbOperation).where(FbsWbOperation.local_entity_id == supply_id)
        )
        assert operation is not None
        assert operation.state == WB_OPERATION_STATE_CONFIRMED


@pytest.mark.asyncio
async def test_repair_skips_cancelled_order(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Отменённый покупателем заказ в поставку не возвращается."""
    headers, _tenant_id, order_id = await _prepare_order(
        async_client, monkeypatch, wb_order_id=871004, sku="repair-cancel"
    )
    _patch_lost_response(monkeypatch)
    resp = await _create_supply_request(async_client, headers, order_id)
    assert resp.status_code == 504, resp.text

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        order.status = FBS_ORDER_STATUS_CANCELLED
        supply = await session.scalar(
            select(FbsSupply).where(FbsSupply.wb_supply_id == WB_SUPPLY_ID)
        )
        assert supply is not None
        supply_id = supply.id
        await session.commit()

    _patch_wb_composition(monkeypatch, [871004])
    repaired = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/repair-from-wb", headers=headers
    )
    assert repaired.status_code == 200, repaired.text
    assert repaired.json()["orders"] == []

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.supply_id is None
        assert order.status == FBS_ORDER_STATUS_CANCELLED


@pytest.mark.asyncio
async def test_repair_rejects_shipped_supply(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Отгруженную поставку задним числом не переписываем."""
    headers, _tenant_id, order_id = await _prepare_order(
        async_client, monkeypatch, wb_order_id=871005, sku="repair-done"
    )
    _patch_lost_response(monkeypatch)
    resp = await _create_supply_request(async_client, headers, order_id)
    assert resp.status_code == 504, resp.text

    async with SessionLocal() as session:
        supply = await session.scalar(
            select(FbsSupply).where(FbsSupply.wb_supply_id == WB_SUPPLY_ID)
        )
        assert supply is not None
        supply.status = FBS_SUPPLY_STATUS_DONE
        supply_id = supply.id
        await session.commit()

    _patch_wb_composition(monkeypatch, [871005])
    repaired = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/repair-from-wb", headers=headers
    )
    assert repaired.status_code == 409, repaired.text
    assert repaired.json()["detail"]["code"] == "supply_not_repairable"


@pytest.mark.asyncio
async def test_autopoll_repairs_pending_supply(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Фоновый цикл сам добирает состав — оператору не нужно ничего нажимать."""
    from app.services.fbs_supply_service import repair_pending_supplies_for_seller

    headers, tenant_id, order_id = await _prepare_order(
        async_client, monkeypatch, wb_order_id=871006, sku="repair-auto"
    )
    _patch_lost_response(monkeypatch)
    resp = await _create_supply_request(async_client, headers, order_id)
    assert resp.status_code == 504, resp.text

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None and order.supply_id is None
        seller_id = order.seller_id

    _patch_wb_composition(monkeypatch, [871006])
    async with SessionLocal() as session, httpx.AsyncClient() as http_client:
        result: dict[str, Any] = await repair_pending_supplies_for_seller(
            session,
            tenant_id,
            seller_id,
            http_client=http_client,
        )
    assert result == {"supplies_scanned": 1, "orders_linked": 1}

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.supply_id is not None
        assert order.status == FBS_ORDER_STATUS_IN_SUPPLY
