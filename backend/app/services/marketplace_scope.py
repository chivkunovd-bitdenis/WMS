"""Проверка, что операция обращается к тому маркетплейсу, которому принадлежит документ.

Зачем это отдельным модулем. Модуль FBS писался под Wildberries, и вызовы к нему
раскиданы по общим сервисам — поставка, грузоместа, отмена заказа, отвязка кода
маркировки. Когда рядом появился Ozon, у заказа и поставки завели поле
`marketplace`, но развилку добавили не везде. Ревизия 03.09.2026 нашла четыре
места, где операция над озоновским документом уходила настоящим HTTP-запросом в
чужой вайлдберрисовский кабинет — с отрицательным числом вместо номера заказа
(у заказов Ozon `wb_order_id` синтезируется хешем от номера отправления).

Сегодня это не стреляет: на бою все заказы и поставки вайлдберрисовские. Мина
взводится в тот день, когда появится первый заказ Ozon, — то есть ровно тогда,
когда за ней никто не будет следить.

Поле `marketplace` объявлено `NOT NULL` со значением по умолчанию `wb` и у заказа,
и у поставки, поэтому проверка не может случайно запереть живой процесс: пустого
значения в базе не бывает.
"""

from __future__ import annotations

from typing import Protocol

MARKETPLACE_WB = "wb"
MARKETPLACE_OZON = "ozon"


class HasMarketplace(Protocol):
    marketplace: str


def is_wildberries(entity: HasMarketplace | object | None) -> bool:
    """Принадлежит ли документ Wildberries."""
    if entity is None:
        return False
    return getattr(entity, "marketplace", MARKETPLACE_WB) == MARKETPLACE_WB


def wrong_marketplace_message(entity: HasMarketplace | object | None, operation: str) -> str:
    """Текст оператору: почему операция не выполнена.

    Оператору незачем знать про устройство интеграции — ему нужно понять, что
    произошло и что делать. Поэтому называем маркетплейс документа и операцию,
    а не внутренние коды.
    """
    marketplace = getattr(entity, "marketplace", None) or "неизвестный маркетплейс"
    names = {"wb": "Wildberries", "ozon": "Ozon"}
    return (
        f"{operation} для маркетплейса «{names.get(marketplace, marketplace)}» пока не поддержана. "
        "Операция остановлена, чтобы запрос не ушёл в чужой кабинет."
    )


MARKETPLACE_NAMES = {"wb": "WB", "ozon": "Ozon"}


def marketplace_name(entity: HasMarketplace | object | None) -> str:
    """Короткое имя маркетплейса для подписей оператору."""
    marketplace = getattr(entity, "marketplace", None) or MARKETPLACE_WB
    return MARKETPLACE_NAMES.get(str(marketplace), str(marketplace))


def order_display_number(order: object) -> str:
    """Номер заказа так, как его называет его собственный маркетплейс.

    У Wildberries номер — это число, и оно лежит в `wb_order_id`. У Ozon номер
    отправления строковый («12345-0001-1»), а колонка `wb_order_id` осталась от
    времён, когда маркетплейс был один: туда пишется синтезированный
    отрицательный хеш, чтобы не занимать чужое пространство идентификаторов.
    Показывать этот хеш оператору бессмысленно — по нему ничего не найти ни у
    нас, ни в кабинете.
    """
    external = getattr(order, "external_order_id", None)
    if not is_wildberries(order) and external:
        return str(external)
    return str(getattr(order, "wb_order_id", "") or "")
