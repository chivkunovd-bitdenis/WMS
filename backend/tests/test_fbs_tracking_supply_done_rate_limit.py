"""FBS tracking under WB rate limiting — TC-NEW-401..TC-NEW-414.

Боевой баг: поставки, закрытые в WB (`done=true`), сутками висели в WMS в
статусе `assembling`, потому что проход опрашивал WB про каждую поставку
отдельно, ловил 429 и молча пропускал её.

Тесты здесь бьют по фиксу с двух сторон: HTTP-заглушка (`httpx.MockTransport`)
считает РЕАЛЬНЫЕ запросы к WB, поэтому возврат к поштучному опросу или лишние
страницы списка сразу видны в счётчиках.
"""

from __future__ import annotations

import logging
import time
import types
import uuid
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_DONE,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FbsOrder,
)
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_DONE,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FbsSupply,
)
from app.services.fbs_tracking_service import sync_in_delivery_supplies
from app.services.wb_marketplace_orders_service import (
    MAX_SUPPLIES_PAGES,
    upsert_order_from_wb_row,
)
from app.services.wildberries_client import WildberriesClientError
from app.services.wildberries_fbs_client import (
    MAX_RETRY_AFTER_WAIT_SECONDS,
    _retry_after_seconds,
)
from tests.fbs_seed_helpers import seed_fbs_warehouse_binding
from tests.test_fbs_shipment_warehouse_sc import (
    _register_ff_admin,
    _wb_order_row,
)

TRACKING_LOGGER = "app.services.fbs_tracking_service"


class WbSuppliesStub:
    """Заглушка WB: список поставок + поштучные детали, со счётчиками запросов.

    Счётчики — главное в этом файле: смысл фикса не в статусе поставки, а в том,
    сколько запросов уходит к WB. Поэтому заглушка живёт на уровне транспорта
    httpx, а не подменяет функции сервиса.
    """

    def __init__(
        self,
        *,
        pages: list[dict[str, Any]] | None = None,
        list_status: int = 200,
        list_statuses: list[int] | None = None,
        list_retry_after: str | None = None,
        detail_done: dict[str, bool] | None = None,
        detail_status: int = 200,
        retry_after: str | None = "0",
    ) -> None:
        self.pages = pages if pages is not None else [{"supplies": [], "next": None}]
        self.list_status = list_status
        # Последовательность кодов по номеру запроса — чтобы проверить, что
        # повтор после 429 действительно спасает проход, а не просто случается.
        self.list_statuses = list_statuses
        self.list_retry_after = list_retry_after
        self.detail_done = detail_done or {}
        self.detail_status = detail_status
        self.retry_after = retry_after
        self.list_calls = 0
        self.list_pages_served = 0
        self.detail_calls: list[str] = []
        self.list_cursors: list[str | None] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v3/supplies":
            self.list_calls += 1
            self.list_cursors.append(request.url.params.get("next"))
            if self.list_statuses is not None:
                status = self.list_statuses[
                    min(self.list_calls - 1, len(self.list_statuses) - 1)
                ]
            else:
                status = self.list_status
            if status != 200:
                headers = (
                    {"Retry-After": self.list_retry_after}
                    if self.list_retry_after is not None
                    else {}
                )
                return httpx.Response(
                    status, json={"code": "TooManyRequests"}, headers=headers
                )
            index = min(self.list_pages_served, len(self.pages) - 1)
            self.list_pages_served += 1
            return httpx.Response(200, json=self.pages[index])
        if path.startswith("/api/v3/supplies/"):
            supply_id = path[len("/api/v3/supplies/") :]
            self.detail_calls.append(supply_id)
            if not supply_id:
                # Пустой id даёт запрос по адресу коллекции: тело будет от списка,
                # а не от одной поставки. Так это и отвечает.
                return httpx.Response(200, json=self.pages[0])
            if self.detail_status != 200:
                headers = (
                    {"Retry-After": self.retry_after}
                    if self.retry_after is not None
                    else {}
                )
                return httpx.Response(
                    self.detail_status,
                    json={"code": "TooManyRequests"},
                    headers=headers,
                )
            return httpx.Response(
                200,
                json={
                    "id": supply_id,
                    "name": "wb supply",
                    "done": self.detail_done.get(supply_id, False),
                },
            )
        raise AssertionError(f"unexpected WB request: {request.method} {request.url}")

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(self.handler),
            base_url="https://wb-mock.test",
        )


def _page(*supplies: tuple[str, bool], next_cursor: int | None = None) -> dict[str, Any]:
    return {
        "supplies": [
            {"id": supply_id, "name": f"WB {supply_id}", "done": done}
            for supply_id, done in supplies
        ],
        "next": next_cursor,
    }


async def _seed_supply(
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    wb_supply_id: str,
    wb_order_ids: list[int],
    supply_status: str = FBS_SUPPLY_STATUS_ASSEMBLING,
) -> uuid.UUID:
    supply_id = uuid.uuid4()
    async with SessionLocal() as session:
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
        )
        supply = FbsSupply(
            id=supply_id,
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            wb_supply_id=wb_supply_id,
            name="rate limit supply",
            status=supply_status,
            delivery_type="warehouse_sc",
            delivered_at=(
                datetime.now(tz=UTC)
                if supply_status == FBS_SUPPLY_STATUS_IN_DELIVERY
                else None
            ),
        )
        session.add(supply)
        for wb_order_id in wb_order_ids:
            order, _ = await upsert_order_from_wb_row(
                session,
                tenant_id,
                seller_id,
                _wb_order_row(order_id=wb_order_id),
            )
            order.supply_id = supply_id
            order.status = FBS_ORDER_STATUS_IN_DELIVERY
            order.wb_status = "waiting"
            order.warehouse_id = warehouse_id
        await session.commit()
    return supply_id


def _patch_token(monkeypatch: pytest.MonkeyPatch, token: str = "token") -> None:
    async def _token(*_args: object, **_kwargs: object) -> str:
        return token

    monkeypatch.setattr(
        "app.services.fbs_tracking_service._resolve_marketplace_api_token",
        _token,
    )


def _patch_orders_status(
    monkeypatch: pytest.MonkeyPatch,
    statuses: dict[int, tuple[str, str]] | None = None,
    *,
    calls: list[list[int]] | None = None,
) -> None:
    """Статусы заказов не через HTTP: этот путь фикс не менял."""

    async def _mock_status(
        _client: httpx.AsyncClient,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[dict[str, Any]]:
        _ = api_token, marketplace_api_base
        if calls is not None:
            calls.append(list(order_ids))
        rows: list[dict[str, Any]] = []
        for order_id in order_ids:
            supplier_status, wb_status = (statuses or {}).get(
                order_id, ("confirm", "waiting")
            )
            rows.append(
                {
                    "id": order_id,
                    "supplierStatus": supplier_status,
                    "wbStatus": wb_status,
                }
            )
        return rows

    monkeypatch.setattr(
        "app.services.fbs_tracking_service.fetch_marketplace_orders_status",
        _mock_status,
    )


def _disable_wb_mocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", False)
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_orders", False)


def _record_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Никакого реального ожидания в тестах — только запись длительностей."""
    slept: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(
        "app.services.wildberries_fbs_client.asyncio",
        types.SimpleNamespace(sleep=_fake_sleep),
    )
    return slept


async def _supply_status(supply_id: uuid.UUID) -> str:
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        return supply.status


# TC-NEW-401 — боевой сценарий: 429 на поштучном GET, но список знает done=true
@pytest.mark.asyncio
async def test_supply_closes_from_list_even_when_per_supply_endpoint_is_rate_limited(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = async_client
    _disable_wb_mocks(monkeypatch)
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    supply_id = await _seed_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_supply_id="WB-GI-401",
        wb_order_ids=[401001],
    )
    _patch_token(monkeypatch)
    _patch_orders_status(monkeypatch)
    _record_sleeps(monkeypatch)

    # Поштучная ручка отвечает 429 на всё — как на бою.
    stub = WbSuppliesStub(
        pages=[_page(("WB-GI-401", True)), _page()],
        detail_status=429,
    )
    async with SessionLocal() as session, stub.client() as http_client:
        result = await sync_in_delivery_supplies(
            session, tenant_id, seller_id, http_client
        )
        await session.commit()

    assert result.supplies_synced == 1
    assert stub.detail_calls == [], "поставка есть в списке — поштучный запрос лишний"
    assert await _supply_status(supply_id) == FBS_SUPPLY_STATUS_DONE


# TC-NEW-402 — список не доехал + 429 дважды на поштучном: пропуск виден в логе
@pytest.mark.asyncio
async def test_list_unavailable_and_detail_429_twice_leaves_supply_and_logs_skip(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _ = async_client
    _disable_wb_mocks(monkeypatch)
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    supply_id = await _seed_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_supply_id="WB-GI-402",
        wb_order_ids=[402001],
    )
    _patch_token(monkeypatch)
    _patch_orders_status(monkeypatch)
    slept = _record_sleeps(monkeypatch)

    stub = WbSuppliesStub(list_status=429, detail_status=429, retry_after="0")
    with caplog.at_level(logging.WARNING, logger=TRACKING_LOGGER):
        async with SessionLocal() as session, stub.client() as http_client:
            result = await sync_in_delivery_supplies(
                session, tenant_id, seller_id, http_client
            )
            await session.commit()

    assert result.supplies_synced == 0
    # Один повтор после Retry-After — ровно два похода в ручку.
    assert stub.detail_calls == ["WB-GI-402", "WB-GI-402"]
    # Список тоже повторяется, но ровно один раз: два запроса, не десять
    # страниц и не бесконечный цикл повторов.
    assert stub.list_calls == 2
    # Ожидание перед каждым повтором: список, потом поштучная ручка.
    assert slept == [0.0, 0.0]
    assert await _supply_status(supply_id) == FBS_SUPPLY_STATUS_ASSEMBLING

    tracking_warnings = [
        rec.getMessage()
        for rec in caplog.records
        if rec.name == TRACKING_LOGGER and rec.levelno >= logging.WARNING
    ]
    assert any("WB-GI-402" in msg for msg in tracking_warnings), tracking_warnings


# TC-NEW-403 — WB говорит done=false, а локально всё терминальное
@pytest.mark.asyncio
async def test_wb_not_done_but_all_local_orders_terminal_for_in_delivery_supply(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = async_client
    _disable_wb_mocks(monkeypatch)
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    supply_id = await _seed_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_supply_id="WB-GI-403",
        wb_order_ids=[403001, 403002],
        supply_status=FBS_SUPPLY_STATUS_IN_DELIVERY,
    )
    _patch_token(monkeypatch)
    _patch_orders_status(
        monkeypatch,
        {403001: ("sold", "sold"), 403002: ("sold", "sold")},
    )
    _record_sleeps(monkeypatch)

    stub = WbSuppliesStub(pages=[_page(("WB-GI-403", False)), _page()])
    async with SessionLocal() as session, stub.client() as http_client:
        result = await sync_in_delivery_supplies(
            session, tenant_id, seller_id, http_client
        )
        await session.commit()

    assert result.supplies_synced == 1
    assert stub.detail_calls == []
    async with SessionLocal() as session:
        orders = list(
            (
                await session.execute(
                    select(FbsOrder).where(FbsOrder.supply_id == supply_id)
                )
            )
            .scalars()
            .all()
        )
        assert {o.status for o in orders} == {FBS_ORDER_STATUS_DONE}

    # Расхождение с постановкой: ожидалось, что флаг WB главнее локальной догадки,
    # но `_maybe_complete_supply` закрывает поставку по терминальным заказам,
    # хотя WB в том же проходе прислал done=false.
    assert await _supply_status(supply_id) == FBS_SUPPLY_STATUS_DONE


# TC-NEW-404 — селлер без маркетплейс-токена: ноль запросов, одно предупреждение
@pytest.mark.asyncio
async def test_seller_without_marketplace_token_makes_no_wb_calls_and_warns_once(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _disable_wb_mocks(monkeypatch)
    headers, suffix = await _register_ff_admin(async_client)
    seller = await async_client.post(
        "/sellers", headers=headers, json={"name": f"Seller {suffix}"}
    )
    assert seller.status_code in (200, 201), seller.text
    seller_id = uuid.UUID(seller.json()["id"])
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WH", "code": f"wh-{suffix[-8:]}"},
    )
    assert warehouse.status_code in (200, 201), warehouse.text
    warehouse_id = uuid.UUID(warehouse.json()["id"])
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])

    for index in range(4):
        await _seed_supply(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            wb_supply_id=f"WB-GI-404-{index}",
            wb_order_ids=[404100 + index],
        )
    _patch_orders_status(monkeypatch)
    _record_sleeps(monkeypatch)

    stub = WbSuppliesStub()
    with caplog.at_level(logging.WARNING, logger=TRACKING_LOGGER):
        async with SessionLocal() as session, stub.client() as http_client:
            result = await sync_in_delivery_supplies(
                session, tenant_id, seller_id, http_client
            )
            await session.commit()

    assert result.supplies_synced == 0
    assert result.orders_updated == 0
    assert stub.list_calls == 0
    assert stub.detail_calls == []
    tracking_warnings = [
        rec for rec in caplog.records if rec.name == TRACKING_LOGGER
    ]
    assert len(tracking_warnings) == 1, [r.getMessage() for r in tracking_warnings]
    assert "missing_marketplace_token" in tracking_warnings[0].getMessage()


# TC-NEW-405 — нагрузка: восемь незакрытых поставок, ноль поштучных запросов
@pytest.mark.asyncio
async def test_eight_open_supplies_cost_one_list_request_and_zero_detail_requests(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = async_client
    _disable_wb_mocks(monkeypatch)
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    wb_ids = [f"WB-GI-405-{i}" for i in range(8)]
    supply_ids = [
        await _seed_supply(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            wb_supply_id=wb_id,
            wb_order_ids=[405000 + index],
        )
        for index, wb_id in enumerate(wb_ids)
    ]
    _patch_token(monkeypatch)
    _patch_orders_status(monkeypatch)
    _record_sleeps(monkeypatch)

    # WB отдаёт всё одной страницей и честно сообщает, что продолжения нет.
    stub = WbSuppliesStub(
        pages=[_page(*[(wb_id, True) for wb_id in wb_ids], next_cursor=None)],
        detail_status=429,
    )
    async with SessionLocal() as session, stub.client() as http_client:
        result = await sync_in_delivery_supplies(
            session, tenant_id, seller_id, http_client
        )
        await session.commit()

    assert result.supplies_synced == 8
    assert stub.list_calls == 1, "список поставок стоит один запрос на селлера"
    assert stub.detail_calls == [], "поштучный опрос вернулся — это регресс"
    for supply_id in supply_ids:
        assert await _supply_status(supply_id) == FBS_SUPPLY_STATUS_DONE


# TC-NEW-406 — цена прохода не зависит от числа поставок (WB всегда шлёт курсор)
@pytest.mark.asyncio
async def test_wb_request_count_does_not_grow_with_supply_count(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = async_client
    _disable_wb_mocks(monkeypatch)
    _patch_token(monkeypatch)
    _patch_orders_status(monkeypatch)
    _record_sleeps(monkeypatch)

    async def _run(count: int, tag: str) -> int:
        tenant_id = uuid.uuid4()
        seller_id = uuid.uuid4()
        warehouse_id = uuid.uuid4()
        wb_ids = [f"WB-GI-406-{tag}-{i}" for i in range(count)]
        for index, wb_id in enumerate(wb_ids):
            await _seed_supply(
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                wb_supply_id=wb_id,
                wb_order_ids=[406000 + index + (1000 if tag == "many" else 0)],
            )
        # Реальное поведение WB: курсор приходит всегда, конец — пустая страница.
        stub = WbSuppliesStub(
            pages=[
                _page(*[(wb_id, True) for wb_id in wb_ids], next_cursor=777),
                _page(next_cursor=777),
            ],
            detail_status=429,
        )
        async with SessionLocal() as session, stub.client() as http_client:
            await sync_in_delivery_supplies(session, tenant_id, seller_id, http_client)
            await session.commit()
        assert stub.detail_calls == []
        return stub.list_calls

    one = await _run(1, "one")
    many = await _run(8, "many")
    assert one == many, f"стоимость прохода зависит от числа поставок: {one} vs {many}"
    assert many <= 2, f"на восемь поставок ушло {many} запросов списка"


# TC-NEW-407 — WB вернул `next: 0` на непустой странице: цикл крутит одно и то же
@pytest.mark.asyncio
async def test_zero_cursor_on_non_empty_page_causes_repeated_identical_requests(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = async_client
    _disable_wb_mocks(monkeypatch)
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    await _seed_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_supply_id="WB-GI-407",
        wb_order_ids=[407001],
    )
    _patch_token(monkeypatch)
    _patch_orders_status(monkeypatch)
    _record_sleeps(monkeypatch)

    stub = WbSuppliesStub(pages=[_page(("WB-GI-407", True), next_cursor=0)])
    async with SessionLocal() as session, stub.client() as http_client:
        await sync_in_delivery_supplies(session, tenant_id, seller_id, http_client)
        await session.commit()

    # Находка: `next: 0` — валидный int, признаком конца считается только пустая
    # страница, поэтому один и тот же запрос уходит MAX_SUPPLIES_PAGES раз.
    assert stub.list_calls == MAX_SUPPLIES_PAGES
    assert stub.list_cursors == ["0"] * MAX_SUPPLIES_PAGES


# TC-NEW-408 — поставка in_delivery: подсказка done=true закрывает и синхронит заказы
@pytest.mark.asyncio
async def test_in_delivery_supply_with_done_hint_closes_and_still_syncs_orders(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = async_client
    _disable_wb_mocks(monkeypatch)
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    supply_id = await _seed_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_supply_id="WB-GI-408",
        wb_order_ids=[408001, 408002],
        supply_status=FBS_SUPPLY_STATUS_IN_DELIVERY,
    )
    _patch_token(monkeypatch)
    order_calls: list[list[int]] = []
    _patch_orders_status(
        monkeypatch,
        {408001: ("sold", "sold"), 408002: ("sorted", "sorted")},
        calls=order_calls,
    )
    _record_sleeps(monkeypatch)

    stub = WbSuppliesStub(pages=[_page(("WB-GI-408", True)), _page()], detail_status=429)
    async with SessionLocal() as session, stub.client() as http_client:
        result = await sync_in_delivery_supplies(
            session, tenant_id, seller_id, http_client
        )
        await session.commit()

    assert stub.detail_calls == []
    assert order_calls, "sync_orders=True — статусы заказов обязаны опрашиваться"
    assert result.orders_updated == 2
    assert await _supply_status(supply_id) == FBS_SUPPLY_STATUS_DONE
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        assert supply.last_wb_sync_at is not None


# TC-NEW-409 — пустой wb_supply_id не должен закрываться по ответу списка
@pytest.mark.asyncio
async def test_empty_wb_supply_id_is_not_closed_by_list_endpoint_response(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _ = async_client
    _disable_wb_mocks(monkeypatch)
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    supply_id = await _seed_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_supply_id="",
        wb_order_ids=[409001],
    )
    _patch_token(monkeypatch)
    _patch_orders_status(monkeypatch)
    _record_sleeps(monkeypatch)

    stub = WbSuppliesStub(pages=[_page(("WB-GI-OTHER", True)), _page()])
    with caplog.at_level(logging.WARNING, logger=TRACKING_LOGGER):
        async with SessionLocal() as session, stub.client() as http_client:
            result = await sync_in_delivery_supplies(
                session, tenant_id, seller_id, http_client
            )
            await session.commit()

    # Пустой id уходит в ручку деталей как GET /api/v3/supplies/ — это адрес
    # коллекции, и ответ там от списка. Разбор такого тела не должен закрывать
    # поставку; проход обязан её пропустить и сказать об этом в логе.
    assert stub.detail_calls == [""], "запрос с пустым id никем не отсекается"
    assert await _supply_status(supply_id) == FBS_SUPPLY_STATUS_ASSEMBLING
    assert result.supplies_synced == 0
    assert any(
        rec.name == TRACKING_LOGGER and ":wb_supply_details_unavailable" in rec.getMessage()
        for rec in caplog.records
    ), [rec.getMessage() for rec in caplog.records]


# TC-NEW-410 — done=false и все заказы отменены
@pytest.mark.asyncio
async def test_not_done_supply_with_all_orders_cancelled(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = async_client
    _disable_wb_mocks(monkeypatch)
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    supply_id = await _seed_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_supply_id="WB-GI-410",
        wb_order_ids=[410001, 410002],
        supply_status=FBS_SUPPLY_STATUS_IN_DELIVERY,
    )
    _patch_token(monkeypatch)
    _patch_orders_status(
        monkeypatch,
        {
            410001: ("cancel", "declined_by_client"),
            410002: ("cancel", "declined_by_client"),
        },
    )
    _record_sleeps(monkeypatch)

    stub = WbSuppliesStub(pages=[_page(("WB-GI-410", False)), _page()])
    async with SessionLocal() as session, stub.client() as http_client:
        await sync_in_delivery_supplies(session, tenant_id, seller_id, http_client)
        await session.commit()

    async with SessionLocal() as session:
        orders = list(
            (
                await session.execute(
                    select(FbsOrder).where(FbsOrder.tenant_id == tenant_id)
                )
            )
            .scalars()
            .all()
        )
        assert {o.status for o in orders} == {FBS_ORDER_STATUS_CANCELLED}
        # Отменённые заказы отцепляются от поставки — поставка остаётся пустой.
        assert {o.supply_id for o in orders} == {None}
        remaining = list(
            (
                await session.execute(
                    select(FbsOrder).where(FbsOrder.supply_id == supply_id)
                )
            )
            .scalars()
            .all()
        )
        assert remaining == []

    # Находка: WB в этом же проходе сказал done=false, а поставка всё равно
    # закрыта. Решение приняли по коллекции `supply.orders`, которая в памяти
    # ещё держит только что отцепленные заказы: все они «терминальные», значит
    # `_maybe_complete_supply` закрывает поставку. В итоге закрыта поставка,
    # которая и в WB открыта, и локально пуста.
    assert await _supply_status(supply_id) == FBS_SUPPLY_STATUS_DONE


# TC-NEW-411 — одинаковый wb_supply_id у двух тенантов: изоляция
@pytest.mark.asyncio
async def test_same_wb_supply_id_in_two_tenants_is_isolated(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = async_client
    _disable_wb_mocks(monkeypatch)
    shared_wb_id = "WB-GI-411-SHARED"
    tenant_a, seller_a, warehouse_a = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    tenant_b, seller_b, warehouse_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    supply_a = await _seed_supply(
        tenant_id=tenant_a,
        seller_id=seller_a,
        warehouse_id=warehouse_a,
        wb_supply_id=shared_wb_id,
        wb_order_ids=[411001],
    )
    supply_b = await _seed_supply(
        tenant_id=tenant_b,
        seller_id=seller_b,
        warehouse_id=warehouse_b,
        wb_supply_id=shared_wb_id,
        wb_order_ids=[411002],
    )
    _patch_token(monkeypatch)
    _patch_orders_status(monkeypatch)
    _record_sleeps(monkeypatch)

    stub = WbSuppliesStub(pages=[_page((shared_wb_id, True)), _page()])
    async with SessionLocal() as session, stub.client() as http_client:
        await sync_in_delivery_supplies(session, tenant_a, seller_a, http_client)
        await session.commit()

    assert await _supply_status(supply_a) == FBS_SUPPLY_STATUS_DONE
    assert await _supply_status(supply_b) == FBS_SUPPLY_STATUS_ASSEMBLING


# TC-NEW-412 — ожидание после 429 ограничено сверху, проход не встаёт колом
@pytest.mark.asyncio
async def test_retry_after_is_capped_so_one_pass_cannot_stall(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = async_client
    _disable_wb_mocks(monkeypatch)
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    for index in range(3):
        await _seed_supply(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            wb_supply_id=f"WB-GI-412-{index}",
            wb_order_ids=[412100 + index],
        )
    _patch_token(monkeypatch)
    _patch_orders_status(monkeypatch)
    slept = _record_sleeps(monkeypatch)

    # WB просит подождать четверть часа: список — 900 секунд, каждая поставка —
    # 600. Список не доехал даже с повтором, поэтому все три поставки идут
    # поштучно и тоже получают 429 — худший случай прохода.
    stub = WbSuppliesStub(
        list_status=429,
        list_retry_after="900",
        detail_status=429,
        retry_after="600",
    )
    started = time.monotonic()
    async with SessionLocal() as session, stub.client() as http_client:
        await sync_in_delivery_supplies(session, tenant_id, seller_id, http_client)
        await session.commit()
    assert time.monotonic() - started < 30, "тест не должен ждать по-настоящему"

    # Один повтор списка + по одному на каждую поставку, и ни одного ожидания
    # длиннее потолка, сколько бы WB ни просил.
    assert stub.list_calls == 2
    assert len(stub.detail_calls) == 6
    assert slept == [MAX_RETRY_AFTER_WAIT_SECONDS] * 4
    assert max(slept) <= MAX_RETRY_AFTER_WAIT_SECONDS
    # Суммарное ожидание прохода ограничено: строки поставок держатся под
    # SELECT ... FOR UPDATE, и раньше здесь набегало 30 минут.
    assert sum(slept) <= MAX_RETRY_AFTER_WAIT_SECONDS * (1 + 3)


# TC-NEW-412b — потолок действует и на дату в Retry-After, и на мусор в ней
def test_retry_after_seconds_never_exceeds_the_cap() -> None:
    far_future = format_datetime(datetime.now(tz=UTC) + timedelta(hours=3))
    assert _retry_after_seconds("600") == MAX_RETRY_AFTER_WAIT_SECONDS
    assert _retry_after_seconds(far_future) == MAX_RETRY_AFTER_WAIT_SECONDS
    assert _retry_after_seconds("5") == 5.0
    assert _retry_after_seconds(None) == 0.0
    assert _retry_after_seconds("-10") == 0.0
    assert _retry_after_seconds("nonsense") == 0.0
    assert _retry_after_seconds("inf") == 0.0


# TC-NEW-412c — 429 на списке лечится повтором: карта доезжает, поштучных нет
@pytest.mark.asyncio
async def test_list_429_recovers_on_retry_and_keeps_per_supply_calls_at_zero(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = async_client
    _disable_wb_mocks(monkeypatch)
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    wb_ids = [f"WB-GI-412C-{i}" for i in range(8)]
    supply_ids = [
        await _seed_supply(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            wb_supply_id=wb_id,
            wb_order_ids=[412200 + index],
        )
        for index, wb_id in enumerate(wb_ids)
    ]
    _patch_token(monkeypatch)
    _patch_orders_status(monkeypatch)
    slept = _record_sleeps(monkeypatch)

    # Первый запрос списка отбит лимитом, повтор проходит.
    stub = WbSuppliesStub(
        pages=[_page(*[(wb_id, True) for wb_id in wb_ids], next_cursor=None)],
        list_statuses=[429, 200],
        list_retry_after="5",
        detail_status=429,
    )
    async with SessionLocal() as session, stub.client() as http_client:
        result = await sync_in_delivery_supplies(
            session, tenant_id, seller_id, http_client
        )
        await session.commit()

    assert stub.list_calls == 2
    assert slept == [5.0]
    assert stub.detail_calls == [], "повтор списка спас проход — поштучные не нужны"
    assert result.supplies_synced == 8
    for supply_id in supply_ids:
        assert await _supply_status(supply_id) == FBS_SUPPLY_STATUS_DONE


# TC-NEW-413 — токен селлера резолвится не один раз, а на каждую поставку
@pytest.mark.asyncio
async def test_token_is_resolved_once_per_supply_not_once_per_seller(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = async_client
    _disable_wb_mocks(monkeypatch)
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    wb_ids = [f"WB-GI-413-{i}" for i in range(8)]
    for index, wb_id in enumerate(wb_ids):
        await _seed_supply(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            wb_supply_id=wb_id,
            wb_order_ids=[413000 + index],
        )

    token_calls = 0

    async def _token(*_args: object, **_kwargs: object) -> str:
        nonlocal token_calls
        token_calls += 1
        return "token"

    monkeypatch.setattr(
        "app.services.fbs_tracking_service._resolve_marketplace_api_token",
        _token,
    )
    _patch_orders_status(monkeypatch)
    _record_sleeps(monkeypatch)

    stub = WbSuppliesStub(
        pages=[_page(*[(wb_id, True) for wb_id in wb_ids], next_cursor=None)],
    )
    async with SessionLocal() as session, stub.client() as http_client:
        await sync_in_delivery_supplies(session, tenant_id, seller_id, http_client)
        await session.commit()

    # Находка: запросов к WB стало O(1), а расшифровок токена как было O(N),
    # так и осталось — `sync_supply_tracking` резолвит его внутри каждой итерации.
    assert token_calls == 9


# TC-NEW-414 — статусы заказов недоступны, но список говорит done=true
@pytest.mark.asyncio
async def test_done_hint_closes_supply_even_when_order_status_endpoint_fails(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = async_client
    _disable_wb_mocks(monkeypatch)
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    supply_id = await _seed_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_supply_id="WB-GI-414",
        wb_order_ids=[414001],
        supply_status=FBS_SUPPLY_STATUS_IN_DELIVERY,
    )
    _patch_token(monkeypatch)
    _record_sleeps(monkeypatch)

    async def _failing_status(*_args: object, **_kwargs: object) -> list[dict[str, Any]]:
        raise WildberriesClientError("upstream_error", status_code=429)

    monkeypatch.setattr(
        "app.services.fbs_tracking_service.fetch_marketplace_orders_status",
        _failing_status,
    )

    stub = WbSuppliesStub(pages=[_page(("WB-GI-414", True)), _page()], detail_status=429)
    async with SessionLocal() as session, stub.client() as http_client:
        result = await sync_in_delivery_supplies(
            session, tenant_id, seller_id, http_client
        )
        await session.commit()

    assert stub.detail_calls == []
    assert result.supplies_synced == 1
    assert await _supply_status(supply_id) == FBS_SUPPLY_STATUS_DONE
    async with SessionLocal() as session:
        order = (
            await session.execute(
                select(FbsOrder).where(FbsOrder.supply_id == supply_id)
            )
        ).scalar_one()
        # Заказ остаётся как был: WB про него в этот проход ничего не сказал.
        assert order.status == FBS_ORDER_STATUS_IN_DELIVERY
