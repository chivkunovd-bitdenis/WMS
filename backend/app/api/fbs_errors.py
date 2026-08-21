# ruff: noqa: RUF001
"""Stable FBS HTTP error envelope for operator-facing contract endpoints.

Wire shape (BACKEND_CONTRACT.md §1):

    {"detail": {"code": "...", "message": "...", "context": {}, "retryable": false}}

FastAPI wraps the dict passed to ``HTTPException(detail=...)`` as the top-level
``detail`` field, so helpers return the *inner* object only.
"""

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import HTTPException

# RU operator messages — keep in sync with tasks/fbs-operator-flow/ERROR_CATALOG_RU.md
FBS_ERROR_MESSAGES_RU: dict[str, str] = {
    "empty_order_set": "Не выбран ни один заказ.",
    "missing_idempotency_key": "Не передан ключ идемпотентности.",
    "supply_empty": "Поставка без заказов.",
    "invalid_delivery_type": "Недопустимый тип доставки.",
    "seller_not_found": "Селлер не найден.",
    "warehouse_not_found": "Склад не найден.",
    "missing_marketplace_token": "Нет токена WB Marketplace.",
    "order_not_found": "Заказ не найден.",
    "order_already_in_supply": "Заказ уже в другой поставке.",
    "order_bad_status": "Заказ в недопустимом статусе.",
    "order_warehouse_unmapped": "Склад WB заказа не привязан к WMS.",
    "order_warehouse_mismatch": "Склад заказа не совпадает с поставкой.",
    "supply_not_editable": "Поставку нельзя изменить.",
    "supply_not_found": "Поставка не найдена.",
    "order_incompatible": "Заказ нельзя добавить в выбранную поставку.",
    "idempotency_key_reused": "Ключ идемпотентности уже использован с другими параметрами.",
    "wb_invalid_response": "Некорректный ответ Wildberries.",
    "wb_timeout": "Таймаут при обращении к Wildberries; результат неизвестен.",
    "wb_pending_confirmation": "Wildberries не подтвердил результат; нужна сверка.",
    "operation_in_progress": "Операция уже выполняется.",
    "wb_stickers_incomplete": "Wildberries вернул неполный набор стикеров.",
    "wrong_location": "Ячейка не найдена или не подходит для подбора.",
    "wrong_product": "Товар не найден по штрихкоду.",
    "seller_stock_mismatch": "Товар принадлежит другому селлеру.",
    "product_not_in_supply": "Товар не входит в состав поставки или уже подобран.",
    "order_already_picked": "Заказ уже подобран.",
    "insufficient_unpacked": "Недостаточно неупакованного остатка.",
    "insufficient_packaging_stock": "Недостаточно остатка товара в ячейке упаковки.",
    "pick_undo_not_allowed": "Отмена подбора после упаковки запрещена.",
    "order_not_picked": "Заказ ещё не подобран.",
    "trbx_not_found": "Грузоместо не найдено.",
    "wrong_delivery_type": "Неверный тип доставки для этой операции.",
    "invalid_status_transition": "Недопустимый переход статуса.",
    "order_not_in_supply": "Заказ не входит в эту поставку.",
    "order_product_mismatch": "Товар не совпадает с заказом.",
    "order_already_packed": "Заказ уже упакован.",
    "no_eligible_order": "Нет подходящего заказа для упаковки.",
    "invalid_qty": "Недопустимое количество.",
    "invalid_kind": "Неизвестный тип идентификатора или актива.",
    "empty_value": "Пустое значение.",
    "kind_not_required": "Этот идентификатор не требуется для заказа.",
    "gs_separator_lost": (
        "Разделители кода потеряны при вводе, а структуру не удалось "
        "восстановить — отсканируйте Честный знак заново целиком."
    ),
    "order_marking_frozen": "Маркировка заморожена.",
    "duplicate_kiz": "КИЗ уже использован.",
    "cross_seller_code": "Код принадлежит другому селлеру.",
    "code_product_mismatch": "Код не соответствует товару.",
    "kind_already_assigned": "Идентификатор уже назначен.",
    "marking_code_already_assigned": "Код маркировки уже назначен другому заказу.",
    "meta_validation_fail": "Wildberries отклонил метаданные.",
    "sgtin_missing_gs": (
        "КИЗ без служебного GS-разделителя после серийного номера — Wildberries его не "
        "примет. Запустите восстановление пула (python -m app.cli."
        "restore_truncated_marking_cis) или отсканируйте DataMatrix заново."
    ),
    "sticker_not_found": "Стикер не найден в этой поставке.",
    "order_frozen": "Заказ уже передан в доставку — КИЗ не изменить.",
    "invalid_order_ids": "Недопустимый список заказов для печати.",
    "asset_not_ready": "Печатный актив ещё не готов.",
    "asset_error": "Ошибка получения печатного актива.",
    "asset_not_found": "Печатный актив не найден.",
    "file_missing": "Файл печатного актива отсутствует.",
    "empty_content": "Пустой файл печатного актива.",
    "supply_has_cancelled_orders": "В поставке есть отменённые заказы.",
    "orders_not_ready": "Заказы не готовы к передаче.",
    "packaging_required": "Требуется завершить упаковку.",
    "marking_required": "Требуется маркировка.",
    "marking_not_allowed": "Маркировка не разрешена Wildberries.",
    "invalid_barcode_path": "Некорректный путь QR поставки.",
    "cargo_places_required": "Нужны грузоместа (ПВЗ).",
    "cargo_place_qr_not_ready": "QR грузомест не готов.",
    "physical_boxes_required": "Для передачи нужны физические короба.",
    "packed_order_unassigned": "Упакованный заказ не назначен в короб.",
    "order_cancelled": "Заказ отменён на Wildberries.",
    "supply_bad_status": "Неверный статус поставки.",
    "stale_preflight": "Чек-лист устарел — обновите preflight.",
    "trbx_oversized": "Сторона коробки превышает 60 см.",
    "trbx_sides_sum_exceeded": "Сумма сторон коробки превышает 140 см.",
    "trbx_overweight": "Вес коробки превышает 5 кг.",
    "trbx_min_orders": "Слишком мало заказов в грузоместе.",
    "trbx_volume_exceeded": "Суммарный объём грузомест превышает 1 м³.",
    "trbx_count_exceeded": "Слишком много грузомест.",
    "order_already_in_trbx": "Заказ уже в грузоместе.",
    "invalid_trbx_count": "Недопустимое количество грузомест.",
    "invalid_sticker_path": "Некорректный путь QR грузоместа.",
    "boxes_count_mismatch": "Число коробов не совпадает с count.",
    "cargo_places_preflight_failed": "Preflight грузомест не пройден.",
    "cargo_place_not_found": "Грузоместо не найдено в поставке.",
    "empty_cargo_place_selection": "Не выбраны грузоместа для удаления.",
    "measurements_confirmation_required": (
        "Укажите размеры и вес или подтвердите отсутствие данных."
    ),
    "deprecated_use_cargo_places": (
        "Ручное распределение заказов по грузоместам отключено — используйте cargo-places."
    ),
    "supply_not_in_delivery": "Поставка не в доставке.",
    "order_not_cancellable": "Заказ нельзя отменить.",
    "invalid_cursor": "Некорректный cursor.",
    "invalid_status_group": "Некорректная группа статусов.",
    "wb_operation_failed": "Операция Wildberries завершилась ошибкой.",
    # Warehouse binding / stock sync (fbs_sellers.py) — see ERROR_CATALOG_RU.md
    # "Склады и привязки" / "Синхронизация остатков" sections.
    "binding_not_found": "Привязка склада не найдена.",
    "invalid_wb_warehouse_id": "Некорректный ID склада WB.",
    "wms_warehouse_already_bound": "WMS-склад уже привязан.",
    "wb_warehouse_already_bound": "Этот WB-склад уже привязан к другому складу WMS.",
    "active_fbs_reservations": "Есть активные FBS-резервы.",
    "packaging_box_already_bound": "Короб уже привязан к другому грузоместу.",
    "packaging_box_not_found": "Короб не найден в складе этой поставки.",
    "supply_already_delivered": "Поставка уже передана в WB, изменение коробов запрещено.",
    "boxes_already_distributed": (
        "Нельзя переключить режим: в короба уже разложены заказы. Уберите заказы из "
        "коробов и повторите."
    ),
    "missing_fbs_packaging_location": "Для упакованного заказа не найдена исходная ячейка.",
    "ambiguous_fbs_packaging_fulfillment": (
        "Для заказа найдено несколько активных подтверждений упаковки."
    ),
    "fbs_packaging_product_mismatch": "Товар строки упаковки не совпадает с товаром заказа.",
}

_RETRYABLE_CODES = frozenset(
    {
        "wb_timeout",
        "wb_pending_confirmation",
        "operation_in_progress",
        "asset_not_ready",
        "asset_error",
    }
)


def fbs_error_message(code: str, explicit: str | None = None) -> str:
    if explicit and explicit != code:
        return explicit
    if code in FBS_ERROR_MESSAGES_RU:
        return FBS_ERROR_MESSAGES_RU[code]
    if code.startswith("wb_"):
        return "Ошибка Wildberries."
    return code


def fbs_error_retryable(code: str, explicit: bool | None = None) -> bool:
    if explicit is not None:
        return explicit
    return code in _RETRYABLE_CODES


def fbs_error_envelope(
    code: str,
    *,
    message: str | None = None,
    context: dict[str, Any] | None = None,
    retryable: bool | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": fbs_error_message(code, message),
        "context": context or {},
        "retryable": fbs_error_retryable(code, retryable),
    }


def raise_fbs_http(
    status_code: int,
    code: str,
    *,
    message: str | None = None,
    context: dict[str, Any] | None = None,
    retryable: bool | None = None,
) -> NoReturn:
    raise HTTPException(
        status_code=status_code,
        detail=fbs_error_envelope(
            code,
            message=message,
            context=context,
            retryable=retryable,
        ),
    )


def envelope_from_exc(exc: Any) -> dict[str, Any]:
    code = str(getattr(exc, "code", "internal_error"))
    message = getattr(exc, "message", None)
    context = getattr(exc, "context", None)
    retryable = getattr(exc, "retryable", None)
    if not isinstance(context, dict):
        context = {}
    if not isinstance(retryable, bool):
        retryable = None
    if not isinstance(message, str):
        message = None
    return fbs_error_envelope(
        code,
        message=message,
        context=context,
        retryable=retryable,
    )
