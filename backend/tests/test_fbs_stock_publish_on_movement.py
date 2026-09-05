"""Публикация остатка ФБС привязана к движению товара, не к ручной кнопке.

Проверяем самое хрупкое место всей схемы: остаток уезжает в WB после КАЖДОГО движения,
ровно один раз на селлера, и не уезжает вовсе, когда транзакция откатилась.
Промах в любом из трёх пунктов означает, что в кабинете висит неверная цифра и WB
продаёт то, чего на складе нет.
"""

from __future__ import annotations

import time
import uuid
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.product import Product
from app.services import fbs_stock_publish_service, inventory_service
from app.services.fbs_stock_publish_service import schedule_seller_stock_publish
from tests.inventory_actor_helpers import resolve_test_actor_user_id


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
async def test_publish_lock_survives_business_commits_and_does_not_block_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy import text

    from app.db.session import engine
    from app.services import fbs_autopoll_service
    from app.services.marketplace_seller_lock_service import marketplace_seller_lock

    if engine.dialect.name != "postgresql":
        pytest.skip("Real PostgreSQL advisory locks required")
    tenant_id, seller_id = uuid.uuid4(), uuid.uuid4()
    target = SimpleNamespace(tenant_id=tenant_id, seller_id=seller_id, marketplace="ozon")
    checked = []

    async def targets(_session):
        return [target]

    async def sync(session, _target, _client):
        # A real publisher commits inside its service. The connection owning
        # the advisory lock must remain pinned throughout both commits.
        for _ in range(2):
            await session.execute(text("select 1"))
            await session.commit()
            async with SessionLocal() as contender:
                async with marketplace_seller_lock(contender, seller_id, "ozon") as acquired:
                    assert not acquired
                async with marketplace_seller_lock(
                    contender, seller_id, "ozon-delivery",
                ) as acquired:
                    assert acquired
            checked.append(True)
        return SimpleNamespace(
            bindings_processed=1, products_targeted=1, products_confirmed=1, binding_errors=0,
        )

    monkeypatch.setattr(fbs_autopoll_service, "list_marketplace_poll_targets", targets)
    monkeypatch.setattr(fbs_autopoll_service, "sync_marketplace_stocks_for_target", sync)
    await fbs_stock_publish_service.publish_seller_stocks_now(tenant_id, seller_id)
    assert checked == [True, True]
    async with (
        SessionLocal() as contender,
        marketplace_seller_lock(contender, seller_id, "ozon") as acquired,
    ):
        assert acquired, "The publication lock must be released after completion"


@pytest.mark.asyncio
async def test_movement_publishes_stock_once_per_seller(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Движение товара обязано тянуть за собой публикацию — и ровно одну на селлера.

    Бьём в `record_movement_and_adjust_balance` напрямую: это единственная точка,
    через которую вообще меняется остаток, и именно на ней висит хук публикации.
    """
    dispatched: list[str] = []
    monkeypatch.setattr(
        fbs_stock_publish_service,
        "_dispatch",
        lambda tenant_id, seller_id: dispatched.append(str(seller_id)),
    )

    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "FBS Publish On Movement",
            "slug": f"fbs-mov-{suffix}",
            "admin_email": f"fbs-mov-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    seller = await async_client.post("/sellers", headers=headers, json={"name": "Seller M"})
    seller_id = seller.json()["id"]
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WH M", "code": f"whm{suffix[-8:]}"},
    )
    warehouse_id = warehouse.json()["id"]
    location = await async_client.post(
        f"/warehouses/{warehouse_id}/locations",
        headers=headers,
        json={"code": f"CELL-{suffix[-6:]}"},
    )
    assert location.status_code in (200, 201), location.text
    location_id = uuid.UUID(location.json()["id"])

    product_ids = []
    for index in (1, 2):
        created = await async_client.post(
            "/products",
            headers=headers,
            json={
                "name": f"Product M{index}",
                "sku_code": f"FBS-M{index}-{suffix}",
                "seller_id": seller_id,
            },
        )
        assert created.status_code in (200, 201), created.text
        product_ids.append(uuid.UUID(created.json()["id"]))

    dispatched.clear()
    async with SessionLocal() as session:
        first = await session.get(Product, product_ids[0])
        assert first is not None
        tenant_id = first.tenant_id
        for product_id in product_ids:
            await inventory_service.record_movement_and_adjust_balance(
                session,
                tenant_id=tenant_id,
                product_id=product_id,
                storage_location_id=location_id,
                quantity_delta=5,
                movement_type="inbound_intake",
                actor_user_id=await resolve_test_actor_user_id(session, tenant_id),
            )
        assert dispatched == [], "публикация не должна уходить до коммита транзакции"
        await session.commit()

    # Два товара одного селлера в одной транзакции дают одну публикацию, не две.
    assert dispatched == [seller_id], f"ожидали одну публикацию на селлера, получили {dispatched}"


@pytest.mark.asyncio
async def test_schedule_collapses_duplicates_and_skips_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatched: list[tuple[str, str]] = []
    monkeypatch.setattr(
        fbs_stock_publish_service,
        "_dispatch",
        lambda tenant_id, seller_id: dispatched.append((str(tenant_id), str(seller_id))),
    )

    tenant_id = uuid.uuid4()
    seller_one = uuid.uuid4()
    seller_two = uuid.uuid4()

    async with SessionLocal() as session:
        for _ in range(5):
            schedule_seller_stock_publish(session, tenant_id, seller_one)
        schedule_seller_stock_publish(session, tenant_id, seller_two)
        # Пустой seller_id молча игнорируется: товар без селлера в WB не выгружается.
        schedule_seller_stock_publish(session, tenant_id, None)
        await session.commit()

    assert sorted(entry[1] for entry in dispatched) == sorted(
        [str(seller_one), str(seller_two)]
    ), "дубли не схлопнулись в одну публикацию на селлера"

    dispatched.clear()
    async with SessionLocal() as session:
        schedule_seller_stock_publish(session, tenant_id, seller_one)
        await session.rollback()
    assert dispatched == [], "откат транзакции не должен публиковать остаток в WB"


def test_read_only_wb_token_is_reported_distinctly() -> None:
    """WB отвечает 401 и поясняет, что ключ создан «только на чтение».

    Такой ключ читает заказы, но не может записать остаток. Смешивать это
    и «неверный токен» нельзя: селлер будет перепроверять полностью рабочий ключ.
    """
    import httpx

    from app.services.wildberries_fbs_client import map_upstream_error

    read_only = httpx.Response(
        401,
        json={
            "title": "unauthorized",
            "detail": "read-only token scope not allowed for this route",
            "status": 401,
        },
        request=httpx.Request("PUT", "https://marketplace-api.wildberries.ru/api/v3/stocks/1"),
    )
    assert map_upstream_error(read_only).code == "token_read_only"

    plain_401 = httpx.Response(
        401,
        json={"title": "unauthorized", "detail": "token is invalid"},
        request=httpx.Request("PUT", "https://marketplace-api.wildberries.ru/api/v3/stocks/1"),
    )
    assert map_upstream_error(plain_401).code == "upstream_error"


@pytest.mark.asyncio
async def test_outbound_reservation_publishes_stock(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Резерв под исходящую отгрузку тоже обязан обновлять цифру в кабинете.

    Он вычитается из доступного для ФБС, но движения товара при этом нет.
    Без публикации WB продолжал бы продавать уже обещанный кому-то товар.
    """
    from app.models.outbound_shipment import OutboundShipmentLine, OutboundShipmentRequest

    dispatched: list[str] = []
    monkeypatch.setattr(
        fbs_stock_publish_service,
        "_dispatch",
        lambda tenant_id, seller_id: dispatched.append(str(seller_id)),
    )

    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "FBS Outbound Reserve",
            "slug": f"fbs-out-{suffix}",
            "admin_email": f"fbs-out-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    seller_id = (
        await async_client.post("/sellers", headers=headers, json={"name": "Seller O"})
    ).json()["id"]
    warehouse_id = (
        await async_client.post(
            "/warehouses", headers=headers, json={"name": "WH O", "code": f"who{suffix[-8:]}"}
        )
    ).json()["id"]
    product_id = uuid.UUID(
        (
            await async_client.post(
                "/products",
                headers=headers,
                json={"name": "Product O", "sku_code": f"FBS-O-{suffix}", "seller_id": seller_id},
            )
        ).json()["id"]
    )

    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        # Статус вне OUTBOUND_RESERVE_STATUSES: резерв снимается. Это и проверяем —
        # снятие возвращает товар в доступное, и WB обязан увидеть увеличенную цифру.
        request = OutboundShipmentRequest(
            tenant_id=product.tenant_id,
            warehouse_id=uuid.UUID(warehouse_id),
            status="shipped",
        )
        session.add(request)
        await session.flush()
        line = OutboundShipmentLine(
            request_id=request.id,
            product_id=product_id,
            quantity=1,
            shipped_qty=0,
        )
        session.add(line)
        await session.flush()

        dispatched.clear()
        await inventory_service.sync_outbound_line_reservation(
            session, product.tenant_id, request, line
        )
        assert dispatched == [], "публикация не должна уходить до коммита"
        await session.commit()

    assert dispatched == [seller_id], "резерв под отгрузку не обновил остаток в WB"


def test_picking_service_allows_sorting_zone() -> None:
    """Подбор ФБС обязан принимать зону сортировки.

    Доступное для ФБС считается как storage + sorting, поэтому сортировка уезжает
    в остаток WB. Если подбор её не принимает, мы публикуем количество, которое
    оператор физически не может собрать, и заказы зависают.
    """
    from pathlib import Path

    service = Path(__file__).resolve().parents[1] / "app" / "services" / "fbs_picking_service.py"
    source = service.read_text(encoding="utf-8")
    assert "зону сортировки" not in source, (
        "в подборе снова появился запрет на зону сортировки — "
        "он противоречит формуле доступного"
    )


def test_drain_removes_finished_task_even_when_its_done_callback_has_not_run() -> None:
    """A real subprocess deadline also stops a busy loop that never yields asyncio."""
    import subprocess
    import sys
    import textwrap
    from pathlib import Path

    script = textwrap.dedent("""
        import asyncio
        from app.services import fbs_stock_publish_service as service

        async def finished():
            return None

        async def check():
            task = asyncio.create_task(finished())
            await task
            assert task.done()
            service._BACKGROUND_TASKS.add(task)
            await service.drain_background_stock_publish_tasks()
            assert not service._BACKGROUND_TASKS

        asyncio.run(check())
    """)
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("Stock-publish drain spins forever with a finished task still in its set")
    assert result.returncode == 0, result.stderr
