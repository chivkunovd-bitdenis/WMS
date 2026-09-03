"""Ошибка начисления не имеет права утащить за собой статус заказа.

WB подтвердил, что забрал заказ: статус меняется, товар списывается, резерв
снимается — и только потом считаются деньги. Если начисление уронит транзакцию
базы, откатится всё перечисленное, и заказ, физически уехавший к покупателю,
останется на складе в старой вкладке. Поэтому начисление живёт в точке
сохранения.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.db.session import SessionLocal
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.services import wb_marketplace_orders_service


@pytest.mark.asyncio
async def test_charge_failure_keeps_outer_transaction_alive(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, bool] = {}

    async def explode(session: object, order: object) -> None:
        # Проверяем именно вложенность: аварийное состояние транзакции —
        # поведение PostgreSQL, а тесты идут на SQLite, где сорвавшийся запрос
        # внешнюю транзакцию не ломает. Поэтому убеждаемся, что начисление
        # выполняется внутри точки сохранения, — на бою это и спасает статусы.
        seen["nested"] = session.in_nested_transaction()  # type: ignore[attr-defined]
        await session.execute(text("SELECT * FROM table_that_does_not_exist"))  # type: ignore[attr-defined]

    monkeypatch.setattr(
        "app.services.fbs_order_billing_service.record_fbs_order_confirmed", explode
    )

    async with SessionLocal() as session:
        tenant = Tenant(id=uuid.uuid4(), name="Savepoint", slug=f"sp-{uuid.uuid4().hex[:8]}")
        session.add(tenant)
        await session.flush()
        order = type("OrderStub", (), {"id": uuid.uuid4(), "tenant_id": tenant.id})()

        await wb_marketplace_orders_service._charge_confirmed_order(session, order)  # type: ignore[arg-type]

        assert seen["nested"] is True, "начисление обязано идти внутри точки сохранения"

        # Транзакция цела: и читать, и коммитить после сорвавшегося начисления
        # по-прежнему можно.
        seller = Seller(id=uuid.uuid4(), tenant_id=tenant.id, name="После сбоя")
        session.add(seller)
        await session.commit()
        saved = await session.scalar(select(Seller).where(Seller.id == seller.id))
        assert saved is not None
