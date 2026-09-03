"""Операция над документом Ozon не должна уходить в кабинет Wildberries.

Ревизия 03.09.2026 нашла четыре таких пути. Ни один не проверял маркетплейс, а
у заказа Ozon `wb_order_id` — синтезированный отрицательный хеш от номера
отправления: запрос уходил в чужой кабинет с заведомо несуществующим номером.
Сегодня это не стреляет (на бою все заказы вайлдберрисовские), поэтому здесь
проверяется именно намерение — что защита стоит и что она не задевает WB.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest

from app.services.marketplace_scope import is_wildberries, wrong_marketplace_message


@dataclass
class _Doc:
    marketplace: str


def test_wildberries_document_passes() -> None:
    assert is_wildberries(_Doc("wb")) is True


def test_ozon_document_is_not_wildberries() -> None:
    assert is_wildberries(_Doc("ozon")) is False


def test_missing_document_is_not_wildberries() -> None:
    assert is_wildberries(None) is False


def test_message_names_the_marketplace_and_the_operation() -> None:
    message = wrong_marketplace_message(_Doc("ozon"), "Отмена заказа")
    assert "Ozon" in message
    assert "Отмена заказа" in message
    assert "чужой кабинет" in message


def _stub_session(order: object) -> object:
    class _Result:
        def scalar_one_or_none(self) -> object:
            return order

    class _Session:
        async def execute(self, *_args: object, **_kwargs: object) -> _Result:
            return _Result()

    return _Session()


@pytest.mark.asyncio
async def test_cancel_refuses_an_unknown_marketplace_before_touching_wildberries() -> None:
    """Заказ маркетплейса, которого мы не умеем, останавливается до вызова к WB."""
    from app.models.fbs_order import FbsOrder
    from app.services.fbs_cancellation_service import FbsCancellationError, cancel_order

    order = FbsOrder(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        seller_id=uuid.uuid4(),
        marketplace="yandex",
        wb_order_id=-4823094820938,
        status="new",
    )

    with pytest.raises(FbsCancellationError) as exc:
        await cancel_order(
            _stub_session(order),  # type: ignore[arg-type]
            order.tenant_id,
            order.id,
            None,  # type: ignore[arg-type]
            actor_user_id=None,
        )
    assert exc.value.code == "marketplace_not_supported"


@pytest.mark.asyncio
async def test_cancel_of_an_ozon_order_never_runs_on_the_local_fake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Выключенный боевой транспорт — это отказ, а не «Ozon не подтвердил отмену».

    На локальном фейке ответ пустой, `result` не `true`, и оператор увидел бы
    сообщение про Ozon, который на самом деле ничего не отвечал. Отмена
    необратима, поэтому в таком состоянии её просто нельзя начинать.
    """
    from app.core.settings import settings
    from app.models.fbs_order import FbsOrder
    from app.services.fbs_cancellation_service import FbsCancellationError, cancel_order

    monkeypatch.setattr(settings, "ozon_live_api_enabled", False)
    order = FbsOrder(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        seller_id=uuid.uuid4(),
        marketplace="ozon",
        external_order_id="12345-0001-1",
        wb_order_id=-4823094820938,
        status="new",
    )

    with pytest.raises(FbsCancellationError) as exc:
        await cancel_order(
            _stub_session(order),  # type: ignore[arg-type]
            order.tenant_id,
            order.id,
            None,  # type: ignore[arg-type]
            actor_user_id=None,
        )
    assert exc.value.code == "ozon_live_cancel_blocked"


def test_ozon_order_shows_its_own_number_not_the_synthetic_hash() -> None:
    """У заказа Ozon показываем номер отправления, а не отрицательный хеш.

    В колонке `wb_order_id` у Ozon лежит `-(hash(posting_number))` — по нему
    заказ не найти ни у нас, ни в кабинете.
    """
    from app.services.marketplace_scope import order_display_number

    @dataclass
    class _Order:
        marketplace: str
        wb_order_id: int
        external_order_id: str | None

    ozon = _Order("ozon", -4823094820938, "12345-0001-1")
    assert order_display_number(ozon) == "12345-0001-1"

    wb = _Order("wb", 987654321, None)
    assert order_display_number(wb) == "987654321"

    # Заказ Ozon без сохранённого номера отправления не должен ронять экран.
    broken = _Order("ozon", -1, None)
    assert order_display_number(broken) == "-1"


def test_status_labels_name_the_right_marketplace() -> None:
    """«ВБ получил» не должно стоять над заказом Ozon."""
    from app.services.billing_seller_report_service import _confirmed_label, _handed_label

    assert _confirmed_label("wb") == "ВБ получил"
    assert _confirmed_label(None) == "ВБ получил"
    assert _confirmed_label("ozon") == "Ozon получил"
    assert _handed_label("wb") == "Передан ВБ"
    assert _handed_label("ozon") == "Передан Ozon"
