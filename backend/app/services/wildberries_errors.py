"""Shared Wildberries client exceptions."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

WB_RESPONSE_BODY_LOG_LIMIT = 500

# Wildberries отвечает по-английски и без кодов ошибок, пригодных для показа.
# До 01.09.2026 его ответ уходил оператору как есть: в диалоге передачи склад
# видел «Wildberries ответил: Supply not found» и не понимал ни что случилось,
# ни что делать. Ключ — приведённый к нижнему регистру фрагмент ответа WB.
_WB_MESSAGE_TRANSLATIONS: tuple[tuple[str, str], ...] = (
    (
        "supply not found",
        "Wildberries не нашёл эту поставку у себя. Скорее всего её удалили или "
        "закрыли в кабинете продавца — обновите страницу и проверьте состав.",
    ),
    (
        "fix them to dispatch items",
        "Wildberries ещё обрабатывает поставку. Повторите передачу через минуту.",
    ),
    (
        "metavalidationfail",
        "Wildberries отклонил данные маркировки. Проверьте Честный знак у указанных "
        "заказов и повторите передачу.",
    ),
    (
        "uinbadstatus",
        "Wildberries отклонил код маркировки: статус КИЗ не позволяет передать заказ. "
        "Проверьте или замените КИЗ.",
    ),
    (
        "mandatory mark",
        "Wildberries требует обязательную маркировку. Проверьте Честный знак у "
        "указанных заказов.",
    ),
    (
        "supply is already delivered",
        "Wildberries считает эту поставку уже сданной. Повторно передавать её не нужно.",
    ),
    (
        "supply has no orders",
        "В поставке на стороне Wildberries нет заказов — добавьте заказы и повторите.",
    ),
    (
        "order not found",
        "Wildberries не нашёл заказ из состава поставки. Обновите состав и повторите.",
    ),
    (
        "unauthorized",
        "Wildberries не принял ключ продавца. Проверьте API-ключ в карточке селлера.",
    ),
    (
        "forbidden",
        "У ключа продавца нет прав на эту операцию. Нужен ключ с доступом к «Маркетплейсу».",
    ),
    (
        "too many requests",
        "Wildberries временно ограничил частоту запросов. Повторите через минуту.",
    ),
    (
        "internal server error",
        "На стороне Wildberries сбой. Повторите операцию через несколько минут.",
    ),
    (
        "trbx",
        "Wildberries отклонил работу с грузоместами. Проверьте короба поставки и повторите.",
    ),
)


def translate_wb_message(raw: str | None) -> str | None:
    """Переводит ответ Wildberries на человеческий русский.

    Возвращает None, если знакомого фрагмента не нашлось — тогда вызывающий код
    показывает исходный текст, но уже с явной пометкой, что это слова WB.
    """
    if not raw:
        return None
    lowered = raw.lower()
    for needle, translated in _WB_MESSAGE_TRANSLATIONS:
        if needle in lowered:
            return translated
    return None


class WildberriesClientError(Exception):
    def __init__(
        self,
        code: str,
        *,
        status_code: int | None = None,
        endpoint: str | None = None,
        response_body: str | None = None,
        message: str | None = None,
    ) -> None:
        self.code = code
        self.status_code = status_code
        self.endpoint = endpoint
        self.response_body = response_body
        self.message = message
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class MetaValidationFailItem:
    order_id: int | None
    key: str
    value: str | None
    decision: str
    reason: str | None = None


class WildberriesBusinessError(WildberriesClientError):
    """409 and other parsed WB business rejections (safe codes, no token leakage)."""

    def __init__(
        self,
        code: str,
        *,
        status_code: int | None = None,
        wb_code: str | None = None,
        message: str | None = None,
        meta_validation: list[MetaValidationFailItem] | None = None,
        endpoint: str | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(
            code,
            status_code=status_code,
            endpoint=endpoint,
            response_body=response_body,
            message=message,
        )
        self.wb_code = wb_code
        self.message = message
        self.meta_validation: tuple[MetaValidationFailItem, ...] = tuple(
            meta_validation or ()
        )


def truncate_wb_response_body(body: str | None) -> str | None:
    if body is None:
        return None
    text = body.replace("\x00", "").strip()
    if not text:
        return None
    return text[:WB_RESPONSE_BODY_LOG_LIMIT]


def wb_error_ref() -> str:
    return f"wb-{uuid.uuid4()}"


def _message_from_response_body(body: str | None) -> str | None:
    snippet = truncate_wb_response_body(body)
    if snippet is None:
        return None
    try:
        data = json.loads(snippet)
    except json.JSONDecodeError:
        return snippet
    if isinstance(data, dict):
        for key in ("message", "detail", "errorText", "error"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return truncate_wb_response_body(value)
    return snippet


def wb_operator_message(exc: WildberriesClientError) -> str:
    if isinstance(exc.message, str) and exc.message.strip() and exc.message != exc.code:
        own = exc.message.strip()
        return translate_wb_message(own) or own
    body_message = _message_from_response_body(exc.response_body)
    if body_message:
        translated = translate_wb_message(body_message)
        if translated:
            return translated
        if exc.status_code == 401:
            return "Wildberries не принял ключ продавца. Проверьте API-ключ в карточке селлера."
        if exc.status_code == 403:
            return (
                "У ключа продавца нет прав на эту операцию. "
                "Нужен ключ с доступом к «Маркетплейсу»."
            )
        if exc.status_code == 429:
            return "Wildberries временно ограничил частоту запросов. Повторите через минуту."
        if exc.status_code is not None and exc.status_code >= 500:
            return "На стороне Wildberries сбой. Повторите операцию через несколько минут."
        return "Wildberries отклонил операцию. Подробности ответа сохранены в журнале."
    if exc.status_code == 401:
        return "Wildberries не принял ключ продавца. Проверьте API-ключ в карточке селлера."
    if exc.status_code == 403:
        return "У ключа продавца нет прав на эту операцию. Нужен ключ с доступом к «Маркетплейсу»."
    if exc.status_code == 429:
        return "Wildberries временно ограничил частоту запросов. Повторите через минуту."
    if exc.status_code is not None and exc.status_code >= 500:
        return "На стороне Wildberries сбой. Повторите операцию через несколько минут."
    if exc.code == "token_read_only":
        return "Ключ Wildberries создан в режиме только для чтения; нужен ключ с правом записи."
    if exc.code == "transport_error":
        return "Wildberries не ответил вовремя; повторите операцию или проверьте связь."
    return "Wildberries отклонил операцию; проверьте детали ошибки в журнале."


def wb_error_context(
    exc: WildberriesClientError,
    *,
    ref: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {"ref": ref or wb_error_ref()}
    if exc.status_code is not None:
        context["wb_status_code"] = exc.status_code
    if exc.endpoint:
        context["wb_endpoint"] = exc.endpoint
    response_body = truncate_wb_response_body(exc.response_body)
    if response_body:
        context["wb_response_body"] = response_body
    if extra:
        context.update(extra)
    return context


def log_wb_client_error(
    logger: logging.Logger,
    event: str,
    exc: WildberriesClientError,
    *,
    tenant_id: uuid.UUID | None = None,
    seller_id: uuid.UUID | None = None,
    local_entity_id: uuid.UUID | str | None = None,
    wb_object_id: str | int | None = None,
    endpoint: str | None = None,
    ref: str | None = None,
    level: int = logging.ERROR,
) -> None:
    logger.log(
        level,
        (
            "%s ref=%s code=%s wb_status=%s wb_endpoint=%s tenant_id=%s "
            "seller_id=%s local_entity_id=%s wb_object_id=%s wb_response_body=%r"
        ),
        event,
        ref,
        exc.code,
        exc.status_code,
        endpoint or exc.endpoint,
        tenant_id,
        seller_id,
        local_entity_id,
        wb_object_id,
        truncate_wb_response_body(exc.response_body),
    )
