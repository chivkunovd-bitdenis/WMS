"""Generated Pydantic v2 models for Ozon Seller API 2.1 Returns operations.

Source of truth: tasks/ozon-integration-20260825/OZON_RETURNS_OPENAPI.json.
Run scripts/generate_ozon_returns_models.py to regenerate this file.
"""
# ruff: noqa: E501

from __future__ import annotations

from enum import Enum
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

_OPTIONAL_FIELD_DEFAULT = cast(Any, None)


class OzonReturnsModel(BaseModel):
    """Base model preserving OpenAPI's default additional-properties behaviour."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class OzonV1GetReturnsListRequest(OzonReturnsModel):
    __openapi_name__ = 'v1GetReturnsListRequest'
    filter: OzonGetReturnsListRequestFilter = Field(_OPTIONAL_FIELD_DEFAULT)
    limit: int = Field(..., description='Количество подгружаемых возвратов. Максимальное значение — 500.', json_schema_extra={'format': 'int32'})
    last_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор последнего подгруженного возврата.', json_schema_extra={'format': 'int64'})


class OzonGetReturnsListRequestFilter(OzonReturnsModel):
    __openapi_name__ = 'GetReturnsListRequestFilter'
    'Фильтры. Используйте только один фильтр в запросе: `logistic_return_date`, `storage_tariffication_start_date` или `visual_status_change_moment`, иначе вернётся ошибка.\n'
    logistic_return_date: OzonV1TimeRangeReturnDate = Field(_OPTIONAL_FIELD_DEFAULT)
    storage_tariffication_start_date: OzonV1TimeRangeStorageTariffication = Field(_OPTIONAL_FIELD_DEFAULT)
    visual_status_change_moment: OzonV1TimeRangeVisualStatus = Field(_OPTIONAL_FIELD_DEFAULT)
    order_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Фильтр по идентификатору заказа.', json_schema_extra={'format': 'int64'})
    posting_numbers: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Фильтр по номеру отправления. Передавайте не больше 50 постингов.')
    product_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Фильтр по названию товара.')
    offer_id: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Фильтр по артикулу товара.')
    visual_status_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Фильтр по статусу возврата:\n- `DisputeOpened` — открыт спор с покупателем;\n- `OnSellerApproval` — на согласовании у продавца;\n- `ArrivedAtReturnPlace` — в пункте выдачи;\n- `OnSellerClarification` — на уточнении у продавца;\n- `OnSellerClarificationAfterPartialCompensation` — на уточнении у продавца после частичной компенсации;\n- `OfferedPartialCompensation` — предложена частичная компенсация;\n- `ReturnMoneyApproved` — одобрен возврат денег;\n- `PartialCompensationReturned` — вернули часть денег;\n- `CancelledDisputeNotOpen` — возврат отклонён, спор не открыт;\n- `Rejected` — заявка отклонена;\n- `CrmRejected` — заявка отклонена Ozon;\n- `Cancelled` — заявка отменена;\n- `Approved` — заявка одобрена продавцом;\n- `ApprovedByOzon` — заявка одобрена Ozon;\n- `ReceivedBySeller` — продавец получил возврат;\n- `MovingToSeller` — возврат на пути к продавцу;\n- `ReturningToSellerByCourier` — курьер везёт возврат продавцу;\n- `Utilizing` — на утилизации;\n- `Utilized` — утилизирован;\n- `MoneyReturned` — покупателю вернули всю сумму;\n- `PartialCompensationInProcess` — одобрен частичный возврат денег;\n- `DisputeYouOpened` — продавец открыл спор;\n- `CompensationRejected` — отказано в компенсации;\n- `DisputeOpening` — обращение в поддержку отправлено;\n- `CompensationOffered` — ожидает вашего решения по компенсации;\n- `WaitingCompensation` — ожидает компенсации;\n- `SendingError` — ошибка при отправке обращения в поддержку;\n- `CompensationRejectedBySla` — истёк срок решения;\n- `CompensationRejectedBySeller` — продавец отказался от компенсации;\n- `MovingToOzon` — едет на склад Ozon;\n- `ReturnedToOzon` — на складе Ozon;\n- `MoneyReturnedBySystem` — быстрый возврат;\n- `WaitingShipment` — ожидает отправки.\n')
    warehouse_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Фильтр по идентификатору склада. Можно получить с помощью метода [/v1/warehouse/list](#operation/WarehouseAPI_WarehouseList).', json_schema_extra={'format': 'int64'})
    barcode: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Фильтр по штрихкоду возвратной этикетки.')
    return_schema: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Фильтр по схеме доставки: `FBS` или `FBO`.\n')
    compensation_status_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Фильтр по статусу компенсации:\n- `1` — отправлена;\n- `2` — получена;\n- `3` — отменена;\n- `4` — проведена декомпенсация.\n', json_schema_extra={'format': 'int32'})


class OzonV1TimeRangeReturnDate(OzonReturnsModel):
    __openapi_name__ = 'v1TimeRange_return_date'
    'Фильтр по дате создания возврата.'
    time_from: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Начало периода.', json_schema_extra={'format': 'date-time'})
    time_to: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Окончание периода.', json_schema_extra={'format': 'date-time'})


class OzonV1TimeRangeStorageTariffication(OzonReturnsModel):
    __openapi_name__ = 'v1TimeRange_storage_tariffication'
    'Фильтр по дате начала тарификации.'
    time_from: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Начало периода.', json_schema_extra={'format': 'date-time'})
    time_to: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Окончание периода.', json_schema_extra={'format': 'date-time'})


class OzonV1TimeRangeVisualStatus(OzonReturnsModel):
    __openapi_name__ = 'v1TimeRange_visual_status'
    'Фильтр по дате изменения статуса возврата.'
    time_from: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Начало периода.', json_schema_extra={'format': 'date-time'})
    time_to: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Окончание периода.', json_schema_extra={'format': 'date-time'})


class OzonV1GetReturnsListResponse(OzonReturnsModel):
    __openapi_name__ = 'v1GetReturnsListResponse'
    returns: list[OzonGetReturnsListResponseReturnsItem] = Field(_OPTIONAL_FIELD_DEFAULT, description='Информация о возвратах.')
    has_next: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если у продавца есть другие возвраты.\n')


class OzonGetReturnsListResponseReturnsItem(OzonReturnsModel):
    __openapi_name__ = 'GetReturnsListResponseReturnsItem'
    exemplars: list[OzonGetReturnsListResponseExemplar] = Field(_OPTIONAL_FIELD_DEFAULT, description='Информация об экземплярах.')
    id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор возврата.', json_schema_extra={'format': 'int64'})
    company_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор продавца.', json_schema_extra={'format': 'int64'})
    return_reason_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Причина возврата или отмены.')
    type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип возврата: \n`Cancellation` - отмена (до вручения);\n`FullReturn` - полный отказ при вручении;\n`PartialReturn` - частичный отказ при вручении;\n`ClientReturn` - клиентский возврат (после вручения);\n`Unknown` - технический возврат.\n')
    schema_: str = Field(_OPTIONAL_FIELD_DEFAULT, alias='schema', description='Схема возврата:\n`FBS`;\n`FBO`.\n')
    order_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор заказа.', json_schema_extra={'format': 'int64'})
    order_number: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер заказа.')
    place: OzonGetReturnsListResponsePlaceNow = Field(_OPTIONAL_FIELD_DEFAULT)
    target_place: OzonGetReturnsListResponsePlaceTarget = Field(_OPTIONAL_FIELD_DEFAULT)
    storage: OzonGetReturnsListResponseStorage = Field(_OPTIONAL_FIELD_DEFAULT)
    product: OzonGetReturnsListResponseProduct = Field(_OPTIONAL_FIELD_DEFAULT)
    logistic: OzonGetReturnsListResponseLogistic = Field(_OPTIONAL_FIELD_DEFAULT)
    visual: OzonGetReturnsListResponseVisual = Field(_OPTIONAL_FIELD_DEFAULT)
    additional_info: OzonGetReturnsListResponseAdditionalInfo = Field(_OPTIONAL_FIELD_DEFAULT)
    source_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Предыдущий идентификатор возврата.', json_schema_extra={'format': 'int64'})
    posting_number: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер отправления.')
    clearing_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Штрихкод изначального отправления.', json_schema_extra={'format': 'int64'})
    return_clearing_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Возвратный штрихкод изначального отправления.', json_schema_extra={'format': 'int64'})
    compensation_status: OzonGetReturnsListResponseCompensation = Field(_OPTIONAL_FIELD_DEFAULT)


class OzonGetReturnsListResponseExemplar(OzonReturnsModel):
    __openapi_name__ = 'GetReturnsListResponseExemplar'
    id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор экземпляра.', json_schema_extra={'format': 'int64'})


class OzonGetReturnsListResponsePlaceNow(OzonReturnsModel):
    __openapi_name__ = 'GetReturnsListResponsePlace_now'
    'Склад, где находится возврат.'
    id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор склада.', json_schema_extra={'format': 'int64'})
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название.')
    address: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Адрес.')


class OzonGetReturnsListResponsePlaceTarget(OzonReturnsModel):
    __openapi_name__ = 'GetReturnsListResponsePlace_target'
    'Склад, куда едет возврат.'
    id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор склада.', json_schema_extra={'format': 'int64'})
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название.')
    address: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Адрес.')


class OzonGetReturnsListResponseStorage(OzonReturnsModel):
    __openapi_name__ = 'GetReturnsListResponseStorage'
    'Информация о хранении.'
    sum: OzonSellerReturnsv1MoneyStorage = Field(_OPTIONAL_FIELD_DEFAULT)
    tariffication_first_date: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Первый день тарификации за хранение.', json_schema_extra={'format': 'date-time'})
    tariffication_start_date: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата старта тарификации за хранение.', json_schema_extra={'format': 'date-time'})
    arrived_moment: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата, когда возврат был готов к выдаче.', json_schema_extra={'format': 'date-time'})
    days: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Сколько дней возврат ожидает выдачи продавцу.', json_schema_extra={'format': 'int64'})
    utilization_sum: OzonSellerReturnsv1MoneyUtilization = Field(_OPTIONAL_FIELD_DEFAULT, json_schema_extra={'format': 'date-time'})
    utilization_forecast_date: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Планируемая дата утилизации.')


class OzonSellerReturnsv1MoneyStorage(OzonReturnsModel):
    __openapi_name__ = 'seller_returnsv1Money_storage'
    'Стоимость хранения.'
    currency_code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Валюта.')
    price: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Стоимость хранения.', json_schema_extra={'format': 'double'})


class OzonSellerReturnsv1MoneyUtilization(OzonReturnsModel):
    __openapi_name__ = 'seller_returnsv1Money_utilization'
    'Стоимость утилизации.'
    currency_code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Валюта.')
    price: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Стоимость утилизации.', json_schema_extra={'format': 'double'})


class OzonGetReturnsListResponseProduct(OzonReturnsModel):
    __openapi_name__ = 'GetReturnsListResponseProduct'
    'Информация о товаре.'
    sku: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор товара в системе Ozon — SKU.', json_schema_extra={'format': 'int64'})
    offer_id: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор товара в системе продавца — артикул.')
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название товара.')
    price: OzonSellerReturnsv1MoneyProduct = Field(_OPTIONAL_FIELD_DEFAULT)
    price_without_commission: OzonSellerReturnsv1MoneyWithoutCommission = Field(_OPTIONAL_FIELD_DEFAULT)
    commission_percent: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Процент комиссии.', json_schema_extra={'format': 'double'})
    commission: OzonSellerReturnsv1MoneyCommission = Field(_OPTIONAL_FIELD_DEFAULT)
    quantity: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество товара.', json_schema_extra={'format': 'int32'})


class OzonSellerReturnsv1MoneyProduct(OzonReturnsModel):
    __openapi_name__ = 'seller_returnsv1Money_product'
    'Стоимость товара.'
    currency_code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Валюта.')
    price: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Стоимость товара.', json_schema_extra={'format': 'double'})


class OzonSellerReturnsv1MoneyWithoutCommission(OzonReturnsModel):
    __openapi_name__ = 'seller_returnsv1Money_without_commission'
    'Стоимость товара без комиссии.'
    currency_code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Валюта.')
    price: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Стоимость товара без комиссии.', json_schema_extra={'format': 'double'})


class OzonSellerReturnsv1MoneyCommission(OzonReturnsModel):
    __openapi_name__ = 'seller_returnsv1Money_commission'
    'Информация о комиссии.'
    currency_code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Валюта.')
    price: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Размер комиссии.', json_schema_extra={'format': 'double'})


class OzonGetReturnsListResponseLogistic(OzonReturnsModel):
    __openapi_name__ = 'GetReturnsListResponseLogistic'
    'Информация о возврате.'
    technical_return_moment: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата, когда заказ поставили на технический возврат.', json_schema_extra={'format': 'date-time'})
    final_moment: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата, когда возврат прибыл на фулфилмент или выдан продавцу.', json_schema_extra={'format': 'date-time'})
    cancelled_with_compensation_moment: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата, когда продавцу компенсировали возврат.', json_schema_extra={'format': 'date-time'})
    return_date: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата, когда покупатель вернул товар.', json_schema_extra={'format': 'date-time'})
    barcode: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Штрихкод этикетки возврата.')


class OzonGetReturnsListResponseVisual(OzonReturnsModel):
    __openapi_name__ = 'GetReturnsListResponseVisual'
    'Информация о статусе возврата.'
    status: OzonGetReturnsListResponseVisualStatus = Field(_OPTIONAL_FIELD_DEFAULT)
    change_moment: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата изменения статуса возврата.', json_schema_extra={'format': 'date-time'})


class OzonGetReturnsListResponseVisualStatus(OzonReturnsModel):
    __openapi_name__ = 'GetReturnsListResponseVisualStatus'
    'Статус возврата.'
    id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор статуса возврата.', json_schema_extra={'format': 'int32'})
    display_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название статуса возврата.')
    sys_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Системное название статуса возврата.')


class OzonGetReturnsListResponseAdditionalInfo(OzonReturnsModel):
    __openapi_name__ = 'GetReturnsListResponseAdditionalInfo'
    'Дополнительная информация.'
    is_opened: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если возврат вскрыт.\n')
    is_super_econom: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если возврат относится к товарам «Суперэконом».\n')


class OzonGetReturnsListResponseCompensation(OzonReturnsModel):
    __openapi_name__ = 'GetReturnsListResponseCompensation'
    'Информация о статусе компенсации.'
    status: OzonGetReturnsListResponseCompensationStatus = Field(_OPTIONAL_FIELD_DEFAULT)
    change_moment: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата изменения статуса компенсации.', json_schema_extra={'format': 'date-time'})


class OzonGetReturnsListResponseCompensationStatus(OzonReturnsModel):
    __openapi_name__ = 'GetReturnsListResponseCompensationStatus'
    'Статус компенсации.'
    id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор статуса.', json_schema_extra={'format': 'int32'})
    display_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название статуса:\n- «Отправлено на компенсацию»,\n- «Вы получили компенсацию»,\n- «Компенсация отменена»,\n- «Провели декомпенсацию».\n')
    sys_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Системное название статуса:\n- `Sent` — отправлена;\n- `Received` — получена;\n- `Canceled` — отменена;\n- `DecompensationSent` — проведена декомпенсация.\n')


class OzonRpcStatus(OzonReturnsModel):
    __openapi_name__ = 'rpcStatus'
    code: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Код ошибки.', json_schema_extra={'format': 'int32'})
    details: list[OzonProtobufAny] = Field(_OPTIONAL_FIELD_DEFAULT, description='Дополнительная информация об ошибке.')
    message: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Описание ошибки.')


class OzonProtobufAny(OzonReturnsModel):
    __openapi_name__ = 'protobufAny'
    typeUrl: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип протокола передачи данных.')
    value: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Значение ошибки.', json_schema_extra={'format': 'byte'})


class OzonV1ReturnsCompanyFbsInfoRequest(OzonReturnsModel):
    __openapi_name__ = 'v1ReturnsCompanyFbsInfoRequest'
    filter: OzonV1ReturnsCompanyFbsInfoRequestFilter = Field(_OPTIONAL_FIELD_DEFAULT)
    pagination: OzonReturnsCompanyFbsInfoRequestPagination = Field(...)


class OzonV1ReturnsCompanyFbsInfoRequestFilter(OzonReturnsModel):
    __openapi_name__ = 'v1ReturnsCompanyFbsInfoRequestFilter'
    'Фильтры.'
    place_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Фильтр по идентификатору drop-off пункта.', json_schema_extra={'format': 'int64'})


class OzonReturnsCompanyFbsInfoRequestPagination(OzonReturnsModel):
    __openapi_name__ = 'ReturnsCompanyFbsInfoRequestPagination'
    'Разделение ответа метода.'
    last_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор последнего drop-off пункта на странице. Для первого запроса оставьте это поле пустым.\n\nЧтобы получить следующие значения, укажите `id` последнего drop-off пункта из ответа предыдущего запроса.\n', json_schema_extra={'format': 'int64'})
    limit: int = Field(..., description='Количество drop-off пунктов на странице. Максимум — 500.', json_schema_extra={'format': 'int32'})


class OzonV1ReturnsCompanyFbsInfoResponse(OzonReturnsModel):
    __openapi_name__ = 'v1ReturnsCompanyFbsInfoResponse'
    drop_off_points: list[OzonReturnsCompanyFbsInfoResponseDropOffPoints] = Field(_OPTIONAL_FIELD_DEFAULT, description='Информация о drop-off пунктах.')
    has_next: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак, есть ли ещё пункты, где продавца ожидают возвраты.')


class OzonReturnsCompanyFbsInfoResponseDropOffPoints(OzonReturnsModel):
    __openapi_name__ = 'ReturnsCompanyFbsInfoResponseDropOffPoints'
    address: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Адрес drop-off пункта.')
    box_count: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество коробок в drop-off пункте.', json_schema_extra={'format': 'int32'})
    id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор drop-off пункта.', json_schema_extra={'format': 'int64'})
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название drop-off пункта.')
    pass_info: OzonReturnsCompanyFbsInfoResponsePassInfo = Field(_OPTIONAL_FIELD_DEFAULT)
    place_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор склада, на который приедет отгрузка.', json_schema_extra={'format': 'int64'})
    returns_count: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество возвратов в drop-off пункте.', json_schema_extra={'format': 'int32'})
    utc_offset: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Смещение часового пояса времени отгрузки от UTC-0.')
    warehouses_ids: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор складов продавца.')


class OzonReturnsCompanyFbsInfoResponsePassInfo(OzonReturnsModel):
    __openapi_name__ = 'ReturnsCompanyFbsInfoResponsePass_info'
    'Информация о пропуске.'
    count: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество пропусков на drop-off пункт.', json_schema_extra={'format': 'int32'})
    is_required: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак, нужен ли пропуск на drop-off пункт.')


class OzonV1Empty(OzonReturnsModel):
    __openapi_name__ = 'v1Empty'
    pass


class OzonV1GiveoutIsEnabledResponse(OzonReturnsModel):
    __openapi_name__ = 'v1GiveoutIsEnabledResponse'
    enabled: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если вы можете получить возвратную отгрузку по штрихкоду.\n')


class OzonV1GiveoutListRequest(OzonReturnsModel):
    __openapi_name__ = 'v1GiveoutListRequest'
    last_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор последнего значения на странице.', json_schema_extra={'format': 'int64'})
    limit: int = Field(..., description='Количество элементов в ответе.', json_schema_extra={'format': 'int64'})


class OzonV1GiveoutListResponse(OzonReturnsModel):
    __openapi_name__ = 'v1GiveoutListResponse'
    giveouts: list[OzonGiveoutListResponseGiveoutDetails] = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор отгрузки.')


class OzonGiveoutListResponseGiveoutDetails(OzonReturnsModel):
    __openapi_name__ = 'GiveoutListResponseGiveoutDetails'
    approved_articles_count: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество товаров в отгрузке.', json_schema_extra={'format': 'int32'})
    created_at: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время.', json_schema_extra={'format': 'date-time'})
    giveout_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор отгрузки.', json_schema_extra={'format': 'int64'})
    giveout_status: OzonV1GiveoutStatus = Field(_OPTIONAL_FIELD_DEFAULT)
    total_articles_count: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Общее количество товаров, которые нужно забрать со склада.', json_schema_extra={'format': 'int32'})
    warehouse_address: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Адрес склада.')
    warehouse_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор склада.', json_schema_extra={'format': 'int64'})
    warehouse_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название склада.')


class OzonV1GiveoutStatus(OzonReturnsModel):
    __openapi_name__ = 'v1GiveoutStatus'
    'Статусы возвратной отгрузки:\n - `GIVEOUT_STATUS_UNSPECIFIED` — не определён, напишите в поддержку.\n - `GIVEOUT_STATUS_CREATED` — создана.\n - `GIVEOUT_STATUS_APPROVED` — одобрена.\n - `GIVEOUT_STATUS_COMPLETED` — завершена.\n - `GIVEOUT_STATUS_CANCELLED` — отменена.\n'
    pass


class OzonV1GiveoutInfoRequest(OzonReturnsModel):
    __openapi_name__ = 'v1GiveoutInfoRequest'
    giveout_id: int = Field(..., description='Идентификатор отгрузки.', json_schema_extra={'format': 'int64'})


class OzonV1GiveoutInfoResponse(OzonReturnsModel):
    __openapi_name__ = 'v1GiveoutInfoResponse'
    articles: list[OzonGiveoutInfoResponseArticleDetails] = Field(_OPTIONAL_FIELD_DEFAULT, description='Артикулы товаров.')
    giveout_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор отгрузки.', json_schema_extra={'format': 'int64'})
    giveout_status: OzonV1GiveoutStatus = Field(_OPTIONAL_FIELD_DEFAULT)
    warehouse_address: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Адрес склада.')
    warehouse_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название склада.')


class OzonGiveoutInfoResponseArticleDetails(OzonReturnsModel):
    __openapi_name__ = 'GiveoutInfoResponseArticleDetails'
    approved: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если отгрузка подтверждена.\n')
    delivery_schema: OzonV1GiveoutDeliverySchema = Field(_OPTIONAL_FIELD_DEFAULT)
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название товара.')
    seller_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор продавца.', json_schema_extra={'format': 'int64'})


class OzonV1GiveoutDeliverySchema(OzonReturnsModel):
    __openapi_name__ = 'v1GiveoutDeliverySchema'
    'Cхема доставки:\n - `GIVEOUT_DELIVERY_SCHEMA_UNSPECIFIED` — не определёна, напишите в поддержку.\n - `GIVEOUT_DELIVERY_SCHEMA_FBO` — FBO.\n - `GIVEOUT_DELIVERY_SCHEMA_FBS` — FBS.\n'
    pass


class OzonV1GiveoutGetBarcodeResponse(OzonReturnsModel):
    __openapi_name__ = 'v1GiveoutGetBarcodeResponse'
    barcode: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Значение штрихкода в текстовом виде.')


class OzonV1GiveoutGetPDFResponse(OzonReturnsModel):
    __openapi_name__ = 'v1GiveoutGetPDFResponse'
    file_content: str = Field(_OPTIONAL_FIELD_DEFAULT, description='PDF-файл со штрихкодом в кодировке Base64.')
    file_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название файла.')
    content_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип файла.')


class OzonV1GiveoutGetPNGResponse(OzonReturnsModel):
    __openapi_name__ = 'v1GiveoutGetPNGResponse'
    file_content: str = Field(_OPTIONAL_FIELD_DEFAULT, description='PNG-файл со штрихкодом в кодировке Base64.')
    file_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название файла.')
    content_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип файла.')


class OzonV1GiveoutBarcodeResetResponse(OzonReturnsModel):
    __openapi_name__ = 'v1GiveoutBarcodeResetResponse'
    file_content: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Изображение со штрихкодом в бинарном виде.')
    file_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название файла.')
    content_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип файла.')


MODEL_BY_OPENAPI_NAME: dict[str, type[BaseModel] | type[Enum]] = {
    'v1GetReturnsListRequest': OzonV1GetReturnsListRequest,
    'GetReturnsListRequestFilter': OzonGetReturnsListRequestFilter,
    'v1TimeRange_return_date': OzonV1TimeRangeReturnDate,
    'v1TimeRange_storage_tariffication': OzonV1TimeRangeStorageTariffication,
    'v1TimeRange_visual_status': OzonV1TimeRangeVisualStatus,
    'v1GetReturnsListResponse': OzonV1GetReturnsListResponse,
    'GetReturnsListResponseReturnsItem': OzonGetReturnsListResponseReturnsItem,
    'GetReturnsListResponseExemplar': OzonGetReturnsListResponseExemplar,
    'GetReturnsListResponsePlace_now': OzonGetReturnsListResponsePlaceNow,
    'GetReturnsListResponsePlace_target': OzonGetReturnsListResponsePlaceTarget,
    'GetReturnsListResponseStorage': OzonGetReturnsListResponseStorage,
    'seller_returnsv1Money_storage': OzonSellerReturnsv1MoneyStorage,
    'seller_returnsv1Money_utilization': OzonSellerReturnsv1MoneyUtilization,
    'GetReturnsListResponseProduct': OzonGetReturnsListResponseProduct,
    'seller_returnsv1Money_product': OzonSellerReturnsv1MoneyProduct,
    'seller_returnsv1Money_without_commission': OzonSellerReturnsv1MoneyWithoutCommission,
    'seller_returnsv1Money_commission': OzonSellerReturnsv1MoneyCommission,
    'GetReturnsListResponseLogistic': OzonGetReturnsListResponseLogistic,
    'GetReturnsListResponseVisual': OzonGetReturnsListResponseVisual,
    'GetReturnsListResponseVisualStatus': OzonGetReturnsListResponseVisualStatus,
    'GetReturnsListResponseAdditionalInfo': OzonGetReturnsListResponseAdditionalInfo,
    'GetReturnsListResponseCompensation': OzonGetReturnsListResponseCompensation,
    'GetReturnsListResponseCompensationStatus': OzonGetReturnsListResponseCompensationStatus,
    'rpcStatus': OzonRpcStatus,
    'protobufAny': OzonProtobufAny,
    'v1ReturnsCompanyFbsInfoRequest': OzonV1ReturnsCompanyFbsInfoRequest,
    'v1ReturnsCompanyFbsInfoRequestFilter': OzonV1ReturnsCompanyFbsInfoRequestFilter,
    'ReturnsCompanyFbsInfoRequestPagination': OzonReturnsCompanyFbsInfoRequestPagination,
    'v1ReturnsCompanyFbsInfoResponse': OzonV1ReturnsCompanyFbsInfoResponse,
    'ReturnsCompanyFbsInfoResponseDropOffPoints': OzonReturnsCompanyFbsInfoResponseDropOffPoints,
    'ReturnsCompanyFbsInfoResponsePass_info': OzonReturnsCompanyFbsInfoResponsePassInfo,
    'v1Empty': OzonV1Empty,
    'v1GiveoutIsEnabledResponse': OzonV1GiveoutIsEnabledResponse,
    'v1GiveoutListRequest': OzonV1GiveoutListRequest,
    'v1GiveoutListResponse': OzonV1GiveoutListResponse,
    'GiveoutListResponseGiveoutDetails': OzonGiveoutListResponseGiveoutDetails,
    'v1GiveoutStatus': OzonV1GiveoutStatus,
    'v1GiveoutInfoRequest': OzonV1GiveoutInfoRequest,
    'v1GiveoutInfoResponse': OzonV1GiveoutInfoResponse,
    'GiveoutInfoResponseArticleDetails': OzonGiveoutInfoResponseArticleDetails,
    'v1GiveoutDeliverySchema': OzonV1GiveoutDeliverySchema,
    'v1GiveoutGetBarcodeResponse': OzonV1GiveoutGetBarcodeResponse,
    'v1GiveoutGetPDFResponse': OzonV1GiveoutGetPDFResponse,
    'v1GiveoutGetPNGResponse': OzonV1GiveoutGetPNGResponse,
    'v1GiveoutBarcodeResetResponse': OzonV1GiveoutBarcodeResetResponse,
}

for _ozon_model in MODEL_BY_OPENAPI_NAME.values():
    if isinstance(_ozon_model, type) and issubclass(_ozon_model, BaseModel):
        _ozon_model.model_rebuild(_types_namespace=globals())

__all__ = [*MODEL_BY_OPENAPI_NAME, 'MODEL_BY_OPENAPI_NAME', 'OzonReturnsModel']
