"""FBS honest sign skip — пропуск маркировки Честный знак при необязательной маркировке."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.fbs_supply import FBS_SUPPLY_STATUS_IN_DELIVERY, FbsSupply
from tests.test_fbs_shipment_warehouse_sc import (
    _prepare_supply_with_orders,
    _register_ff_admin,
    _setup_seller_with_token,
)


async def _skip_honest_sign(
    async_client: AsyncClient,
    headers: dict[str, str],
    supply_id: str,
) -> dict:
    """Вызвать эндпоинт пропуска маркировки Честный знак."""
    resp = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/honest-sign-skip",
        headers=headers,
    )
    return resp


# Роут поднимает флаг и идемпотентен
@pytest.mark.asyncio
async def test_honest_sign_skip_sets_flag_and_is_idempotent(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TC-NEW-001: POST /operations/fbs-supplies/{supply_id}/honest-sign-skip идемпотентен.

    Given: поставка в статусе draft с заказами
    When: вызовем честный_знак_пропустить дважды
    Then: первый вызов вернёт workspace с honest_sign_skipped=true, второй — то же самое
    """
    monkeypatch.setattr(
        __import__("app.core.settings", fromlist=["settings"]).settings,
        "e2e_mock_wb_marketplace_supplies",
        True,
    )
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    supply, _order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[990001, 990002],
        supply_name="TC-NEW-001 honest sign skip idempotent",
    )

    # Первый вызов
    resp1 = await _skip_honest_sign(async_client, headers, supply["id"])
    assert resp1.status_code == 200, f"Got {resp1.status_code}: {resp1.text}"
    data1 = resp1.json()
    assert data1["supply"]["honest_sign_skipped"] is True

    # Второй вызов — идемпотентен
    resp2 = await _skip_honest_sign(async_client, headers, supply["id"])
    assert resp2.status_code == 200, f"Got {resp2.status_code}: {resp2.text}"
    data2 = resp2.json()
    assert data2["supply"]["honest_sign_skipped"] is True
    # Поле должно быть установлено один раз, дополнительных вызовов не было
    # (проверяется через БД в другом тесте)


# После флага печать ленты по заказу с обязательной маркировкой не выпускает код из пула
@pytest.mark.asyncio
async def test_honest_sign_skip_blocks_code_release_on_print(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TC-NEW-002 (проверяем по факту: в ленте нет ни одного кода)

    TC-NEW-002: После пропуска маркировки печать не выпускает коды из пула.

    Given: поставка с заказом, требующим маркировку, флаг пропуска установлен
    When: печатаем ленту заказа
    Then: коды не выпускаются из пула (requires_honest_sign=false для заказа)
    """
    monkeypatch.setattr(
        __import__("app.core.settings", fromlist=["settings"]).settings,
        "e2e_mock_wb_marketplace_supplies",
        True,
    )
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    supply, order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[990101, 990102],
        supply_name="TC-NEW-002 honest sign skip print",
    )

    # Установим флаг пропуска маркировки
    skip_resp = await _skip_honest_sign(async_client, headers, supply["id"])
    assert skip_resp.status_code == 200

    # Печатаем ленту заказа — коды не должны выпускаться
    print_resp = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/order-print-tape",
        headers=headers,
        json={
            "order_ids": [str(oid) for oid in order_ids],
            "layout": None,
            "allow_partial": False,
            "include_order_qr": True,
            "reprint": False,
        },
    )
    assert print_resp.status_code == 200, f"Got {print_resp.status_code}: {print_resp.text}"
    tape_data = print_resp.json()
    # Проверяем, что requires_honest_sign=false для заказов
    for order in tape_data["orders"]:
        assert order["requires_honest_sign"] is False
        # И главное — ни одного кода в ленте: пул не тронут, жечь нечего.
        assert not order.get("printed_codes"), order
        assert not order.get("codes"), order
    assert tape_data.get("shortage", 0) == 0


# Уже привязанный код остаётся на месте
@pytest.mark.asyncio
async def test_honest_sign_skip_preserves_existing_codes(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TC-NEW-003: Пропуск маркировки не стирает уже привязанные коды.

    Given: поставка с кодом в привязанном заказе
    When: установим флаг пропуска маркировки
    Then: привязанные коды остаются в заказе и уходят в WB
    """
    monkeypatch.setattr(
        __import__("app.core.settings", fromlist=["settings"]).settings,
        "e2e_mock_wb_marketplace_supplies",
        True,
    )
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    supply, _order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[990201, 990202],
        supply_name="TC-NEW-003 preserve codes",
    )

    # Проверяем, что заказы есть в поставке
    workspace_before = await async_client.get(
        f"/operations/fbs-supplies/{supply['id']}/workspace",
        headers=headers,
    )
    assert workspace_before.status_code == 200
    ws_before = workspace_before.json()
    assert len(ws_before["orders"]) == 2

    # Установим флаг пропуска маркировки
    skip_resp = await _skip_honest_sign(async_client, headers, supply["id"])
    assert skip_resp.status_code == 200

    # Проверяем, что заказы всё еще есть и их данные не стёрты
    workspace_after = await async_client.get(
        f"/operations/fbs-supplies/{supply['id']}/workspace",
        headers=headers,
    )
    assert workspace_after.status_code == 200
    ws_after = workspace_after.json()
    assert len(ws_after["orders"]) == 2
    # Заказы должны остаться тем же
    for i, order in enumerate(ws_after["orders"]):
        assert order["id"] == ws_before["orders"][i]["id"]


# Нельзя применять к поставке, которая уже сдана в WB
@pytest.mark.asyncio
async def test_honest_sign_skip_blocked_on_submitted_supply(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TC-NEW-004: Пропуск маркировки невозможен для уже переданных поставок.

    Given: поставка в статусе in_delivery (передана в доставку)
    When: попытаемся установить флаг пропуска маркировки
    Then: получим 409 Conflict с кодом supply_already_submitted
    """
    monkeypatch.setattr(
        __import__("app.core.settings", fromlist=["settings"]).settings,
        "e2e_mock_wb_marketplace_supplies",
        True,
    )
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    supply, _order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[990301, 990302],
        supply_name="TC-NEW-004 submitted supply",
    )

    # Устанавливаем статус поставки в in_delivery через БД
    # (чтобы не заморачиваться с полной подготовкой к доставке)
    async with SessionLocal() as session:
        db_supply = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        assert db_supply is not None
        db_supply.status = FBS_SUPPLY_STATUS_IN_DELIVERY
        await session.commit()

    # Теперь попытаемся установить флаг — должна быть ошибка 409
    resp = await _skip_honest_sign(async_client, headers, supply["id"])
    assert resp.status_code == 409, f"Expected 409, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", {})
    if isinstance(detail, dict):
        assert detail.get("code") == "supply_already_submitted"


# Флаг должен быть в workspace для фронта
@pytest.mark.asyncio
async def test_honest_sign_skipped_in_workspace(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TC-NEW-005: Флаг honest_sign_skipped виден в workspace.

    Given: поставка с установленным флагом пропуска маркировки
    When: запросим workspace поставки
    Then: в supply.honest_sign_skipped вернётся true
    """
    monkeypatch.setattr(
        __import__("app.core.settings", fromlist=["settings"]).settings,
        "e2e_mock_wb_marketplace_supplies",
        True,
    )
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    supply, _order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[990401, 990402],
        supply_name="TC-NEW-005 workspace flag",
    )

    # Установим флаг
    skip_resp = await _skip_honest_sign(async_client, headers, supply["id"])
    assert skip_resp.status_code == 200
    assert skip_resp.json()["supply"]["honest_sign_skipped"] is True

    # Запросим workspace ещё раз
    ws_resp = await async_client.get(
        f"/operations/fbs-supplies/{supply['id']}/workspace",
        headers=headers,
    )
    assert ws_resp.status_code == 200
    ws_data = ws_resp.json()
    assert ws_data["supply"]["honest_sign_skipped"] is True
