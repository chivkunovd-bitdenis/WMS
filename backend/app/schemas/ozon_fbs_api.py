"""Generated Pydantic v2 models for Ozon Seller API 2.1 FBS operations.

Source of truth: tasks/ozon-integration-20260825/OZON_FBS_OPENAPI.json.
Run scripts/generate_ozon_fbs_models.py to regenerate this file.
"""
# ruff: noqa: E501, RUF001

from __future__ import annotations

from enum import Enum, StrEnum
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

_OPTIONAL_FIELD_DEFAULT = cast(Any, None)


class OzonFbsModel(BaseModel):
    """Base model preserving OpenAPI's default additional-properties behaviour."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class OzonPostingV4PostingFbsUnfulfilledListRequest(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListRequest'
    cursor: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Указатель для выборки следующих данных.')
    filter: OzonPostingV4PostingFbsUnfulfilledListRequestFilter = Field(_OPTIONAL_FIELD_DEFAULT)
    limit: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество значений в ответе.', ge=1, le=100, json_schema_extra={'format': 'int64'})
    sort_dir: OzonPostingV4PostingFbsUnfulfilledListRequestSortDirEnum = Field(_OPTIONAL_FIELD_DEFAULT)
    translit: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, чтобы включить транслитерацию адреса из кириллицы в латиницу.\n')
    with_: OzonPostingV4PostingFbsUnfulfilledListRequestWith = Field(_OPTIONAL_FIELD_DEFAULT, alias='with')


class OzonPostingV4PostingFbsUnfulfilledListRequestFilter(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListRequest.Filter'
    'Фильтр запроса.\n\nИспользуйте фильтр по времени сборки — `cutoff` или по дате передачи отправления в доставку — `delivering_date`.\nЕсли использовать их вместе, в ответе вернётся ошибка.\n\nЧтобы использовать фильтр по времени сборки, заполните поля `cutoff_from` и `cutoff_to`.\n\nЧтобы использовать фильтр по дате передачи отправления в доставку, заполните поля `delivering_date_from` и `delivering_date_to`.\n'
    cutoff_from: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Время, до которого продавцу нужно собрать заказ. Начало периода.', json_schema_extra={'format': 'date-time'})
    cutoff_to: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Время, до которого продавцу нужно собрать заказ. Конец периода.', json_schema_extra={'format': 'date-time'})
    delivering_date_from: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Минимальная дата передачи отправления в доставку.', json_schema_extra={'format': 'date-time'})
    delivering_date_to: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Максимальная дата передачи отправления в доставку.', json_schema_extra={'format': 'date-time'})
    delivery_method_ids: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор способа доставки. Можно получить с помощью метода [/v1/delivery-method/list](#operation/WarehouseAPI_DeliveryMethodList).', max_length=1000)
    last_changed_status_date: OzonPostingV4PostingFbsUnfulfilledListRequestFilterLastChangedStatusDate = Field(_OPTIONAL_FIELD_DEFAULT)
    provider_ids: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор службы доставки. Можно получить с помощью метода [/v1/delivery-method/list](#operation/WarehouseAPI_DeliveryMethodList).', max_length=1000)
    statuses: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Статус отправления:\n- `acceptance_in_progress` — идёт приёмка;\n- `awaiting_approve` — ожидает подтверждения;\n- `awaiting_packaging` — ожидает упаковки;\n- `awaiting_registration` — ожидает регистрации;\n- `awaiting_deliver` — ожидает отгрузки;\n- `arbitration` — арбитраж;\n- `client_arbitration` — клиентский арбитраж доставки;\n- `delivering` — доставляется;\n- `driver_pickup` — у водителя;\n- `not_accepted` — не принято на сортировочном центре.\n')
    warehouse_ids: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор склада. Можно получить с помощью метода [/v1/warehouse/list](#operation/WarehouseAPI_WarehouseList).', max_length=1000)


class OzonPostingV4PostingFbsUnfulfilledListRequestFilterLastChangedStatusDate(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListRequest.Filter.LastChangedStatusDate'
    'Период, в который последний раз изменялся статус отправления.'
    from_: str = Field(_OPTIONAL_FIELD_DEFAULT, alias='from', description='Дата начала периода.', json_schema_extra={'format': 'date-time'})
    to: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата окончания периода.', json_schema_extra={'format': 'date-time'})


class OzonPostingV4PostingFbsUnfulfilledListRequestSortDirEnum(StrEnum):
    'Направление сортировки:\n- `ASC` — по возрастанию;\n- `DESC` — по убыванию.\n'
    ASC = 'ASC'
    DESC = 'DESC'


class OzonPostingV4PostingFbsUnfulfilledListRequestWith(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListRequest.With'
    'Дополнительные поля, которые нужно добавить в ответ.'
    analytics_data: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, чтобы добавить в ответ данные аналитики.\n')
    barcodes: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, чтобы добавить в ответ штрихкоды отправления.\n')
    financial_data: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, чтобы добавить в ответ финансовые данные.\n')
    legal_info: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, чтобы добавить в ответ юридическую информацию.\n')


class OzonPostingV4PostingFbsUnfulfilledListResponse(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListResponse'
    count: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество отправлений в ответе.', json_schema_extra={'format': 'int64'})
    cursor: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Указатель для выборки следующих данных.')
    has_next: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если в ответе вернулись не все отправления.\n')
    postings: list[OzonPostingV4PostingFbsUnfulfilledListResponsePostings] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список отправлений.')


class OzonPostingV4PostingFbsUnfulfilledListResponsePostings(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListResponse.Postings'
    addressee: OzonPostingV4PostingFbsUnfulfilledListResponsePostingsAddressee = Field(_OPTIONAL_FIELD_DEFAULT)
    analytics_data: OzonPostingV4PostingFbsUnfulfilledListResponsePostingsAnalyticsData = Field(_OPTIONAL_FIELD_DEFAULT)
    available_actions: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Доступные действия и информация об отправлении:\n- `arbitration` — открыть спор;\n- `awaiting_delivery` — перевести в статус «Ожидает отгрузки»;\n- `can_create_chat` — начать чат с покупателем;\n- `cancel` — отменить отправление;\n- `click_track_number` — просмотреть по трек-номеру историю изменения статусов в личном кабинете;\n- `customer_phone_available` — телефон покупателя;\n- `has_weight_products` — весовые товары в отправлении;\n- `hide_region_and_city` — скрыть регион и город покупателя в отчёте;\n- `invoice_get` —  получить информацию из счёта-фактуры;\n- `invoice_send` — создать счёт-фактуру;\n- `invoice_update` — отредактировать счёт-фактуру;\n- `label_download_big` — скачать большую этикетку;\n- `label_download_small` — скачать маленькую этикетку;\n- `label_download` — скачать этикетку;\n- `non_int_delivered` — перевести в статус «Условно доставлен»;\n- `non_int_delivering` — перевести в статус «Доставляется»;\n- `non_int_last_mile` — перевести в статус «Курьер в пути»;\n- `product_cancel` — отменить часть товаров в отправлении;\n- `set_cutoff` — укажите дату отгрузки методом [/v1/posting/cutoff/set](#operation/PostingAPI_SetPostingCutoff) не позже даты в параметре `shipment_date`;\n- `set_timeslot` — изменить время доставки покупателю;\n- `set_track_number` — указать или изменить трек-номер;\n- `ship_async_in_process` — отправление собирается;\n- `ship_async_retry` — собрать отправление повторно после ошибки сборки;\n- `ship_async` — собрать отправление;\n- `ship_with_additional_info` — заполните дополнительную информацию методом [/v6/fbs/posting/product/exemplar/set](https://docs.ozon.ru/api/seller/#operation/PostingAPI_FbsPostingProductExemplarSetV6);\n- `ship` — собрать отправление;\n- `update_cis` — изменить дополнительную информацию.\n')
    barcodes: OzonPostingV4PostingFbsUnfulfilledListResponsePostingsBarcodes = Field(_OPTIONAL_FIELD_DEFAULT)
    cancellation: OzonPostingV4PostingFbsUnfulfilledListResponsePostingsCancellation = Field(_OPTIONAL_FIELD_DEFAULT)
    customer: OzonPostingV4PostingFbsUnfulfilledListResponsePostingsCustomer = Field(_OPTIONAL_FIELD_DEFAULT)
    container: OzonPostingV4PostingFbsUnfulfilledListResponsePostingsContainer = Field(_OPTIONAL_FIELD_DEFAULT)
    container_sort_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип сортировки грузоместа:\n  - `SORT` — сортируемый;\n  - `NON-SORT` — несортируемый.\n')
    delivering_date: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата передачи отправления в доставку.', json_schema_extra={'format': 'date-time'})
    delivery_method: OzonPostingV4PostingFbsUnfulfilledListResponsePostingsDeliveryMethod = Field(_OPTIONAL_FIELD_DEFAULT)
    delivery_schema: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Схема доставки:\n- `SDS` — идентификатор единого SKU;\n- `FBO` — идентификатор товара, который продаётся со склада Ozon;\n- `FBS` — идентификатор товара, который продаётся со склада FBS;\n- `Crossborder` — идентификатор товара, который продаётся из-за границы.\n')
    destination_place_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор места назначения.', json_schema_extra={'format': 'int64'})
    destination_place_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название места назначения.')
    external_order: OzonPostingV4PostingFbsUnfulfilledListResponsePostingsExternalOrder = Field(_OPTIONAL_FIELD_DEFAULT)
    financial_data: OzonPostingV4PostingFbsUnfulfilledListResponsePostingsFinancialData = Field(_OPTIONAL_FIELD_DEFAULT)
    in_process_at: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время начала обработки отправления.', json_schema_extra={'format': 'date-time'})
    integration_type_flow: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Процесс обработки отправления:\n- `ozon` — доставка силами Ozon;\n- `aggregator` — доставка внешней службой, Ozon регистрирует заказ;\n- `non_integrated` — доставка силами продавца;\n- `3pl_tracking` — доставка внешней службой, продавец регистрирует заказ;\n- `hybrid` — гибридная интеграция;\n- `hybrid_aggregator` — гибридная интеграция с доставкой внешней службой, Ozon регистрирует заказ;\n- `hybrid_non_integrated` — гибридная интеграция с доставкой силами продавца;\n- `hybrid_3pl_tracking` — гибридная интеграция с доставкой внешней службой, продавец регистрирует заказ;\n- `click_and_collect` — бронирование в магазине партнёра;\n- `FBP` — доставка с партнёрских складов Ozon.\n')
    is_click_and_collect: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если отправление доставляется методом «Самовывоз из магазина».\n')
    is_express: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если использовалась быстрая доставка Ozon Express.\n')
    is_multibox: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак, что в отправлении есть многокоробочный товар и нужно передать количество коробок для него:\n\n- `true` — до сборки передайте количество коробок через метод [/v3/posting/multiboxqty/set](#operation/PostingAPI_PostingMultiBoxQtySetV3).\n- `false` — отправление собрано с указанием количества коробок в параметре `multi_box_qty` или в отправлении нет многокоробочного товара.\n')
    is_presortable: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если товар пересорт.\n')
    legal_info: OzonPostingV4PostingFbsUnfulfilledListResponsePostingsLegalInfo = Field(_OPTIONAL_FIELD_DEFAULT)
    multi_box_qty: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество коробок, в которые упакован товар.', json_schema_extra={'format': 'int32'})
    optional: OzonPostingV4PostingFbsUnfulfilledListResponsePostingsOptional = Field(_OPTIONAL_FIELD_DEFAULT)
    order_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор заказа, к которому относится отправление.', json_schema_extra={'format': 'int64'})
    order_number: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер заказа, к которому относится отправление.')
    parent_posting_number: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер родительского отправления, в результате разделения которого появилось текущее.')
    pickup_code_verified_at: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время успешной валидации кода курьера. Проверьте код курьера методом [/v1/posting/fbs/pick-up-code/verify](#operation/PostingAPI_PostingFBSPickupCodeVerify).', json_schema_extra={'format': 'date-time'})
    posting_number: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер отправления.')
    products: list[OzonPostingV4PostingFbsUnfulfilledListResponsePostingsProducts] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список товаров в отправлении.')
    prr_option: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Код услуги погрузочно-разгрузочных работ:\n- `lift` — подъём на лифте;\n- `stairs` — подъём по лестнице;\n- `none` — покупатель отказался от услуги, поднимать товары не нужно;\n- `delivery_default` — доставка включена в стоимость, по условиям оферты нужно доставить товар на этаж.\n\nДля КГТ-отправлений с доставкой силами продавца или интегрированной службой.\n')
    quantum_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор эконом-товара.', json_schema_extra={'format': 'int64'})
    require_blr_traceable_attrs: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если нужно заполнить атрибуты отслеживаемости.\n')
    requirements: OzonPostingV4PostingFbsUnfulfilledListResponsePostingsRequirements = Field(_OPTIONAL_FIELD_DEFAULT)
    shipment_date: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время, до которой нужно собрать отправление. Показываем рекомендованное время отгрузки. По истечении этого времени начнёт применяться новый тариф, информацию о нём получите в поле `tariffication`.', json_schema_extra={'format': 'date-time'})
    shipment_date_without_delay: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время отгрузки без просрочки.', json_schema_extra={'format': 'date-time'})
    sorting_center: OzonPostingV4PostingFbsUnfulfilledListResponsePostingsSortingCenter = Field(_OPTIONAL_FIELD_DEFAULT)
    status: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Статус отправления:\n- `acceptance_in_progress` — идёт приёмка;\n- `arbitration` — арбитраж;\n- `awaiting_approve` — ожидает подтверждения;\n- `awaiting_deliver` — ожидает отгрузки;\n- `awaiting_packaging` — ожидает упаковки;\n- `awaiting_registration` — ожидает регистрации;\n- `awaiting_verification` — создано;\n- `cancelled` — отменено;\n- `cancelled_from_split_pending` — отменено из-за разделения отправления;\n- `client_arbitration` — клиентский арбитраж доставки;\n- `delivering` — доставляется;\n- `driver_pickup` — у водителя;\n- `not_accepted` — не принято на сортировочном центре.\n')
    substatus: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Подстатус отправления:\n- `posting_acceptance_in_progress`— идёт приёмка;\n- `posting_in_arbitration` — арбитраж;\n- `posting_created` — создано;\n- `posting_in_carriage` — в перевозке;\n- `posting_not_in_carriage` — не добавлено в перевозку;\n- `posting_registered` — зарегистрировано;\n- `posting_transferring_to_delivery`, если `status=awaiting_deliver` — передаётся в доставку;\n- `posting_awaiting_passport_data` — ожидает паспортных данных;\n- `posting_created` — создано;\n- `posting_awaiting_registration` — ожидает регистрации;\n- `posting_registration_error` — ошибка регистрации;\n- `posting_transferring_to_delivery`, если `status=awaiting_registration` — передаётся курьеру;\n- `posting_split_pending` — создано;\n- `posting_canceled` — отменено;\n- `posting_in_client_arbitration` — клиентский арбитраж доставки;\n- `posting_delivered` — доставлено;\n- `posting_received` — получено;\n- `posting_conditionally_delivered` — условно доставлено;\n- `posting_in_courier_service` — курьер в пути;\n- `posting_in_pickup_point` — в пункте выдачи;\n- `posting_on_way_to_city` — в пути в ваш город;\n- `posting_on_way_to_pickup_point` — в пути в пункт выдачи;\n- `posting_returned_to_warehouse` — возвращено на склад;\n- `posting_transferred_to_courier_service` — передаётся в службу доставки;\n- `posting_driver_pick_up` — у водителя;\n- `posting_not_in_sort_center` — не принято на сортировочном центре;\n- `ship_failed` — сборка не удалась.\n')
    tariffication: OzonPostingV4PostingFbsUnfulfilledListResponsePostingsTariffication = Field(_OPTIONAL_FIELD_DEFAULT)
    tariffication_steps: list[OzonPostingV4PostingFbsUnfulfilledListResponsePostingsTarifficationStep] = Field(_OPTIONAL_FIELD_DEFAULT, description='Этапы тарификации.')
    tpl_integration_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип интеграции со службой доставки:\n  - `ozon` — доставка службой Ozon;\n  - `3pl_tracking` — доставка интегрированной службой;\n  - `non_integrated` — доставка сторонней службой;\n  - `aggregator` — доставка через партнёрскую доставку Ozon;\n  - `hybryd` — схема доставки Почты России.\n')
    tracking_number: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Трек-номер отправления.')
    volume_weight: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Объёмный вес товара.', json_schema_extra={'format': 'double'})


class OzonPostingV4PostingFbsUnfulfilledListResponsePostingsAddressee(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListResponse.Postings.Addressee'
    'Контактные данные получателя.'
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Имя получателя.')


class OzonPostingV4PostingFbsUnfulfilledListResponsePostingsAnalyticsData(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListResponse.Postings.AnalyticsData'
    'Данные аналитики.'
    city: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Город доставки. Только для отправлений rFBS и продавцов из СНГ.')
    client_delivery_date_begin: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время начала доставки. Только для отправлений, оформленных через [Ozon Доставку](#tag/OzonLogistics).', json_schema_extra={'format': 'date-time'})
    client_delivery_date_end: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Ожидаемая дата, до которой заказ будет доставлен. Только для отправлений, оформленных через [Ozon Доставку](#tag/OzonLogistics).', json_schema_extra={'format': 'date-time'})
    delivery_date_begin: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время начала доставки.', json_schema_extra={'format': 'date-time'})
    delivery_date_end: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время конца доставки.', json_schema_extra={'format': 'date-time'})
    delivery_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Способ доставки.')
    is_legal: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если получатель юридическое лицо.\n')
    is_premium: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если у получателя есть подписка Premium.\n')
    payment_type_group_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Способ оплаты: \n- `картой онлайн`;\n- `карта Ozon Банка`;\n- `автосписание с карты Ozon Банка при выдаче`;\n- `сохранённой картой при получении`;\n- `Система Быстрых Платежей`;\n- `Ozon Рассрочка`;\n- `оплата на расчётный счёт`;\n- `SberPay`;\n- `предоплата на стороне внешнего продавца`.\n')
    region: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Регион доставки. Только для отправлений rFBS.')
    tpl_provider: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Служба доставки.')
    tpl_provider_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор службы доставки.', json_schema_extra={'format': 'int64'})
    warehouse: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название склада отправки заказа.')
    warehouse_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор склада.', json_schema_extra={'format': 'int64'})


class OzonPostingV4PostingFbsUnfulfilledListResponsePostingsBarcodes(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListResponse.Postings.Barcodes'
    'Штрихкоды отправления.'
    lower_barcode: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Нижний штрихкод на маркировке отправления.')
    upper_barcode: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Верхний штрихкод на маркировке отправления.')


class OzonPostingV4PostingFbsUnfulfilledListResponsePostingsCancellation(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListResponse.Postings.Cancellation'
    'Информация об отмене.'
    affect_cancellation_rating: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если отмена влияет на рейтинг продавца.\n')
    cancel_reason: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Причина отмены.')
    cancel_reason_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор причины отмены отправления.', json_schema_extra={'format': 'int64'})
    cancellation_initiator: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Инициатор отмены:\n- `Продавец`,\n- `Клиент`,\n- `Покупатель`,\n- `Ozon`,\n- `Система`,\n- `Служба доставки`.\n')
    cancellation_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип отмены:\n- `seller` — отменено продавцом;\n- `client` или `customer` — отменено покупателем;\n- `ozon` — отменено Ozon;\n- `system` — отменено системой;\n- `delivery` — отменено службой доставки.\n')
    cancelled_after_ship: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если отмена произошла после сборки отправления.\n')


class OzonPostingV4PostingFbsUnfulfilledListResponsePostingsCustomer(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListResponse.Postings.Customer'
    'Информация о покупателе.'
    address: OzonPostingV4PostingFbsUnfulfilledListResponsePostingsCustomerAddress = Field(_OPTIONAL_FIELD_DEFAULT)
    customer_email: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Электронная почта покупателя.')
    customer_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор покупателя.', json_schema_extra={'format': 'int64'})
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Имя покупателя.')
    phone: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Подменный контактный телефон покупателя.')


class OzonPostingV4PostingFbsUnfulfilledListResponsePostingsCustomerAddress(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListResponse.Postings.Customer.Address'
    'Информация об адресе доставки.'
    address_tail: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Адрес в текстовом формате.')
    city: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Город доставки.')
    comment: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Комментарий к заказу.')
    country: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Страна доставки.')
    district: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Район доставки.')
    latitude: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Широта.', json_schema_extra={'format': 'double'})
    longitude: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Долгота.', json_schema_extra={'format': 'double'})
    provider_pvz_code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Код пункта выдачи заказов 3PL-провайдера.')
    pvz_code: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Код пункта выдачи заказов.', json_schema_extra={'format': 'int64'})
    region: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Регион доставки.')
    zip_code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Почтовый индекс получателя.')


class OzonPostingV4PostingFbsUnfulfilledListResponsePostingsContainer(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListResponse.Postings.Container'
    'Информация о грузоместе.'
    cargo_type: OzonPostingV4PostingFbsUnfulfilledListResponsePostingsContainerCargoTypeEnum = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип грузоместа.')
    container_date: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата создания грузоместа в часовом поясе склада.')
    container_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор грузоместа.', json_schema_extra={'format': 'int64'})
    container_number: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Порядковый номер грузоместа.', json_schema_extra={'format': 'int32'})


class OzonPostingV4PostingFbsUnfulfilledListResponsePostingsContainerCargoTypeEnum(StrEnum):
    'Тип грузоместа: \n  - `BOX` — коробка;\n  - `PALLET` — палета.\n'
    BOX = 'BOX'
    PALLET = 'PALLET'


class OzonPostingV4PostingFbsUnfulfilledListResponsePostingsDeliveryMethod(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListResponse.Postings.DeliveryMethod'
    'Информация о способе доставки.'
    id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор способа доставки.', json_schema_extra={'format': 'int64'})
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название способа доставки.')
    tpl_provider: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Служба доставки.')
    tpl_provider_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор службы доставки.', json_schema_extra={'format': 'int64'})
    warehouse: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название склада.')
    warehouse_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор склада.', json_schema_extra={'format': 'int64'})


class OzonPostingV4PostingFbsUnfulfilledListResponsePostingsExternalOrder(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListResponse.Postings.ExternalOrder'
    'Информация о заказе с внешней платформы.'
    is_external: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если заказ с внешней платформы.\n')
    platform_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название платформы, с которой сделали заказ.')


class OzonPostingV4PostingFbsUnfulfilledListResponsePostingsFinancialData(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListResponse.Postings.FinancialData'
    'Информация о стоимости товара, размере скидки, выплате и комиссии.'
    cluster_from: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Код региона, откуда отправляется заказ.')
    cluster_to: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Код региона, куда доставляется заказ.')
    products: list[OzonPostingV4PostingFbsUnfulfilledListResponsePostingsFinancialDataProducts] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список товаров в заказе.')


class OzonPostingV4PostingFbsUnfulfilledListResponsePostingsFinancialDataProducts(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListResponse.Postings.FinancialData.Products'
    actions: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список акций.')
    commission: OzonPostingV4PostingFbsUnfulfilledListResponsePostingsFinancialDataProductsCommission = Field(_OPTIONAL_FIELD_DEFAULT)
    customer_price: OzonMoneyPostingMoney = Field(_OPTIONAL_FIELD_DEFAULT)
    old_price: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Цена до учёта скидок. На карточке товара отображается зачёркнутой.', json_schema_extra={'format': 'double'})
    payout: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Выплата продавцу.', json_schema_extra={'format': 'double'})
    price: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Цена товара с учётом акций, кроме акций за счёт Ozon.', json_schema_extra={'format': 'double'})
    product_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор товара в системе Ozon — SKU.', json_schema_extra={'format': 'int64'})
    quantity: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество товара в отправлении.', json_schema_extra={'format': 'int64'})
    total_discount_percent: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Процент скидки.', json_schema_extra={'format': 'double'})
    total_discount_value: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Сумма скидки.', json_schema_extra={'format': 'double'})


class OzonPostingV4PostingFbsUnfulfilledListResponsePostingsFinancialDataProductsCommission(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListResponse.Postings.FinancialData.Products.Commission'
    'Комиссия за товар.'
    amount: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Размер комиссии за товар.', json_schema_extra={'format': 'double'})
    currency: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Код валюты, в которой рассчитывалась комиссия.')
    percent: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Процент комиссии.', json_schema_extra={'format': 'int64'})


class OzonMoneyPostingMoney(OzonFbsModel):
    __openapi_name__ = 'money.postingMoney'
    'Цена товара.'
    amount: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Сумма.')
    currency: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Валюта.')


class OzonPostingV4PostingFbsUnfulfilledListResponsePostingsLegalInfo(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListResponse.Postings.LegalInfo'
    'Юридическая информация о покупателе.'
    company_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название компании.')
    inn: str = Field(_OPTIONAL_FIELD_DEFAULT, description='ИНН.')
    kpp: str = Field(_OPTIONAL_FIELD_DEFAULT, description='КПП.')


class OzonPostingV4PostingFbsUnfulfilledListResponsePostingsOptional(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListResponse.Postings.Optional'
    'Список товаров с дополнительными характеристиками.'
    products_with_possible_mandatory_mark: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список товаров с возможной маркировкой.')


class OzonPostingV4PostingFbsUnfulfilledListResponsePostingsProducts(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListResponse.Postings.Products'
    imei: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список IMEI мобильных устройств.')
    is_blr_traceable: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если товар отслеживаемый.\n')
    is_marketplace_buyout: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если Ozon выкупил товар.\n\n[Подробнее о выкупе товаров в Базе знаний продавца](https://seller-edu.ozon.ru/commissions-tariffs/commissions-tariffs-ozon/prodaji-tovarov-v-eaes-i-drugie-strany#какие-товары-выкупает-ozon)\n')
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название товара.')
    offer_id: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор товара в системе продавца — артикул.')
    price: OzonMoneyPostingMoney = Field(_OPTIONAL_FIELD_DEFAULT)
    product_color: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Цвет товара.')
    quantity: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество товара в отправлении.', json_schema_extra={'format': 'int32'})
    sku: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор товара в системе Ozon — SKU.', json_schema_extra={'format': 'int64'})
    weight: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Вес товара в упаковке.', json_schema_extra={'format': 'double'})


class OzonPostingV4PostingFbsUnfulfilledListResponsePostingsRequirements(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListResponse.Postings.Requirements'
    'Товары, для которых нужна дополнительная информация.\n\nЧтобы перевести отправление в следующий статус, передайте:\n- страну-изготовителя; \n- номер грузовой таможенной декларации (ГТД);\n- регистрационный номер партии товара (РНПТ);\n- маркировку «Честный знак»;\n- другие маркировки;\n- вес.\n'
    products_requiring_change_country: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список идентификаторов товаров (SKU), для которых нужно изменить страну-изготовителя. Чтобы изменить страну-изготовителя, используйте методы [/v2/posting/fbs/product/country/list](#operation/PostingAPI_ListCountryProductFbsPostingV2) и [/v2/posting/fbs/product/country/set](#operation/PostingAPI_SetCountryProductFbsPostingV2).')
    products_requiring_country: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список идентификаторов товаров (SKU), для которых нужно передать информацию о стране-изготовителе.\n\nДля сборки отправления передайте информацию о стране-изготовителе для всех перечисленных товаров методом [/v2/posting/fbs/product/country/set](#operation/PostingAPI_SetCountryProductFbsPostingV2).\n')
    products_requiring_gtd: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список идентификаторов товаров (SKU), для которых нужно передать номера грузовой таможенной декларации (ГТД).\n\nДо сборки отправления передайте для всех перечисленных товаров номер грузовой таможенной декларации или информацию о том, \nчто номера нет, методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).\n')
    products_requiring_imei: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список идентификаторов товаров, для которых нужно передать IMEI.')
    products_requiring_jw_uin: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список товаров, для которых нужно передать уникальный идентификационный номер (УИН) ювелирного изделия.\n\nДо сборки отправления передайте для всех перечисленных товаров УИН методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).\n')
    products_requiring_mandatory_mark: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список идентификаторов товаров (SKU), для которых нужно передать маркировку «Честный знак».\n\nДо сборки отправления передайте для всех перечисленных товаров маркировку «Честный знак» методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).\n')
    products_requiring_rnpt: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список идентификаторов товаров (SKU), для которых нужно передать регистрационный номер партии товара (РНПТ).\n\nДо сборки отправления передайте для всех перечисленных товаров РНПТ методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).\n')
    products_requiring_weight: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список товаров, для которых нужно передать вес.')


class OzonPostingV4PostingFbsUnfulfilledListResponsePostingsSortingCenter(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListResponse.Postings.SortingCenter'
    'Информация о сортировочном центре, в который нужно привезти отправление. Для `integration_type_flow = hybrid_3pl_tracking`.\nЕсли значение `null`, информацию получить не удалось.\n'
    code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Код сортировочного центра.')
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название сортировочного центра.')


class OzonPostingV4PostingFbsUnfulfilledListResponsePostingsTariffication(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListResponse.Postings.Tariffication'
    'Информация по тарификации отгрузки.'
    current_tariff_charge: OzonMoneyMoneyCurrentTariffCharge = Field(_OPTIONAL_FIELD_DEFAULT)
    current_tariff_min_charge: OzonMoneyMoneyCurrentTariffMinCharge = Field(_OPTIONAL_FIELD_DEFAULT)
    current_tariff_rate: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Процент тарификации.', json_schema_extra={'format': 'double'})
    current_tariff_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип тарификации — скидка или надбавка.')
    next_tariff_charge: OzonMoneyMoneyNextTariffCharge = Field(_OPTIONAL_FIELD_DEFAULT)
    next_tariff_min_charge: OzonMoneyMoneyNextTariffMinCharge = Field(_OPTIONAL_FIELD_DEFAULT)
    next_tariff_rate: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Процент, по которому будет тарифицироваться отправление через время из параметра `next_tariff_starts_at`.', json_schema_extra={'format': 'double'})
    next_tariff_starts_at: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время, когда начнёт применяться новый тариф.', json_schema_extra={'format': 'date-time'})
    next_tariff_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип тарификации через время из параметра `next_tariff_starts_at` — скидка или надбавка.')


class OzonMoneyMoneyCurrentTariffCharge(OzonFbsModel):
    __openapi_name__ = 'money.Money.Current_tariff_charge'
    'Скидка или надбавка.'
    amount: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Сумма.')
    currency: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Валюта.')


class OzonMoneyMoneyCurrentTariffMinCharge(OzonFbsModel):
    __openapi_name__ = 'money.Money.Current_tariff_min_charge'
    'Минимальная скидка или надбавка.'
    amount: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Сумма.')
    currency: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Валюта.')


class OzonMoneyMoneyNextTariffCharge(OzonFbsModel):
    __openapi_name__ = 'money.Money.Next_tariff_charge'
    'Скидка или надбавка через время из параметра `next_tariff_starts_at`.'
    amount: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Сумма.')
    currency: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Валюта.')


class OzonMoneyMoneyNextTariffMinCharge(OzonFbsModel):
    __openapi_name__ = 'money.Money.Next_tariff_min_charge'
    'Минимальная скидка или надбавка через время из параметра `next_tariff_starts_at`.'
    amount: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Сумма.')
    currency: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Валюта.')


class OzonPostingV4PostingFbsUnfulfilledListResponsePostingsTarifficationStep(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsUnfulfilledListResponse.Postings.TarifficationStep'
    min_charge: OzonMoneyMoneyCurrentTariffMinCharge = Field(_OPTIONAL_FIELD_DEFAULT)
    tariff_charge: OzonMoneyMoneyCurrentTariffCharge = Field(_OPTIONAL_FIELD_DEFAULT)
    tariff_deadline_at: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время окончания этапа тарификации. После этой даты автоматически применяется следующий этап.', json_schema_extra={'format': 'date-time'})
    tariff_rate: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Процент скидки или надбавки.', json_schema_extra={'format': 'double'})
    tariff_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип тарификации.')


class OzonRpcStatus(OzonFbsModel):
    __openapi_name__ = 'rpcStatus'
    code: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Код ошибки.', json_schema_extra={'format': 'int32'})
    details: list[OzonProtobufAny] = Field(_OPTIONAL_FIELD_DEFAULT, description='Дополнительная информация об ошибке.')
    message: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Описание ошибки.')


class OzonProtobufAny(OzonFbsModel):
    __openapi_name__ = 'protobufAny'
    typeUrl: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип протокола передачи данных.')
    value: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Значение ошибки.', json_schema_extra={'format': 'byte'})


class OzonPostingV4PostingFbsListRequest(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListRequest'
    cursor: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Указатель для выборки следующих данных.')
    filter: OzonPostingV4PostingFbsListRequestFilter = Field(...)
    limit: int = Field(..., description='Количество значений в ответе.', ge=1, le=100, json_schema_extra={'format': 'int64'})
    sort_dir: OzonPostingV4PostingFbsListRequestSortDirEnum = Field(_OPTIONAL_FIELD_DEFAULT)
    translit: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, чтобы включить транслитерацию адреса из кириллицы в латиницу.\n')
    with_: OzonPostingV4PostingFbsListRequestWith = Field(_OPTIONAL_FIELD_DEFAULT, alias='with')


class OzonPostingV4PostingFbsListRequestFilter(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListRequest.Filter'
    'Фильтр.'
    delivery_method_ids: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор способа доставки. Можно получить с помощью метода [/v1/delivery-method/list](#operation/WarehouseAPI_DeliveryMethodList).\n', max_length=1000)
    integration_type_flow: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Процесс обработки отправления:\n- `ozon` — доставка силами Ozon;\n- `aggregator` — доставка внешней службой, Ozon регистрирует заказ;\n- `non_integrated` — доставка силами продавца;\n- `3pl_tracking` — доставка внешней службой, продавец регистрирует заказ;\n- `hybrid` — гибридная интеграция;\n- `hybrid_aggregator` — гибридная интеграция с доставкой внешней службой, Ozon регистрирует заказ;\n- `hybrid_non_integrated` — гибридная интеграция с доставкой силами продавца;\n- `hybrid_3pl_tracking` — гибридная интеграция с доставкой внешней службой, продавец регистрирует заказ;\n- `click_and_collect` — бронирование в магазине партнёра;\n- `FBP` — доставка с партнёрских складов Ozon.\n')
    is_blr_traceable: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если товар отслеживаемый.\n')
    last_changed_status_date: OzonPostingV4PostingFbsListRequestFilterLastChangedStatusDate = Field(_OPTIONAL_FIELD_DEFAULT)
    order_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор заказа.', json_schema_extra={'format': 'int64'})
    order_numbers: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Номера заказов, к которым относятся отправления.', max_length=100)
    provider_ids: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор службы доставки. Можно получить с помощью метода [/v1/delivery-method/list](#operation/WarehouseAPI_DeliveryMethodList).\n', max_length=1000)
    since: str = Field(..., description='Дата начала периода, за который нужно получить список отправлений.', json_schema_extra={'format': 'date-time'})
    statuses: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Статус отправления:\n- `awaiting_registration` — ожидает регистрации;\n- `acceptance_in_progress` — идёт приёмка;\n- `awaiting_approve` — ожидает подтверждения;\n- `awaiting_packaging` — ожидает упаковки;\n- `awaiting_deliver` — ожидает отгрузки;\n- `arbitration` — арбитраж;\n- `client_arbitration` — клиентский арбитраж доставки;\n- `delivering` — доставляется;\n- `driver_pickup` — у водителя;\n- `delivered` — доставлено;\n- `cancelled` — отменено;\n- `not_accepted` — не принято на сортировочном центре;\n- `sent_by_seller` – отправлено продавцом.\n')
    to: str = Field(..., description='Дата конца периода, за который нужно получить список отправлений.', json_schema_extra={'format': 'date-time'})
    warehouse_ids: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор склада. Можно получить с помощью метода [/v1/warehouse/list](#operation/WarehouseAPI_WarehouseList).', max_length=1000)


class OzonPostingV4PostingFbsListRequestFilterLastChangedStatusDate(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListRequest.Filter.LastChangedStatusDate'
    'Период, в который последний раз изменялся статус у отправлений.'
    from_: str = Field(_OPTIONAL_FIELD_DEFAULT, alias='from', description='Дата начала периода.', json_schema_extra={'format': 'date-time'})
    to: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата окончания периода.', json_schema_extra={'format': 'date-time'})


class OzonPostingV4PostingFbsListRequestSortDirEnum(StrEnum):
    'Направление сортировки:\n- `ASC` — по возрастанию;\n- `DESC` — по убыванию.\n'
    ASC = 'ASC'
    DESC = 'DESC'


class OzonPostingV4PostingFbsListRequestWith(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListRequest.With'
    'Дополнительные поля, которые нужно добавить в ответ.'
    analytics_data: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, чтобы добавить в ответ данные аналитики.\n')
    barcodes: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, чтобы добавить в ответ штрихкоды отправления.\n')
    financial_data: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, чтобы добавить в ответ финансовые данные.\n')
    legal_info: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, чтобы добавить в ответ юридическую информацию.\n')


class OzonPostingV4PostingFbsListResponse(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListResponse'
    cursor: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Указатель для выборки следующих данных.')
    has_next: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если в ответе вернулись не все отправления.\n')
    postings: list[OzonPostingV4PostingFbsListResponsePostings] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список отправлений.')


class OzonPostingV4PostingFbsListResponsePostings(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListResponse.Postings'
    addressee: OzonPostingV4PostingFbsListResponsePostingsAddressee = Field(_OPTIONAL_FIELD_DEFAULT)
    analytics_data: OzonPostingV4PostingFbsListResponsePostingsAnalyticsData = Field(_OPTIONAL_FIELD_DEFAULT)
    available_actions: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Доступные действия и информация об отправлении:\n- `arbitration` — открыть спор;\n- `awaiting_delivery` — перевести в статус «Ожидает отгрузки»;\n- `can_create_chat` — начать чат с покупателем;\n- `cancel` — отменить отправление;\n- `click_track_number` — просмотреть по трек-номеру историю изменения статусов в личном кабинете;\n- `customer_phone_available` — телефон покупателя;\n- `has_weight_products` — весовые товары в отправлении;\n- `hide_region_and_city` — скрыть регион и город покупателя в отчёте;\n- `invoice_get` —  получить информацию из счёта-фактуры;\n- `invoice_send` — создать счёт-фактуру;\n- `invoice_update` — отредактировать счёт-фактуру;\n- `label_download_big` — скачать большую этикетку;\n- `label_download_small` — скачать маленькую этикетку;\n- `label_download` — скачать этикетку;\n- `non_int_delivered` — перевести в статус «Условно доставлен»;\n- `non_int_delivering` — перевести в статус «Доставляется»;\n- `non_int_last_mile` — перевести в статус «Курьер в пути»;\n- `product_cancel` — отменить часть товаров в отправлении;\n- `set_cutoff` — укажите дату отгрузки методом [/v1/posting/cutoff/set](#operation/PostingAPI_SetPostingCutoff) не позже даты в параметре `shipment_date`;\n- `set_timeslot` — изменить время доставки покупателю;\n- `set_track_number` — указать или изменить трек-номер;\n- `ship_async_in_process` — отправление собирается;\n- `ship_async_retry` — собрать отправление повторно после ошибки сборки;\n- `ship_async` — собрать отправление;\n- `ship_with_additional_info` — заполните дополнительную информацию методом [/v6/fbs/posting/product/exemplar/set](https://docs.ozon.ru/api/seller/#operation/PostingAPI_FbsPostingProductExemplarSetV6);\n- `ship` — собрать отправление;\n- `update_cis` — изменить дополнительную информацию.\n')
    barcodes: OzonPostingV4PostingFbsListResponsePostingsBarcodes = Field(_OPTIONAL_FIELD_DEFAULT)
    cancellation: OzonPostingV4PostingFbsListResponsePostingsCancellation = Field(_OPTIONAL_FIELD_DEFAULT)
    customer: OzonPostingV4PostingFbsListResponsePostingsCustomer = Field(_OPTIONAL_FIELD_DEFAULT)
    container: OzonPostingV4PostingFbsListResponsePostingsContainer = Field(_OPTIONAL_FIELD_DEFAULT)
    container_sort_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип сортировки грузоместа:\n  - `SORT` — сортируемый;\n  - `NON-SORT` — несортируемый.\n')
    delivering_date: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата передачи отправления в доставку.', json_schema_extra={'format': 'date-time'})
    delivery_method: OzonPostingV4PostingFbsListResponsePostingsDeliveryMethod = Field(_OPTIONAL_FIELD_DEFAULT)
    delivery_schema: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Схема доставки:\n- `SDS` — идентификатор единого SKU;\n- `FBO` — идентификатор товара, который продаётся со склада Ozon;\n- `FBS` — идентификатор товара, который продаётся со склада FBS;\n- `Crossborder` — идентификатор товара, который продаётся из-за границы.\n')
    destination_place_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор места назначения.', json_schema_extra={'format': 'int64'})
    destination_place_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название места назначения.')
    external_order: OzonPostingV4PostingFbsListResponsePostingsExternalOrder = Field(_OPTIONAL_FIELD_DEFAULT)
    financial_data: OzonPostingV4PostingFbsListResponsePostingsFinancialData = Field(_OPTIONAL_FIELD_DEFAULT)
    in_process_at: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время начала обработки отправления.', json_schema_extra={'format': 'date-time'})
    is_click_and_collect: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если отправление доставляется методом «Самовывоз из магазина».\n')
    is_express: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если использовалась быстрая доставка Ozon Express.\n')
    is_multibox: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак, что в отправлении есть многокоробочный товар и нужно передать количество коробок для него:\n\n- `true` — до сборки передайте количество коробок через метод [/v3/posting/multiboxqty/set](#operation/PostingAPI_PostingMultiBoxQtySetV3).\n- `false` — отправление собрано с указанием количества коробок в параметре `multi_box_qty` или в отправлении нет многокоробочного товара.\n')
    is_presortable: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если товар — пересорт.\n')
    integration_type_flow: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Процесс обработки отправления:\n- `ozon` — доставка силами Ozon;\n- `aggregator` — доставка внешней службой, Ozon регистрирует заказ;\n- `non_integrated` — доставка силами продавца;\n- `3pl_tracking` — доставка внешней службой, продавец регистрирует заказ;\n- `hybrid` — гибридная интеграция;\n- `hybrid_aggregator` — гибридная интеграция с доставкой внешней службой, Ozon регистрирует заказ;\n- `hybrid_non_integrated` — гибридная интеграция с доставкой силами продавца;\n- `hybrid_3pl_tracking` — гибридная интеграция с доставкой внешней службой, продавец регистрирует заказ;\n- `click_and_collect` — бронирование в магазине партнёра;\n- `FBP` — доставка с партнёрских складов Ozon.\n')
    legal_info: OzonPostingV4PostingFbsListResponsePostingsLegalInfo = Field(_OPTIONAL_FIELD_DEFAULT)
    multi_box_qty: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество коробок, в которые упакован товар.', json_schema_extra={'format': 'int32'})
    optional: OzonPostingV4PostingFbsListResponsePostingsOptional = Field(_OPTIONAL_FIELD_DEFAULT)
    order_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор заказа, к которому относится отправление.', json_schema_extra={'format': 'int64'})
    order_number: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер заказа, к которому относится отправление.')
    parent_posting_number: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер родительского отправления, в результате разделения которого появилось текущее.')
    pickup_code_verified_at: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время успешной валидации кода курьера. Проверьте код курьера методом [/v1/posting/fbs/pick-up-code/verify](#operation/PostingAPI_PostingFBSPickupCodeVerify).', json_schema_extra={'format': 'date-time'})
    posting_number: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер отправления.')
    products: list[OzonPostingV4PostingFbsListResponsePostingsProducts] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список товаров в отправлении.')
    prr_option: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Код услуги погрузочно-разгрузочных работ:\n- `lift` — подъём на лифте;\n- `stairs` — подъём по лестнице;\n- `none` — покупатель отказался от услуги, поднимать товары не нужно;\n- `delivery_default` — доставка включена в стоимость, по условиям оферты нужно доставить товар на этаж.\n\nДля КГТ-отправлений с доставкой силами продавца или интегрированной службой.\n')
    quantum_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор эконом-товара.', json_schema_extra={'format': 'int64'})
    require_blr_traceable_attrs: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если нужно заполнить атрибуты отслеживаемости.\n')
    requirements: OzonPostingV4PostingFbsListResponsePostingsRequirements = Field(_OPTIONAL_FIELD_DEFAULT)
    shipment_date: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время, до которой нужно собрать отправление. Показываем рекомендованное время отгрузки. По истечении этого времени начнёт применяться новый тариф, информацию о нём получите в поле `tariffication`.', json_schema_extra={'format': 'date-time'})
    shipment_date_without_delay: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время отгрузки без просрочки.', json_schema_extra={'format': 'date-time'})
    sorting_center: OzonPostingV4PostingFbsListResponsePostingsSortingCenter = Field(_OPTIONAL_FIELD_DEFAULT)
    status: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Статус отправления:\n- `acceptance_in_progress` — идёт приёмка;\n- `arbitration` — арбитраж;\n- `awaiting_approve` — ожидает подтверждения;\n- `awaiting_deliver` — ожидает отгрузки;\n- `awaiting_packaging` — ожидает упаковки;\n- `awaiting_registration` — ожидает регистрации;\n- `awaiting_verification` — создано;\n- `cancelled` — отменено;\n- `cancelled_from_split_pending` — отменено из-за разделения отправления;\n- `client_arbitration` — клиентский арбитраж доставки;\n- `delivering` — доставляется;\n- `driver_pickup` — у водителя;\n- `not_accepted` — не принято на сортировочном центре.\n')
    substatus: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Подстатус отправления:\n- `posting_acceptance_in_progress`— идёт приёмка;\n- `posting_in_arbitration` — арбитраж;\n- `posting_created` — создано;\n- `posting_in_carriage` — в перевозке;\n- `posting_not_in_carriage` — не добавлено в перевозку;\n- `posting_registered` — зарегистрировано;\n- `posting_transferring_to_delivery`, если `status=awaiting_deliver` — передаётся в доставку;\n- `posting_awaiting_passport_data` — ожидает паспортных данных;\n- `posting_created` — создано;\n- `posting_awaiting_registration` — ожидает регистрации;\n- `posting_registration_error` — ошибка регистрации;\n- `posting_transferring_to_delivery`, если `status=awaiting_registration` — передаётся курьеру;\n- `posting_split_pending` — создано;\n- `posting_canceled` — отменено;\n- `posting_in_client_arbitration` — клиентский арбитраж доставки;\n- `posting_delivered` — доставлено;\n- `posting_received` — получено;\n- `posting_conditionally_delivered` — условно доставлено;\n- `posting_in_courier_service` — курьер в пути;\n- `posting_in_pickup_point` — в пункте выдачи;\n- `posting_on_way_to_city` — в пути в ваш город;\n- `posting_on_way_to_pickup_point` — в пути в пункт выдачи;\n- `posting_returned_to_warehouse` — возвращено на склад;\n- `posting_transferred_to_courier_service` — передаётся в службу доставки;\n- `posting_driver_pick_up` — у водителя;\n- `posting_not_in_sort_center` — не принято на сортировочном центре;\n- `ship_failed` — сборка не удалась.\n')
    tariffication: OzonPostingV4PostingFbsListResponsePostingsTariffication = Field(_OPTIONAL_FIELD_DEFAULT)
    tariffication_steps: list[OzonPostingV4PostingFbsListResponsePostingsTarifficationStep] = Field(_OPTIONAL_FIELD_DEFAULT, description='Этапы тарификации.')
    tpl_integration_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип интеграции со службой доставки:\n  - `ozon` — доставка службой Ozon;\n  - `3pl_tracking` — доставка интегрированной службой;\n  - `non_integrated` — доставка сторонней службой;\n  - `aggregator` — доставка через партнёрскую доставку Ozon;\n  - `hybryd` — схема доставки Почты России.\n')
    tracking_number: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Трек-номер отправления.')
    volume_weight: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Объёмный вес товара.', json_schema_extra={'format': 'double'})


class OzonPostingV4PostingFbsListResponsePostingsAddressee(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListResponse.Postings.Addressee'
    'Контактные данные получателя.'
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Имя получателя.')


class OzonPostingV4PostingFbsListResponsePostingsAnalyticsData(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListResponse.Postings.AnalyticsData'
    'Данные аналитики.'
    city: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Город доставки. Только для отправлений rFBS и продавцов из СНГ.')
    client_delivery_date_begin: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время начала доставки. Только для отправлений, оформленных через [Ozon Доставку](#tag/OzonLogistics).', json_schema_extra={'format': 'date-time'})
    client_delivery_date_end: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Ожидаемая дата, до которой заказ будет доставлен. Только для отправлений, оформленных через [Ozon Доставку](#tag/OzonLogistics).', json_schema_extra={'format': 'date-time'})
    delivery_date_begin: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время начала доставки.', json_schema_extra={'format': 'date-time'})
    delivery_date_end: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время конца доставки.', json_schema_extra={'format': 'date-time'})
    delivery_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Способ доставки.')
    is_legal: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если получатель юридическое лицо.\n')
    is_premium: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если у получателя есть подписка Premium.\n')
    payment_type_group_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Способ оплаты: \n- `картой онлайн`;\n- `карта Ozon Банка`;\n- `автосписание с карты Ozon Банка при выдаче`;\n- `сохранённой картой при получении`;\n- `Система Быстрых Платежей`;\n- `Ozon Рассрочка`;\n- `оплата на расчётный счёт`;\n- `SberPay`;\n- `предоплата на стороне внешнего продавца`.\n')
    region: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Регион доставки. Только для отправлений rFBS.')
    tpl_provider: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Служба доставки.')
    tpl_provider_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор службы доставки.', json_schema_extra={'format': 'int64'})
    warehouse: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название склада отправки заказа.')
    warehouse_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор склада.', json_schema_extra={'format': 'int64'})


class OzonPostingV4PostingFbsListResponsePostingsBarcodes(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListResponse.Postings.Barcodes'
    'Штрихкоды отправления.'
    lower_barcode: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Нижний штрихкод на маркировке отправления.')
    upper_barcode: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Верхний штрихкод на маркировке отправления.')


class OzonPostingV4PostingFbsListResponsePostingsCancellation(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListResponse.Postings.Cancellation'
    'Информация об отмене.'
    affect_cancellation_rating: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если отмена влияет на рейтинг продавца.\n')
    cancel_reason: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Причина отмены.')
    cancel_reason_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор причины отмены отправления.', json_schema_extra={'format': 'int64'})
    cancellation_initiator: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Инициатор отмены:\n- `Продавец`,\n- `Клиент`,\n- `Покупатель`,\n- `Ozon`,\n- `Система`,\n- `Служба доставки`.\n')
    cancellation_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип отмены:\n- `seller` — отменено продавцом;\n- `client` или `customer` — отменено покупателем;\n- `ozon` — отменено Ozon;\n- `system` — отменено системой;\n- `delivery` — отменено службой доставки.\n')
    cancelled_after_ship: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если отмена произошла после сборки отправления.\n')


class OzonPostingV4PostingFbsListResponsePostingsCustomer(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListResponse.Postings.Customer'
    'Информация о покупателе.'
    address: OzonPostingV4PostingFbsListResponsePostingsCustomerAddress = Field(_OPTIONAL_FIELD_DEFAULT)
    customer_email: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Электронная почта покупателя.')
    customer_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор покупателя.', json_schema_extra={'format': 'int64'})
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Имя покупателя.')
    phone: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Подменный контактный телефон покупателя.')


class OzonPostingV4PostingFbsListResponsePostingsCustomerAddress(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListResponse.Postings.Customer.Address'
    'Адрес доставки.'
    address_tail: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Адрес в текстовом формате.')
    city: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Город доставки.')
    comment: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Комментарий к заказу.')
    country: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Страна доставки.')
    district: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Район доставки.')
    latitude: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Широта.', json_schema_extra={'format': 'double'})
    longitude: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Долгота.', json_schema_extra={'format': 'double'})
    provider_pvz_code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Код пункта выдачи заказов 3PL-провайдера.')
    pvz_code: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Код пункта выдачи заказов.', json_schema_extra={'format': 'int64'})
    region: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Регион доставки.')
    zip_code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Почтовый индекс получателя.')


class OzonPostingV4PostingFbsListResponsePostingsContainer(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListResponse.Postings.Container'
    'Информация о грузоместе.'
    cargo_type: OzonPostingV3FbsPostingContainerCargoTypeEnum = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип грузоместа.')
    container_date: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата создания грузоместа в часовом поясе склада.')
    container_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор грузоместа.', json_schema_extra={'format': 'int64'})
    container_number: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Порядковый номер грузоместа.', json_schema_extra={'format': 'int32'})


class OzonPostingV3FbsPostingContainerCargoTypeEnum(StrEnum):
    'Тип грузоместа: \n  - `BOX` — коробка;\n  - `PALLET` — палета.\n'
    BOX = 'BOX'
    PALLET = 'PALLET'


class OzonPostingV4PostingFbsListResponsePostingsDeliveryMethod(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListResponse.Postings.DeliveryMethod'
    'Информация о способе доставки.'
    id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор способа доставки.', json_schema_extra={'format': 'int64'})
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название способа доставки.')
    tpl_provider: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Служба доставки.')
    tpl_provider_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор службы доставки.', json_schema_extra={'format': 'int64'})
    warehouse: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название склада.')
    warehouse_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор склада.', json_schema_extra={'format': 'int64'})


class OzonPostingV4PostingFbsListResponsePostingsExternalOrder(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListResponse.Postings.ExternalOrder'
    'Информация о заказе с внешней платформы.'
    is_external: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если заказ с внешней платформы.\n')
    platform_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название платформы, с которой сделали заказ.')


class OzonPostingV4PostingFbsListResponsePostingsFinancialData(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListResponse.Postings.FinancialData'
    'Информация о стоимости товара, размере скидки, выплате и комиссии.'
    cluster_from: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Код региона, откуда отправляется заказ.')
    cluster_to: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Код региона, куда доставляется заказ.')
    products: list[OzonPostingV4PostingFbsListResponsePostingsFinancialDataProducts] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список товаров в заказе.')


class OzonPostingV4PostingFbsListResponsePostingsFinancialDataProducts(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListResponse.Postings.FinancialData.Products'
    actions: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список акций.')
    commission: OzonPostingV4PostingFbsListResponsePostingsFinancialDataProductsCommission = Field(_OPTIONAL_FIELD_DEFAULT)
    customer_price: OzonMoneyPostingMoney = Field(_OPTIONAL_FIELD_DEFAULT)
    old_price: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Цена до учёта скидок. На карточке товара отображается зачёркнутой.', json_schema_extra={'format': 'double'})
    payout: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Выплата продавцу.', json_schema_extra={'format': 'double'})
    price: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Цена товара с учётом акций, кроме акций за счёт Ozon.', json_schema_extra={'format': 'double'})
    product_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор товара в системе Ozon — SKU.', json_schema_extra={'format': 'int64'})
    quantity: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество товара в отправлении.', json_schema_extra={'format': 'int64'})
    total_discount_percent: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Процент скидки.', json_schema_extra={'format': 'double'})
    total_discount_value: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Сумма скидки.', json_schema_extra={'format': 'double'})


class OzonPostingV4PostingFbsListResponsePostingsFinancialDataProductsCommission(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListResponse.Postings.FinancialData.Products.Commission'
    'Комиссия за товар.'
    amount: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Размер комиссии за товар.', json_schema_extra={'format': 'double'})
    currency: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Код валюты, в которой рассчитывалась комиссия.')
    percent: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Процент комиссии.', json_schema_extra={'format': 'int64'})


class OzonPostingV4PostingFbsListResponsePostingsLegalInfo(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListResponse.Postings.LegalInfo'
    'Юридическая информация о покупателе.'
    company_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название компании.')
    inn: str = Field(_OPTIONAL_FIELD_DEFAULT, description='ИНН.')
    kpp: str = Field(_OPTIONAL_FIELD_DEFAULT, description='КПП.')


class OzonPostingV4PostingFbsListResponsePostingsOptional(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListResponse.Postings.Optional'
    'Список товаров с дополнительными характеристиками.'
    products_with_possible_mandatory_mark: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список товаров с возможной маркировкой.')


class OzonPostingV4PostingFbsListResponsePostingsProducts(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListResponse.Postings.Products'
    imei: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список IMEI мобильных устройств.')
    is_blr_traceable: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если товар отслеживаемый.\n')
    is_marketplace_buyout: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если Ozon выкупил товар.\n\n[Подробнее о выкупе товаров в Базе знаний продавца](https://seller-edu.ozon.ru/commissions-tariffs/commissions-tariffs-ozon/prodaji-tovarov-v-eaes-i-drugie-strany#какие-товары-выкупает-ozon)\n')
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название товара.')
    offer_id: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор товара в системе продавца — артикул.')
    price: OzonMoneyPostingMoney = Field(_OPTIONAL_FIELD_DEFAULT)
    product_color: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Цвет товара.')
    quantity: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество товара в отправлении.', json_schema_extra={'format': 'int32'})
    sku: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор товара в системе Ozon — SKU.', json_schema_extra={'format': 'int64'})
    weight: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Вес товара в упаковке.', json_schema_extra={'format': 'double'})


class OzonPostingV4PostingFbsListResponsePostingsRequirements(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListResponse.Postings.Requirements'
    'Товары, для которых нужна дополнительная информация.\n\nЧтобы перевести отправление в следующий статус, передайте:\n- страну-изготовителя; \n- номер грузовой таможенной декларации (ГТД);\n- регистрационный номер партии товара (РНПТ);\n- маркировку «Честный знак»;\n- другие маркировки;\n- вес.\n'
    products_requiring_change_country: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список идентификаторов товаров (SKU), для которых нужно изменить страну-изготовителя. Чтобы изменить страну-изготовителя, используйте методы [/v2/posting/fbs/product/country/list](#operation/PostingAPI_ListCountryProductFbsPostingV2) и [/v2/posting/fbs/product/country/set](#operation/PostingAPI_SetCountryProductFbsPostingV2).')
    products_requiring_country: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список идентификаторов товаров (SKU), для которых нужно передать информацию о стране-изготовителе.\n\nДля сборки отправления передайте информацию о стране-изготовителе для всех перечисленных товаров методом [/v2/posting/fbs/product/country/set](#operation/PostingAPI_SetCountryProductFbsPostingV2).\n')
    products_requiring_gtd: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список идентификаторов товаров (SKU), для которых нужно передать номера грузовой таможенной декларации (ГТД).\n\nДо сборки отправления передайте для всех перечисленных товаров номер грузовой таможенной декларации или информацию о том, \nчто номера нет, методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).\n')
    products_requiring_imei: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список идентификаторов товаров, для которых нужно передать IMEI.')
    products_requiring_jw_uin: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список товаров, для которых нужно передать уникальный идентификационный номер (УИН) ювелирного изделия.\n\nДо сборки отправления передайте для всех перечисленных товаров УИН методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).\n')
    products_requiring_mandatory_mark: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список идентификаторов товаров (SKU), для которых нужно передать маркировку «Честный знак».\n\nДо сборки отправления передайте для всех перечисленных товаров маркировку «Честный знак» методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).\n')
    products_requiring_rnpt: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список идентификаторов товаров (SKU), для которых нужно передать регистрационный номер партии товара (РНПТ).\n\nДо сборки отправления передайте для всех перечисленных товаров РНПТ методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).\n')
    products_requiring_weight: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список товаров, для которых нужно передать вес.')


class OzonPostingV4PostingFbsListResponsePostingsSortingCenter(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListResponse.Postings.SortingCenter'
    'Информация о сортировочном центре, в который нужно привезти отправление. Для `integration_type_flow = hybrid_3pl_tracking`.\nЕсли значение `null`, информацию получить не удалось.\n'
    code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Код сортировочного центра.')
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название сортировочного центра.')


class OzonPostingV4PostingFbsListResponsePostingsTariffication(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListResponse.Postings.Tariffication'
    'Информация по тарификации отгрузки.'
    current_tariff_charge: OzonMoneyMoneyCurrentTariffCharge = Field(_OPTIONAL_FIELD_DEFAULT)
    current_tariff_min_charge: OzonMoneyMoneyCurrentTariffMinCharge = Field(_OPTIONAL_FIELD_DEFAULT)
    current_tariff_rate: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Процент тарификации.', json_schema_extra={'format': 'double'})
    current_tariff_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип тарификации — скидка или надбавка.')
    next_tariff_charge: OzonMoneyMoneyNextTariffCharge = Field(_OPTIONAL_FIELD_DEFAULT)
    next_tariff_min_charge: OzonMoneyMoneyNextTariffMinCharge = Field(_OPTIONAL_FIELD_DEFAULT)
    next_tariff_rate: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Процент, по которому будет тарифицироваться отправление через время из параметра `next_tariff_starts_at`.', json_schema_extra={'format': 'double'})
    next_tariff_starts_at: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время, когда начнёт применяться новый тариф.', json_schema_extra={'format': 'date-time'})
    next_tariff_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип тарификации через время из параметра `next_tariff_starts_at` — скидка или надбавка.')


class OzonPostingV4PostingFbsListResponsePostingsTarifficationStep(OzonFbsModel):
    __openapi_name__ = 'posting.v4.PostingFbsListResponse.Postings.TarifficationStep'
    min_charge: OzonMoneyMoneyCurrentTariffMinCharge = Field(_OPTIONAL_FIELD_DEFAULT)
    tariff_charge: OzonMoneyMoneyCurrentTariffCharge = Field(_OPTIONAL_FIELD_DEFAULT)
    tariff_deadline_at: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время окончания этапа тарификации. После этой даты автоматически начинается следующий этап.', json_schema_extra={'format': 'date-time'})
    tariff_rate: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Процент скидки или надбавки.', json_schema_extra={'format': 'double'})
    tariff_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип тарификации.')


class OzonPostingv3GetFbsPostingRequest(OzonFbsModel):
    __openapi_name__ = 'postingv3GetFbsPostingRequest'
    posting_number: str = Field(..., description='Идентификатор отправления.')
    with_: OzonPostingv3FbsPostingWithParamsExamplars = Field(_OPTIONAL_FIELD_DEFAULT, alias='with')


class OzonPostingv3FbsPostingWithParamsExamplars(OzonFbsModel):
    __openapi_name__ = 'postingv3FbsPostingWithParamsExamplars'
    'Дополнительные поля, которые нужно добавить в ответ.'
    analytics_data: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Добавить в ответ данные аналитики.')
    barcodes: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Добавить в ответ штрихкоды отправления.')
    financial_data: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Добавить в ответ финансовые данные.')
    legal_info: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Добавить в ответ юридическую информацию.')
    product_exemplars: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Добавить в ответ данные о продуктах и их экземплярах.')
    related_postings: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Добавить в ответ номера связанных отправлений. Связанные отправления — те, на которое было разделено родительское отправление при сборке.\n')
    translit: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Выполнить транслитерацию возвращаемых значений.')


class OzonV3GetFbsPostingResponseV3(OzonFbsModel):
    __openapi_name__ = 'v3GetFbsPostingResponseV3'
    result: OzonV3FbsPostingDetail = Field(_OPTIONAL_FIELD_DEFAULT)


class OzonV3FbsPostingDetail(OzonFbsModel):
    __openapi_name__ = 'v3FbsPostingDetail'
    'Информация об отправлении.'
    additional_data: list[OzonV3AdditionalDataItem] = Field(_OPTIONAL_FIELD_DEFAULT)
    addressee: OzonV3Addressee = Field(_OPTIONAL_FIELD_DEFAULT)
    analytics_data: OzonV3FbsPostingAnalyticsData = Field(_OPTIONAL_FIELD_DEFAULT)
    available_actions: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Доступные действия и информация об отправлении:\n- `arbitration` — открыть спор;\n- `awaiting_delivery` — перевести в статус «Ожидает отгрузки»;\n- `can_create_chat` — начать чат с покупателем;\n- `cancel` — отменить отправление;\n- `click_track_number` — просмотреть по трек-номеру историю изменения статусов в личном кабинете;\n- `customer_phone_available` — телефон покупателя;\n- `has_weight_products` — весовые товары в отправлении;\n- `hide_region_and_city` — скрыть регион и город покупателя в отчёте;\n- `invoice_get` —  получить информацию из счёта-фактуры;\n- `invoice_send` — создать счёт-фактуру;\n- `invoice_update` — отредактировать счёт-фактуру;\n- `label_download_big` — скачать большую этикетку;\n- `label_download_small` — скачать маленькую этикетку;\n- `label_download` — скачать этикетку;\n- `non_int_delivered` — перевести в статус «Условно доставлен»;\n- `non_int_delivering` — перевести в статус «Доставляется»;\n- `non_int_last_mile` — перевести в статус «Курьер в пути»;\n- `product_cancel` — отменить часть товаров в отправлении;\n- `set_cutoff` — необходимо указать дату отгрузки, воспользуйтесь методом [/v1/posting/cutoff/set](#operation/PostingAPI_SetPostingCutoff);\n- `set_timeslot` — изменить время доставки покупателю;\n- `set_track_number` — указать или изменить трек-номер;\n- `ship_async_in_process` — отправление собирается;\n- `ship_async_retry` — собрать отправление повторно после ошибки сборки;\n- `ship_async` — собрать отправление;\n- `ship_with_additional_info` — необходимо заполнить дополнительную информацию;\n- `ship` — собрать отправление;\n- `update_cis` — изменить дополнительную информацию.\n')
    barcodes: OzonV3Barcodes = Field(_OPTIONAL_FIELD_DEFAULT)
    cancellation: OzonV3Cancellation = Field(_OPTIONAL_FIELD_DEFAULT)
    courier: OzonFbsPostingDetailCourier = Field(_OPTIONAL_FIELD_DEFAULT)
    customer: OzonV3Customer = Field(_OPTIONAL_FIELD_DEFAULT)
    container: OzonPostingV4PostingFbsListResponsePostingsContainer = Field(_OPTIONAL_FIELD_DEFAULT)
    container_sort_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип сортировки грузоместа:\n  - `SORT` — сортируемый;\n  - `NON-SORT` — несортируемый.\n')
    delivering_date: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата передачи отправления в доставку.', json_schema_extra={'format': 'date-time'})
    delivery_method: OzonV3DeliveryMethod = Field(_OPTIONAL_FIELD_DEFAULT)
    delivery_price: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Стоимость доставки.')
    external_order: OzonPostingV3FbsPostingDetailExternalOrder = Field(_OPTIONAL_FIELD_DEFAULT)
    fact_delivery_date: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата фактической передачи отправления в доставку.', json_schema_extra={'format': 'date-time'})
    financial_data: OzonV3PostingFinancialData = Field(_OPTIONAL_FIELD_DEFAULT)
    in_process_at: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время начала обработки отправления.', json_schema_extra={'format': 'date-time'})
    integration_type_flow: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Процесс обработки отправления:\n- `ozon` — доставка силами Ozon;\n- `aggregator` — доставка внешней службой, Ozon регистрирует заказ;\n- `non_integrated` — доставка силами продавца;\n- `3pl_tracking` — доставка внешней службой, продавец регистрирует заказ;\n- `hybrid` — гибридная интеграция;\n- `hybrid_aggregator` — гибридная интеграция с доставкой внешней службой, Ozon регистрирует заказ;\n- `hybrid_non_integrated` — гибридная интеграция с доставкой силами продавца;\n- `hybrid_3pl_tracking` — гибридная интеграция с доставкой внешней службой, продавец регистрирует заказ;\n- `click_and_collect` — бронирование в магазине партнёра;\n- `FBP` — доставка с партнёрских складов Ozon.\n')
    is_express: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Если использовалась быстрая доставка Ozon Express — `true`.')
    is_multibox: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак, что в отправлении есть многокоробочный товар и нужно передать количество коробок для него:\n\n- `true` — до сборки передайте количество коробок через метод [/v3/posting/multiboxqty/set](#operation/PostingAPI_PostingMultiBoxQtySetV3).\n- `false` — отправление собрано с указанием количества коробок в параметре `multi_box_qty` или в отправлении нет многокоробочного товара.\n')
    legal_info: OzonV2FboSinglePostingLegalInfo = Field(_OPTIONAL_FIELD_DEFAULT)
    multi_box_qty: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество коробок, в которые упакован товар.', json_schema_extra={'format': 'int32'})
    optional: OzonV3FbsPostingDetailOptional = Field(_OPTIONAL_FIELD_DEFAULT)
    order_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор заказа, к которому относится отправление.', json_schema_extra={'format': 'int64'})
    order_number: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер заказа, к которому относится отправление.')
    parent_posting_number: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер родительского отправления, в результате разделения которого появилось текущее.')
    pickup_code_verified_at: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время успешной валидации кода курьера. Чтобы проверить код курьера, воспользуйтесь методом [/v1/posting/fbs/pick-up-code/verify](#operation/PostingAPI_PostingFBSPickupCodeVerify).', json_schema_extra={'format': 'date-time'})
    posting_number: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер отправления.')
    product_exemplars: OzonV3FbsPostingProductExemplarsV3 = Field(_OPTIONAL_FIELD_DEFAULT)
    products: list[OzonV3PostingProductDetail] = Field(_OPTIONAL_FIELD_DEFAULT, description='Массив товаров в отправлении.')
    provider_status: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Статус службы доставки.')
    prr_option: OzonFbsPostingDetailPrrOption = Field(_OPTIONAL_FIELD_DEFAULT)
    related_postings: OzonV3FbsPostingDetailRelatedPostings = Field(_OPTIONAL_FIELD_DEFAULT)
    related_weight_postings: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список номеров связанных весовых отправлений.')
    require_blr_traceable_attrs: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если нужно заполнить атрибуты прослеживаемости.\n')
    requirements: OzonV3FbsPostingRequirementsV3 = Field(_OPTIONAL_FIELD_DEFAULT)
    shipment_date: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время, до которой необходимо собрать отправление. Показываем рекомендованное время отгрузки. По истечении этого времени начнёт применяться новый тариф, информацию о нём уточняйте в поле `tariffication`.', json_schema_extra={'format': 'date-time'})
    shipment_date_without_delay: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время отгрузки без просрочки.', json_schema_extra={'format': 'date-time'})
    sorting_center: OzonPostingV3FbsPostingDetailSortingCenter = Field(_OPTIONAL_FIELD_DEFAULT)
    status: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Статус отправления:\n- `acceptance_in_progress` — идёт приёмка,\n- `arbitration` — арбитраж,\n- `awaiting_approve` — ожидает подтверждения,\n- `awaiting_deliver` — ожидает отгрузки,\n- `awaiting_packaging` — ожидает упаковки,\n- `awaiting_registration` — ожидает регистрации,\n- `awaiting_verification` — создано,\n- `cancelled` — отменено,\n- `cancelled_from_split_pending` — отменён из-за разделения отправления,\n- `client_arbitration` — клиентский арбитраж доставки,\n- `delivered` — доставлено,\n- `delivering` — доставляется,\n- `driver_pickup` — у водителя,\n- `not_accepted` — не принят на сортировочном центре,\n')
    substatus: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Подстатус отправления:\n- `posting_acceptance_in_progress` — идёт приёмка,\n- `posting_in_arbitration` — арбитраж,\n- `posting_created` — создано,\n- `posting_in_carriage` — в перевозке,\n- `posting_not_in_carriage` — не добавлено в перевозку,\n- `posting_registered` — зарегистрировано,\n- `posting_transferring_to_delivery` (`status=awaiting_deliver`) — передаётся в доставку,\n- `posting_awaiting_passport_data` — ожидает паспортных данных, \n- `posting_created` — создано,\n- `posting_awaiting_registration` — ожидает регистрации,\n- `posting_registration_error` — ошибка регистрации,\n- `posting_transferring_to_delivery` (`status=awaiting_registration`) — передаётся курьеру,\n- `posting_split_pending` — создано,\n- `posting_canceled` — отменено,\n- `posting_in_client_arbitration` — клиентский арбитраж доставки,\n- `posting_delivered` — доставлено,\n- `posting_received` — получено,\n- `posting_conditionally_delivered` — условно доставлено,\n- `posting_in_courier_service` — курьер в пути,\n- `posting_in_pickup_point` — в пункте выдачи,\n- `posting_on_way_to_city` — в пути в ваш город,\n- `posting_on_way_to_pickup_point` — в пути в пункт выдачи,\n- `posting_returned_to_warehouse` — возвращено на склад,\n- `posting_transferred_to_courier_service` — передаётся в службу доставки,\n- `posting_driver_pick_up` — у водителя,\n- `posting_not_in_sort_center` — не принято на сортировочном центре,\n- `ship_failed` — сборка не удалась.\n')
    previous_substatus: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Предыдущий подстатус отправления. Возможные значения:\n- `posting_acceptance_in_progress` — идёт приёмка,\n- `posting_in_arbitration` — арбитраж,\n- `posting_created` — создано,\n- `posting_in_carriage` — в перевозке,\n- `posting_not_in_carriage` — не добавлено в перевозку,\n- `posting_registered` — зарегистрировано,\n- `posting_transferring_to_delivery` (`status=awaiting_deliver`) — передаётся в доставку,\n- `posting_awaiting_passport_data` — ожидает паспортных данных, \n- `posting_created` — создано,\n- `posting_awaiting_registration` — ожидает регистрации,\n- `posting_registration_error` — ошибка регистрации,\n- `posting_transferring_to_delivery` (`status=awaiting_registration`) — передаётся курьеру,\n- `posting_split_pending` — создано,\n- `posting_canceled` — отменено,\n- `posting_in_client_arbitration` — клиентский арбитраж доставки,\n- `posting_delivered` — доставлено,\n- `posting_received` — получено,\n- `posting_conditionally_delivered` — условно доставлено,\n- `posting_in_courier_service` — курьер в пути,\n- `posting_in_pickup_point` — в пункте выдачи,\n- `posting_on_way_to_city` — в пути в ваш город,\n- `posting_on_way_to_pickup_point` — в пути в пункт выдачи,\n- `posting_returned_to_warehouse` — возвращено на склад,\n- `posting_transferred_to_courier_service` — передаётся в службу доставки,\n- `posting_driver_pick_up` — у водителя,\n- `posting_not_in_sort_center` — не принято на сортировочном центре.\n')
    tpl_integration_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип интеграции со службой доставки:\n  - `ozon` — доставка через Ozon логистику.\n  - `aggregator` — доставка внешней службой, Ozon регистрирует заказ.\n  - `3pl_tracking` — доставка внешней службой, продавец регистрирует заказ.\n  - `non_integrated` — доставка силами продавца.\n')
    tracking_number: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Трек-номер отправления.')
    tariffication: OzonV3FbsTariffication = Field(_OPTIONAL_FIELD_DEFAULT)
    tariffication_steps: list[OzonPostingV4PostingFbsListResponsePostingsTarifficationStep] = Field(_OPTIONAL_FIELD_DEFAULT, description='Этапы тарификации.')


class OzonV3AdditionalDataItem(OzonFbsModel):
    __openapi_name__ = 'v3AdditionalDataItem'
    key: str = Field(_OPTIONAL_FIELD_DEFAULT)
    value: str = Field(_OPTIONAL_FIELD_DEFAULT)


class OzonV3Addressee(OzonFbsModel):
    __openapi_name__ = 'v3Addressee'
    'Контактные данные получателя.'
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Имя покупателя.')
    phone: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Подменный контактный телефон получателя. \n\n[Подробнее о подменных номерах в Базе знаний](https://seller-edu.ozon.ru/rfbs/orders-cancellations/replacement-number)\n', pattern=' +7(XXX)XXX-XX-XX')
    pin: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Добавочный номер телефона получателя, вводится в тональном режиме. Только для отправлений realFBS со службами доставки:\n  - `3pl_tracking` — доставка внешней службой, продавец регистрирует заказ.\n  - `non_integrated` — доставка силами продавца.\n')


class OzonV3FbsPostingAnalyticsData(OzonFbsModel):
    __openapi_name__ = 'v3FbsPostingAnalyticsData'
    'Данные аналитики.'
    city: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Город доставки. Только для отправлений rFBS и продавцов из СНГ.')
    delivery_date_begin: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время начала доставки.', json_schema_extra={'format': 'date-time'})
    delivery_date_end: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время конца доставки.', json_schema_extra={'format': 'date-time'})
    delivery_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Способ доставки.')
    is_legal: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак, что получатель юридическое лицо:\n  - `true` — юридическое лицо,\n  - `false` — физическое лицо.\n')
    is_premium: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Наличие подписки Premium.')
    payment_type_group_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Способ оплаты: \n- `картой онлайн`,\n- `карта Ozon Банка`,\n- `автосписание с карты Ozon Банка при выдаче`,\n- `сохранённой картой при получении`,\n- `Система Быстрых Платежей`, \n- `Ozon Рассрочка`, \n- `оплата на расчётный счёт`,\n- `SberPay`,\n- `предоплата на стороне внешнего продавца`.\n')
    region: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Регион доставки. Только для отправлений rFBS.')
    tpl_provider: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Служба доставки.')
    tpl_provider_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор службы доставки.', json_schema_extra={'format': 'int64'})
    warehouse: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название склада отправки заказа.')
    warehouse_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор склада.', json_schema_extra={'format': 'int64'})
    client_delivery_date_begin: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время начала доставки. Только для отправлений, оформленных через [Ozon Доставку](#tag/OzonLogistics).', json_schema_extra={'format': 'date-time'})
    client_delivery_date_end: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Ожидаемая дата, до которой заказ будет доставлен. Только для отправлений, оформленных через [Ozon Доставку](#tag/OzonLogistics).', json_schema_extra={'format': 'date-time'})


class OzonV3Barcodes(OzonFbsModel):
    __openapi_name__ = 'v3Barcodes'
    'Штрихкоды отправления.'
    lower_barcode: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Нижний штрихкод на маркировке отправления.')
    upper_barcode: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Верхний штрихкод на маркировке отправления.')


class OzonV3Cancellation(OzonFbsModel):
    __openapi_name__ = 'v3Cancellation'
    'Информация об отмене.'
    affect_cancellation_rating: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Если отмена влияет на рейтинг продавца — `true`.')
    cancel_reason: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Причина отмены.')
    cancel_reason_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор причины отмены отправления.', json_schema_extra={'format': 'int64'})
    cancellation_initiator: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Инициатор отмены:\n- `Продавец`, \n- `Клиент` или `покупатель`,\n- `Ozon`,  \n- `Система`, \n- `Служба доставки`.\n')
    cancellation_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип отмены отправления:\n- `seller` — отменено продавцом;\n- `client` или `customer` — отменено покупателем;\n- `ozon` — отменено Ozon;\n- `system`— отменено системой;\n- `delivery` — отменено службой доставки.\n')
    cancelled_after_ship: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Если отмена произошла после сборки отправления\xa0—\xa0`true`.')


class OzonFbsPostingDetailCourier(OzonFbsModel):
    __openapi_name__ = 'FbsPostingDetailCourier'
    'Данные о курьере.'
    car_model: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Модель автомобиля.')
    car_number: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер автомобиля.')
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Полное имя курьера.')
    phone: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Телефон курьера. \n\nВсегда возвращает пустую строку `""`.\n')


class OzonV3Customer(OzonFbsModel):
    __openapi_name__ = 'v3Customer'
    'Данные о покупателе.'
    address: OzonV3Address = Field(_OPTIONAL_FIELD_DEFAULT)
    customer_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор покупателя.', json_schema_extra={'format': 'int64'})
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Имя покупателя.')
    phone: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Подменный контактный телефон покупателя. \n\n[Подробнее о подменных номерах в Базе знаний](https://seller-edu.ozon.ru/rfbs/orders-cancellations/replacement-number)\n')


class OzonV3Address(OzonFbsModel):
    __openapi_name__ = 'v3Address'
    'Информация об адресе доставки.'
    address_tail: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Адрес в текстовом формате.')
    city: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Город доставки.')
    comment: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Комментарий к заказу.')
    country: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Страна доставки.')
    district: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Район доставки.')
    latitude: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Широта.', json_schema_extra={'format': 'double'})
    longitude: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Долгота.', json_schema_extra={'format': 'double'})
    provider_pvz_code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Код пункта выдачи заказов 3PL провайдера.')
    pvz_code: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Код пункта выдачи заказов.', json_schema_extra={'format': 'int64'})
    region: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Регион доставки.')
    zip_code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Почтовый индекс получателя.')


class OzonV3DeliveryMethod(OzonFbsModel):
    __openapi_name__ = 'v3DeliveryMethod'
    'Метод доставки.'
    id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор способа доставки.', json_schema_extra={'format': 'int64'})
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название способа доставки.')
    tpl_provider: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Служба доставки.')
    tpl_provider_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор службы доставки.', json_schema_extra={'format': 'int64'})
    warehouse: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название склада.')
    warehouse_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор склада.', json_schema_extra={'format': 'int64'})


class OzonPostingV3FbsPostingDetailExternalOrder(OzonFbsModel):
    __openapi_name__ = 'posting.v3.FbsPostingDetail.ExternalOrder'
    'Информация о заказе с внешней платформы.'
    is_external: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если заказ с внешней платформы.\n')
    platform_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название платформы, с которой сделали заказ.')


class OzonV3PostingFinancialData(OzonFbsModel):
    __openapi_name__ = 'v3PostingFinancialData'
    'Данные о стоимости товара, размере скидки, выплате и комиссии.'
    cluster_from: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Код региона, откуда отправляется заказ.')
    cluster_to: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Код региона, куда доставляется заказ.')
    products: list[OzonPostingFinancialDataProduct] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список товаров в заказе.')


class OzonPostingFinancialDataProduct(OzonFbsModel):
    __openapi_name__ = 'PostingFinancialDataProduct'
    actions: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список акций.')
    currency_code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Валюта ваших цен. Cовпадает с валютой, которая установлена в настройках личного кабинета.\n\nВозможные значения: \n  - `RUB` — российский рубль,\n  - `BYN` — белорусский рубль,\n  - `KZT` — тенге,\n  - `EUR` — евро,\n  - `USD` — доллар США,\n  - `CNY` — юань.\n')
    customer_currency_code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Код валюты покупателя.')
    commission_amount: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Размер комиссии за товар.', json_schema_extra={'format': 'double'})
    commission_percent: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Процент комиссии.', json_schema_extra={'format': 'int64'})
    commissions_currency_code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Код валюты, в которой рассчитывались комиссии.')
    old_price: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Цена до учёта скидок. На карточке товара отображается зачёркнутой.', json_schema_extra={'format': 'double'})
    payout: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Выплата продавцу.', json_schema_extra={'format': 'double'})
    price: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Цена товара с учётом акций, кроме акций за счёт Ozon.', json_schema_extra={'format': 'double'})
    customer_price: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Цена товара для покупателя с учётом скидок продавца и Ozon.', json_schema_extra={'format': 'double'})
    product_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор товара в системе Ozon — SKU.', json_schema_extra={'format': 'int64'})
    quantity: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество товара в отправлении.', json_schema_extra={'format': 'int64'})
    total_discount_percent: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Процент скидки.', json_schema_extra={'format': 'double'})
    total_discount_value: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Сумма скидки.', json_schema_extra={'format': 'double'})


class OzonV2FboSinglePostingLegalInfo(OzonFbsModel):
    __openapi_name__ = 'v2FboSinglePostingLegalInfo'
    'Юридическая информация о покупателе.'
    company_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название компании.')
    inn: str = Field(_OPTIONAL_FIELD_DEFAULT, description='ИНН.')
    kpp: str = Field(_OPTIONAL_FIELD_DEFAULT, description='КПП.')


class OzonV3FbsPostingDetailOptional(OzonFbsModel):
    __openapi_name__ = 'v3FbsPostingDetailOptional'
    'Список товаров с дополнительными характеристиками.'
    products_with_possible_mandatory_mark: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список товаров с возможной маркировкой.')


class OzonV3FbsPostingProductExemplarsV3(OzonFbsModel):
    __openapi_name__ = 'v3FbsPostingProductExemplarsV3'
    'Информация по продуктам и их экземплярам.\n\nОтвет содержит поле `product_exemplars`, если в запросе передан признак `with.product_exemplars = true`.\n'
    products: list[OzonV3FbsPostingExemplarProductV3] = Field(_OPTIONAL_FIELD_DEFAULT, description='Информация по продуктам.')


class OzonV3FbsPostingExemplarProductV3(OzonFbsModel):
    __openapi_name__ = 'v3FbsPostingExemplarProductV3'
    'Список товаров и экземпляров.'
    exemplars: list[OzonV3FbsPostingProductExemplarInfoV3] = Field(_OPTIONAL_FIELD_DEFAULT, description='Информация по экземплярам.')
    sku: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор товара в системе Ozon — SKU.', json_schema_extra={'format': 'int64'})


class OzonV3FbsPostingProductExemplarInfoV3(OzonFbsModel):
    __openapi_name__ = 'v3FbsPostingProductExemplarInfoV3'
    exemplar_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор экземпляра.', json_schema_extra={'format': 'int64'})
    mandatory_mark: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Обязательная маркировка «Честный ЗНАК».')
    gtd: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер грузовой таможенной декларации (ГТД).')
    is_gtd_absent: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак того, что не указан номер таможенной декларации.')
    rnpt: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Регистрационный номер партии товара (РНПТ).')
    is_rnpt_absent: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак того, что не указан регистрационный номер партии товара (РНПТ).')
    weight: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Фактический вес экземпляра.', json_schema_extra={'format': 'float'})
    imei: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список IMEI мобильных устройств.')


class OzonV3PostingProductDetail(OzonFbsModel):
    __openapi_name__ = 'v3PostingProductDetail'
    'Размеры товара.'
    dimensions: OzonV3Dimensions = Field(_OPTIONAL_FIELD_DEFAULT)
    mandatory_mark: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Обязательная маркировка товара.')
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название.')
    offer_id: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор товара в системе продавца — артикул.')
    price: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Цена товара с учётом скидок — это значение показывается на карточке товара.')
    jw_uin: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Уникальный идентификационный номер (УИН) ювелирного изделия.')
    currency_code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Валюта ваших цен. Совпадает с валютой, которая установлена в настройках личного кабинета.\n\nВозможные значения: \n  - `RUB` — российский рубль,\n  - `BYN` — белорусский рубль,\n  - `KZT` — тенге,\n  - `EUR` — евро,\n  - `USD` — доллар США,\n  - `CNY` — юань.\n')
    is_blr_traceable: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак прослеживаемости товара.')
    is_marketplace_buyout: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если Ozon выкупил товар.\n\n[Подробнее о выкупе товаров в Базе знаний продавца](https://seller-edu.ozon.ru/commissions-tariffs/commissions-tariffs-ozon/prodaji-tovarov-v-eaes-i-drugie-strany#какие-товары-выкупает-ozon)\n')
    quantity: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество товара.', json_schema_extra={'format': 'int32'})
    sku: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор товара на Ozon.', json_schema_extra={'format': 'int64'})
    is_weight_needed: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если товар весовой.\n')
    weight_max: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Максимальный вес экземпляра.', json_schema_extra={'format': 'float'})
    weight_min: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Минимальный вес экземпляра.', json_schema_extra={'format': 'float'})
    has_imei: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак наличия IMEI.\n\nЕсли IMEI есть — `true`.\n')


class OzonV3Dimensions(OzonFbsModel):
    __openapi_name__ = 'v3Dimensions'
    'Размеры товара.'
    height: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Высота упаковки.')
    length: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Длина товара.')
    weight: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Вес товара в упаковке.')
    width: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Ширина упаковки.')


class OzonFbsPostingDetailPrrOption(OzonFbsModel):
    __openapi_name__ = 'FbsPostingDetailPrrOption'
    'Информация об услуге погрузочно-разгрузочных работ. Актуально для КГТ-отправлений с доставкой силами продавца или интегрированной службой.'
    code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Код услуги погрузочно-разгрузочных работ:\n- `lift` — подъём на лифте.\n- `stairs` — подъём по лестнице.\n- `none` — покупатель отказался от услуги, поднимать товары не нужно.\n- `delivery_default` — доставка включена в стоимость, по условиям оферты нужно доставить товар на этаж.\n')
    price: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Стоимость услуги, которую Ozon компенсирует продавцу.')
    currency_code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Валюта.')
    floor: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Этаж, на который нужно поднять товар.')


class OzonV3FbsPostingDetailRelatedPostings(OzonFbsModel):
    __openapi_name__ = 'v3FbsPostingDetailRelatedPostings'
    'Связанные отправления.'
    related_posting_numbers: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список номеров связанных отправлений.')


class OzonV3FbsPostingRequirementsV3(OzonFbsModel):
    __openapi_name__ = 'v3FbsPostingRequirementsV3'
    'Cписок продуктов, для которых нужно передать страну-изготовителя, номер грузовой таможенной декларации (ГТД), регистрационный номер партии товара (РНПТ), маркировку «Честный ЗНАК», другие маркировки или вес, чтобы перевести отправление в следующий статус.'
    products_requiring_change_country: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список идентификаторов товаров (SKU), для которых нужно изменить страну-изготовитель. Чтобы изменить страну-изготовитель, используйте методы [/v2/posting/fbs/product/country/list](#operation/PostingAPI_ListCountryProductFbsPostingV2) и [/v2/posting/fbs/product/country/set](#operation/PostingAPI_SetCountryProductFbsPostingV2).')
    products_requiring_gtd: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список идентификаторов товаров (SKU), для которых нужно передать номера таможенной декларации (ГТД).\n\nДо сборки отправления передайте для всех перечисленных товаров номер таможенной декларации или информацию о том, \nчто номера нет, методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).\n')
    products_requiring_country: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список идентификаторов товаров (SKU), для которых нужно передать информацию о стране-изготовителе.\n\nДля сборки отправления передайте информацию о стране-изготовителе для всех перечисленных товаров с помощью метода [/v2/posting/fbs/product/country/set](#operation/PostingAPI_SetCountryProductFbsPostingV2).\n')
    products_requiring_mandatory_mark: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список идентификаторов товаров (SKU), для которых нужно передать маркировку «Честный ЗНАК».\n\nДо сборки отправления передайте для всех перечисленных товаров маркировку «Честный ЗНАК» методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).\n')
    products_requiring_jw_uin: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список товаров, для которых нужно передать уникальный идентификационный номер (УИН) ювелирного изделия.\n\nДо сборки отправления передайте для всех перечисленных товаров уникальный идентификационный номер (УИН) методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).\n')
    products_requiring_rnpt: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список идентификаторов товаров (SKU), для которых нужно передать регистрационный номер партии товара (РНПТ).\n\nДо сборки отправления передайте для всех перечисленных товаров регистрационный номер партии товара (РНПТ) методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).\n')
    products_requiring_weight: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список товаров, для которых нужно передать вес.')
    products_requiring_imei: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список идентификаторов товаров, для которых нужно передать IMEI.')


class OzonPostingV3FbsPostingDetailSortingCenter(OzonFbsModel):
    __openapi_name__ = 'posting.v3.FbsPostingDetail.SortingCenter'
    'Информация о сортировочном центре, в который нужно привезти отправление. Для `integration_type_flow = hybrid_3pl_tracking`.\nЕсли значение `null`, информацию получить не удалось.\n'
    code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Код сортировочного центра.')
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название сортировочного центра.')


class OzonV3FbsTariffication(OzonFbsModel):
    __openapi_name__ = 'v3FbsTariffication'
    'Информация по тарификации отгрузки.'
    current_tariff_rate: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Текущий процент тарификации.', json_schema_extra={'format': 'double'})
    current_tariff_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Текущий тип тарификации — скидка или надбавка.')
    current_tariff_charge: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Текущая сумма скидки или надбавки.')
    current_tariff_charge_currency_code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Валюта суммы.')
    next_tariff_rate: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Процент, по которому будет тарифицироваться отправление через указанное в параметре `next_tariff_starts_at` время.', json_schema_extra={'format': 'double'})
    next_tariff_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип тарифа, по которому будет тарифицироваться отправление через указанное в параметре `next_tariff_starts_at` время — скидка или надбавка.')
    next_tariff_charge: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Сумма скидки или надбавки на следующем шаге тарификации.')
    next_tariff_starts_at: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата и время, когда начнёт применяться новый тариф.\n\nФормат: `YYYY-MM-DDThh:mm:ss.mcsZ`. \n\nПример: `2023-11-13T08:05:57.657Z`.\n', json_schema_extra={'format': 'date-time'})
    next_tariff_charge_currency_code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Валюта нового тарифа.')


class OzonV1GetRestrictionsRequest(OzonFbsModel):
    __openapi_name__ = 'v1GetRestrictionsRequest'
    posting_number: str = Field(..., description='Номер отправления, для которого нужно определить ограничения.')


class OzonV1GetRestrictionsResponse(OzonFbsModel):
    __openapi_name__ = 'v1GetRestrictionsResponse'
    result: OzonV1Restriction = Field(_OPTIONAL_FIELD_DEFAULT)


class OzonV1Restriction(OzonFbsModel):
    __openapi_name__ = 'v1Restriction'
    posting_number: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер отправления.')
    max_posting_weight: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Ограничение по максимальному весу в граммах.', json_schema_extra={'format': 'double'})
    min_posting_weight: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Ограничение по минимальному весу в граммах.', json_schema_extra={'format': 'double'})
    width: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Ограничение по ширине в сантиметрах.', json_schema_extra={'format': 'double'})
    length: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Ограничение по длине в сантиметрах.', json_schema_extra={'format': 'double'})
    height: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Ограничение по высоте в сантиметрах.', json_schema_extra={'format': 'double'})
    max_posting_price: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Ограничение по максимальной стоимости отправления в рублях.', json_schema_extra={'format': 'double'})
    min_posting_price: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Ограничение по минимальной стоимости отправления в рублях.', json_schema_extra={'format': 'double'})


class OzonV2FbsPostingProductCountryListRequest(OzonFbsModel):
    __openapi_name__ = 'v2FbsPostingProductCountryListRequest'
    name_search: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Фильтрация по строке.')


class OzonV2FbsPostingProductCountryListResponse(OzonFbsModel):
    __openapi_name__ = 'v2FbsPostingProductCountryListResponse'
    result: list[OzonV2FbsPostingProductCountryListResponseResult] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список стран-изготовителей и ISO коды.')


class OzonV2FbsPostingProductCountryListResponseResult(OzonFbsModel):
    __openapi_name__ = 'v2FbsPostingProductCountryListResponseResult'
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название страны на русском языке.')
    country_iso_code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='ISO код страны.')


class OzonGooglerpcStatus(OzonFbsModel):
    __openapi_name__ = 'googlerpcStatus'
    code: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Код ошибки.', json_schema_extra={'format': 'int32'})
    details: list[OzonProtobufAny] = Field(_OPTIONAL_FIELD_DEFAULT, description='Дополнительная информация об ошибке.')
    message: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Описание ошибки.')


class OzonV2FbsPostingProductCountrySetRequest(OzonFbsModel):
    __openapi_name__ = 'v2FbsPostingProductCountrySetRequest'
    posting_number: str = Field(..., description='Номер отправления.')
    product_id: int = Field(..., description='Идентификатор товара в системе Ozon — `product_id`.', json_schema_extra={'format': 'int64'})
    country_iso_code: str = Field(..., description='Двухбуквенный код добавляемой страны по стандарту ISO_3166-1.\n\nСписок доступных стран-изготовителей и их ISO коды можно получить с помощью метода [/v2/posting/fbs/product/country/list](#operation/PostingAPI_ListCountryProductFbsPostingV2).\n')


class OzonV2FbsPostingProductCountrySetResponse(OzonFbsModel):
    __openapi_name__ = 'v2FbsPostingProductCountrySetResponse'
    product_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор товара в системе Ozon — `product_id`.', json_schema_extra={'format': 'int64'})
    is_gtd_needed: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак того, что необходимо передать номер грузовой таможенной декларации (ГТД) для продукта и отправления.')


class OzonV6FbsPostingProductExemplarCreateOrGetV6Request(OzonFbsModel):
    __openapi_name__ = 'v6FbsPostingProductExemplarCreateOrGetV6Request'
    posting_number: str = Field(..., description='Номер отправления.')


class OzonV6FbsPostingProductExemplarCreateOrGetV6Response(OzonFbsModel):
    __openapi_name__ = 'v6FbsPostingProductExemplarCreateOrGetV6Response'
    multi_box_qty: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество коробок, в которые упакован товар.', json_schema_extra={'format': 'int32'})
    posting_number: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер отправления.')
    products: list[OzonFbsPostingProductExemplarCreateOrGetV6ResponseProduct] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список товаров.')


class OzonFbsPostingProductExemplarCreateOrGetV6ResponseProduct(OzonFbsModel):
    __openapi_name__ = 'FbsPostingProductExemplarCreateOrGetV6ResponseProduct'
    exemplars: list[OzonProductExemplar] = Field(_OPTIONAL_FIELD_DEFAULT, description='Информация об экземплярах.')
    has_imei: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак наличия IMEI.\n\nЕсли IMEI есть — `true`.\n')
    is_gtd_needed: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак того, что необходимо передать номер грузовой таможенной декларации (ГТД) для продукта и отправления.')
    is_jw_uin_needed: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак того, что необходимо передать уникальный идентификационный номер ювелирного изделия (УИН).')
    is_mandatory_mark_needed: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак того, что необходимо передать маркировку «Честный ЗНАК».')
    is_mandatory_mark_possible: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак того, что возможно заполнить маркировку «Честный ЗНАК».')
    is_rnpt_needed: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак того, что необходимо передать номер партии товара (РНПТ).')
    product_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор товара в системе Ozon — SKU.', json_schema_extra={'format': 'int64'})
    quantity: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество экземпляров.', json_schema_extra={'format': 'int32'})
    is_weight_needed: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если товар весовой.\n')
    weight_max: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Максимальный вес экземпляра.', json_schema_extra={'format': 'float'})
    weight_min: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Минимальный вес экземпляра.', json_schema_extra={'format': 'float'})


class OzonProductExemplar(OzonFbsModel):
    __openapi_name__ = 'ProductExemplar'
    exemplar_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор экземпляра.', json_schema_extra={'format': 'int64'})
    gtd: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер грузовой таможенной декларации (ГТД).')
    is_gtd_absent: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак того, что не указан номер грузовой таможенной декларации (ГТД).')
    is_rnpt_absent: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак того, что не указан регистрационный номер партии товара (РНПТ).')
    marks: list[OzonExemplarMark] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список контрольных идентификационных знаков (КИЗ) и других маркировок в одном экземпляре.')
    rnpt: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Регистрационный номер партии товара (РНПТ).')
    weight: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Фактический вес экземпляра.', json_schema_extra={'format': 'float'})


class OzonExemplarMark(OzonFbsModel):
    __openapi_name__ = 'ExemplarMark'
    mark: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Значение кода маркировки.')
    mark_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип кода маркировки:\n - `mandatory_mark` — обязательная маркировка «Честный ЗНАК»;\n - `jw_uin` — уникальный идентификационный номер (УИН) ювелирного изделия;\n - `imei` — IMEI мобильного устройства.\n')


class OzonV5FbsPostingProductExemplarValidateV5Request(OzonFbsModel):
    __openapi_name__ = 'v5FbsPostingProductExemplarValidateV5Request'
    posting_number: str = Field(..., description='Номер отправления.')
    products: list[OzonV5FbsPostingProductExemplarValidateV5RequestProduct] = Field(..., description='Список товаров.')


class OzonV5FbsPostingProductExemplarValidateV5RequestProduct(OzonFbsModel):
    __openapi_name__ = 'v5FbsPostingProductExemplarValidateV5RequestProduct'
    exemplars: list[OzonV5FbsPostingProductExemplarValidateV5RequestProductExemplar] = Field(..., description='Информация об экземплярах.')
    product_id: int = Field(..., description='Идентификатор товара в системе Ozon — SKU.', json_schema_extra={'format': 'int64'})


class OzonV5FbsPostingProductExemplarValidateV5RequestProductExemplar(OzonFbsModel):
    __openapi_name__ = 'v5FbsPostingProductExemplarValidateV5RequestProductExemplar'
    gtd: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер грузовой таможенной декларации (ГТД).')
    marks: list[OzonV5FbsPostingProductExemplarValidateV5RequestProductExemplarMark] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список контрольных идентификационных знаков (КИЗ) и других маркировок в одном экземпляре.')
    rnpt: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Регистрационный номер партии товара (РНПТ).')
    weight: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Фактический вес экземпляра.', json_schema_extra={'format': 'float'})


class OzonV5FbsPostingProductExemplarValidateV5RequestProductExemplarMark(OzonFbsModel):
    __openapi_name__ = 'v5FbsPostingProductExemplarValidateV5RequestProductExemplarMark'
    mark: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Значение кода маркировки.')
    mark_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип кода маркировки:\n - `mandatory_mark` — обязательная маркировка «Честный ЗНАК»;\n - `jw_uin` — уникальный идентификационный номер (УИН) ювелирного изделия;\n - `imei` — IMEI мобильного устройства.\n')


class OzonV5FbsPostingProductExemplarValidateV5Response(OzonFbsModel):
    __openapi_name__ = 'v5FbsPostingProductExemplarValidateV5Response'
    products: list[OzonV5FbsPostingProductExemplarValidateV5ResponseProduct] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список товаров.')


class OzonV5FbsPostingProductExemplarValidateV5ResponseProduct(OzonFbsModel):
    __openapi_name__ = 'v5FbsPostingProductExemplarValidateV5ResponseProduct'
    error: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Код ошибки.')
    exemplars: list[OzonV5FbsPostingProductExemplarValidateV5ResponseProductExemplar] = Field(_OPTIONAL_FIELD_DEFAULT, description='Информация об экземплярах.')
    product_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор товара в системе Ozon — SKU.', json_schema_extra={'format': 'int64'})
    valid: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Результат прохождения проверки. `true`, если коды всех экземпляров соответствуют требованиям.')


class OzonV5FbsPostingProductExemplarValidateV5ResponseProductExemplar(OzonFbsModel):
    __openapi_name__ = 'v5FbsPostingProductExemplarValidateV5ResponseProductExemplar'
    errors: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Ошибки валидации экземпляра.')
    gtd: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер грузовой таможенной декларации (ГТД).')
    marks: list[OzonV5FbsPostingProductExemplarValidateV5ResponseProductExemplarMark] = Field(_OPTIONAL_FIELD_DEFAULT, description='Ошибки при проверке контрольных идентификационных знаков (КИЗ) и других маркировок.')
    rnpt: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Регистрационный номер партии товара (РНПТ).')
    valid: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Результат прохождения проверки. `true`, если код экземпляра соответствует требованиям.')
    weight: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Фактический вес экземпляра.', json_schema_extra={'format': 'float'})


class OzonV5FbsPostingProductExemplarValidateV5ResponseProductExemplarMark(OzonFbsModel):
    __openapi_name__ = 'v5FbsPostingProductExemplarValidateV5ResponseProductExemplarMark'
    errors: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Ошибки при проверке контрольных идентификационных знаков (КИЗ) и других маркировок.')
    mark: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Значение кода маркировки.')
    mark_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип кода маркировки:\n - `mandatory_mark` — обязательная маркировка «Честный ЗНАК»;\n - `jw_uin` — уникальный идентификационный номер (УИН) ювелирного изделия;\n - `imei` — IMEI мобильного устройства.\n')
    valid: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Результат прохождения проверки. `true`, если контрольный идентификационный знак (КИЗ) и другие маркировки соответствуют требованиям.')


class OzonV6FbsPostingProductExemplarSetV6Request(OzonFbsModel):
    __openapi_name__ = 'v6FbsPostingProductExemplarSetV6Request'
    multi_box_qty: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество коробок, в которые упакован товар.', json_schema_extra={'format': 'int32'})
    posting_number: str = Field(..., description='Номер отправления.')
    products: list[OzonFbsPostingProductExemplarSetV6RequestProducts] = Field(..., description='Список товаров.')


class OzonFbsPostingProductExemplarSetV6RequestProducts(OzonFbsModel):
    __openapi_name__ = 'FbsPostingProductExemplarSetV6RequestProducts'
    exemplars: list[OzonFbsPostingProductExemplarSetV6RequestExemplars] = Field(..., description='Информация об экземплярах.')
    product_id: int = Field(..., description='Идентификатор товара в системе Ozon — SKU.', json_schema_extra={'format': 'int64'})


class OzonFbsPostingProductExemplarSetV6RequestExemplars(OzonFbsModel):
    __openapi_name__ = 'FbsPostingProductExemplarSetV6RequestExemplars'
    exemplar_id: int = Field(..., description='Идентификатор экземпляра.', json_schema_extra={'format': 'int64'})
    gtd: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер грузовой таможенной декларации (ГТД).')
    is_gtd_absent: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак того, что не указан номер грузовой таможенной декларации (ГТД).')
    is_rnpt_absent: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак того, что не указан регистрационный номер партии товара (РНПТ).')
    marks: list[OzonExemplarsMarks] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список контрольных идентификационных знаков (КИЗ) и других маркировок в одном экземпляре.')
    rnpt: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Регистрационный номер партии товара (РНПТ).')
    weight: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Фактический вес экземпляра.', json_schema_extra={'format': 'float'})


class OzonExemplarsMarks(OzonFbsModel):
    __openapi_name__ = 'ExemplarsMarks'
    mark: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Значение кода маркировки.')
    mark_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип кода маркировки:\n - `mandatory_mark` — обязательная маркировка «Честный ЗНАК»;\n - `jw_uin` — уникальный идентификационный номер (УИН) ювелирного изделия;\n - `imei` — IMEI мобильного устройства.\n')


class OzonV5FbsPostingProductExemplarStatusV5Request(OzonFbsModel):
    __openapi_name__ = 'v5FbsPostingProductExemplarStatusV5Request'
    posting_number: str = Field(..., description='Номер отправления.')


class OzonV5FbsPostingProductExemplarStatusV5Response(OzonFbsModel):
    __openapi_name__ = 'v5FbsPostingProductExemplarStatusV5Response'
    posting_number: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер отправления.')
    products: list[OzonV5FbsPostingProductExemplarStatusV5ResponseProduct] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список товаров.')
    status: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Статус проверки всех экземпляров и доступности сборки:\n - `ship_available` — сборка доступна;\n - `ship_not_available` — сборка недоступна;\n - `validation_in_process` — экземпляры на проверке;\n - `update_available` — редактирование информации об экземплярах доступно;\n - `update_not_available` — редактирование информации об экземплярах недоступно.\n')


class OzonV5FbsPostingProductExemplarStatusV5ResponseProduct(OzonFbsModel):
    __openapi_name__ = 'v5FbsPostingProductExemplarStatusV5ResponseProduct'
    exemplars: list[OzonV5FbsPostingProductExemplarStatusV5ResponseProductExemplar] = Field(_OPTIONAL_FIELD_DEFAULT, description='Информация об экземплярах.')
    product_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор товара в системе Ozon — SKU.', json_schema_extra={'format': 'int64'})


class OzonV5FbsPostingProductExemplarStatusV5ResponseProductExemplar(OzonFbsModel):
    __openapi_name__ = 'v5FbsPostingProductExemplarStatusV5ResponseProductExemplar'
    exemplar_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор экземпляра.', json_schema_extra={'format': 'int64'})
    gtd: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер грузовой таможенной декларации (ГТД).')
    gtd_check_status: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Статус проверки грузовой таможенной декларации.')
    gtd_error_codes: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Коды ошибок при проверке грузовой таможенной декларации.')
    is_gtd_absent: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак того, что не указан номер таможенной декларации (ГТД).')
    is_rnpt_absent: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Признак того, что не указан регистрационный номер партии товара (РНПТ).')
    marks: list[OzonV5FbsPostingProductExemplarStatusV5ResponseProductExemplarMark] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список контрольных идентификационных знаков (КИЗ) и других маркировок в одном экземпляре.')
    rnpt: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Регистрационный номер партии товара (РНПТ).')
    rnpt_check_status: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Статус проверки регистрационного номера партии товара.')
    rnpt_error_codes: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Коды ошибок при проверке регистрационного номера партии товара.')
    weight: float = Field(_OPTIONAL_FIELD_DEFAULT, description='Фактический вес экземпляра.', json_schema_extra={'format': 'float'})
    weight_check_status: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Статус проверки фактического веса.')
    weight_error_codes: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Коды ошибок при проверке фактического веса.')


class OzonV5FbsPostingProductExemplarStatusV5ResponseProductExemplarMark(OzonFbsModel):
    __openapi_name__ = 'v5FbsPostingProductExemplarStatusV5ResponseProductExemplarMark'
    check_status: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Статус проверки:\n  - `processing` — на проверке;\n  - `failed` — система не успела обработать запрос;\n  - `passed` — заказ готов к сборке.\n')
    error_codes: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Ошибки при проверке контрольных идентификационных знаков (КИЗ) и других маркировок.')
    mark: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Значение кода маркировки.')
    mark_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип кода маркировки:\n - `mandatory_mark` — обязательная маркировка «Честный ЗНАК»;\n - `jw_uin` — уникальный идентификационный номер (УИН) ювелирного изделия;\n - `imei` — IMEI мобильного устройства.\n')


class OzonPostingv3PostingMultiBoxQtySetV3Request(OzonFbsModel):
    __openapi_name__ = 'postingv3PostingMultiBoxQtySetV3Request'
    posting_number: str = Field(..., description='Идентификатор многокоробочного отправления.')
    multi_box_qty: int = Field(..., description='Количество коробок, в которые упакован товар.', json_schema_extra={'format': 'int64'})


class OzonPostingv3PostingMultiBoxQtySetV3Response(OzonFbsModel):
    __openapi_name__ = 'postingv3PostingMultiBoxQtySetV3Response'
    result: OzonPostingv3PostingMultiBoxQtySetV3ResponseResult = Field(_OPTIONAL_FIELD_DEFAULT)


class OzonPostingv3PostingMultiBoxQtySetV3ResponseResult(OzonFbsModel):
    __openapi_name__ = 'postingv3PostingMultiBoxQtySetV3ResponseResult'
    'Результат передачи количества коробок.'
    result: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Возможные значения:\n- `true` — значение передано успешно.\n- `false` — при передаче произошла ошибка. Попробуйте снова.\n')


class OzonFbsv4FbsPostingShipV4Request(OzonFbsModel):
    __openapi_name__ = 'fbsv4FbsPostingShipV4Request'
    packages: list[OzonFbsPostingShipV4RequestPackage] = Field(..., description='Список упаковок. Каждая упаковка содержит список отправлений, на которые делится заказ.')
    posting_number: str = Field(..., description='Номер отправления.')
    with_: OzonFbsPostingShipV4RequestWith = Field(_OPTIONAL_FIELD_DEFAULT, alias='with')


class OzonFbsPostingShipV4RequestPackage(OzonFbsModel):
    __openapi_name__ = 'FbsPostingShipV4RequestPackage'
    products: list[OzonFbsPostingShipV4RequestPackageProduct] = Field(..., description='Список товаров в отправлении.')


class OzonFbsPostingShipV4RequestPackageProduct(OzonFbsModel):
    __openapi_name__ = 'FbsPostingShipV4RequestPackageProduct'
    product_id: int = Field(..., description='Идентификатор товара в системе Ozon — SKU.', json_schema_extra={'format': 'int64'})
    quantity: int = Field(..., description='Количество экземпляров.', json_schema_extra={'format': 'int32'})


class OzonFbsPostingShipV4RequestWith(OzonFbsModel):
    __openapi_name__ = 'FbsPostingShipV4RequestWith'
    'Дополнительная информация.'
    additional_data: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Чтобы получить дополнительную информацию, передайте `true`.')


class OzonFbsv4FbsPostingShipV4Response(OzonFbsModel):
    __openapi_name__ = 'fbsv4FbsPostingShipV4Response'
    additional_data: list[OzonFbsPostingShipV4ResponseShipAdditionalData] = Field(_OPTIONAL_FIELD_DEFAULT, description='Дополнительная информация об отправлениях.')
    result: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Результат сборки отправлений.')


class OzonFbsPostingShipV4ResponseShipAdditionalData(OzonFbsModel):
    __openapi_name__ = 'FbsPostingShipV4ResponseShipAdditionalData'
    posting_number: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер отправления.')
    products: list[OzonFbsv4PostingProductDetailWithoutDimensions] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список товаров в отправлении.')


class OzonFbsv4PostingProductDetailWithoutDimensions(OzonFbsModel):
    __openapi_name__ = 'fbsv4PostingProductDetailWithoutDimensions'
    mandatory_mark: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Обязательная маркировка «Честный ЗНАК».')
    name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название товара.')
    offer_id: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор товара в системе продавца — артикул.')
    price: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Цена.')
    quantity: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество товара в отправлении.', json_schema_extra={'format': 'int32'})
    sku: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор товара в системе Ozon — SKU.', json_schema_extra={'format': 'int64'})
    currency_code: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Валюта ваших цен. Cовпадает с валютой, которая установлена в настройках личного кабинета.\n\nВозможные значения: \n  - `RUB` — российский рубль,\n  - `BYN` — белорусский рубль,\n  - `KZT` — тенге,\n  - `EUR` — евро,\n  - `USD` — доллар США,\n  - `CNY` — юань.\n')


class OzonV4FbsPostingShipPackageV4Request(OzonFbsModel):
    __openapi_name__ = 'v4FbsPostingShipPackageV4Request'
    posting_number: str = Field(..., description='Номер отправления.')
    products: list[OzonV4FbsPostingShipPackageV4RequestProduct] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список товаров в отправлении.')


class OzonV4FbsPostingShipPackageV4RequestProduct(OzonFbsModel):
    __openapi_name__ = 'v4FbsPostingShipPackageV4RequestProduct'
    exemplarsIds: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификаторы экземпляров товара.')
    product_id: int = Field(..., description='Идентификатор товара в системе продавца — SKU.', json_schema_extra={'format': 'int64'})
    quantity: int = Field(..., description='Количество экземпляров.', json_schema_extra={'format': 'int32'})


class OzonV4FbsPostingShipPackageV4Response(OzonFbsModel):
    __openapi_name__ = 'v4FbsPostingShipPackageV4Response'
    result: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номера отправлений, сформированные после сборки.')


class OzonV1CreateLabelBatchRequest(OzonFbsModel):
    __openapi_name__ = 'v1CreateLabelBatchRequest'
    posting_number: list[str] = Field(..., description='Номера отправлений, для которых нужны этикетки.')


class OzonV2CreateLabelBatchResponse(OzonFbsModel):
    __openapi_name__ = 'v2CreateLabelBatchResponse'
    result: OzonV2CreateLabelBatchResponseResult = Field(_OPTIONAL_FIELD_DEFAULT)


class OzonV2CreateLabelBatchResponseResult(OzonFbsModel):
    __openapi_name__ = 'v2CreateLabelBatchResponseResult'
    'Результат работы метода.'
    tasks: list[OzonV2CreateLabelBatchResponseResultTasks] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список заданий.')


class OzonV2CreateLabelBatchResponseResultTasks(OzonFbsModel):
    __openapi_name__ = 'v2CreateLabelBatchResponseResultTasks'
    task_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор задания на формирование этикеток. В зависимости от типа этикетки передайте значение в метод [/v1/posting/fbs/package-label/get](#operation/PostingAPI_GetLabelBatch).', json_schema_extra={'format': 'int64'})
    task_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип задания на формирование этикеток:\n- `big_label` — для обычной этикетки,\n- `small_label` — для маленькой этикетки.\n')


class OzonV1GetLabelBatchRequest(OzonFbsModel):
    __openapi_name__ = 'v1GetLabelBatchRequest'
    task_id: int = Field(..., description='Номер задания на формирование этикеток из ответа метода [/v1/posting/fbs/package-label/create](#operation/PostingAPI_CreateLabelBatch).', json_schema_extra={'format': 'int64'})


class OzonV1GetLabelBatchResponse(OzonFbsModel):
    __openapi_name__ = 'v1GetLabelBatchResponse'
    result: OzonV1GetLabelBatchResponseResult = Field(_OPTIONAL_FIELD_DEFAULT)


class OzonV1GetLabelBatchResponseResult(OzonFbsModel):
    __openapi_name__ = 'v1GetLabelBatchResponseResult'
    'Результат работы метода.'
    error: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Код ошибки.')
    file_url: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Ссылка на файл с этикетками.')
    printed_postings_count: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество напечатанных этикеток.', json_schema_extra={'format': 'int32'})
    status: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Статус формирования этикеток:\n- `pending` — задание в очереди.\n- `in_progress` — формируются.\n- `completed` — файл с этикетками готов.\n- `error` — ошибка при создании файла.\n')
    unprinted_postings: list[OzonResultUnprintedPosting] = Field(_OPTIONAL_FIELD_DEFAULT, description='Информация об ошибках, из-за которых не получилось напечатать этикетки.')
    unprinted_postings_count: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество этикеток, которые не получилось напечатать.', json_schema_extra={'format': 'int32'})


class OzonResultUnprintedPosting(OzonFbsModel):
    __openapi_name__ = 'ResultUnprintedPosting'
    msg: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Причина ошибки.')
    posting_number: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер отправления.')


class OzonPostingPostingFBSPackageLabelRequest(OzonFbsModel):
    __openapi_name__ = 'postingPostingFBSPackageLabelRequest'
    posting_number: list[str] = Field(..., description='Идентификатор отправления.')


class OzonPostingPostingFBSPackageLabelResponse(OzonFbsModel):
    __openapi_name__ = 'postingPostingFBSPackageLabelResponse'
    file_content: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Содержание файла в бинарном виде.', json_schema_extra={'format': 'byte'})
    file_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название файла.')
    content_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип файла.')


class OzonV1CarriageCreateRequest(OzonFbsModel):
    __openapi_name__ = 'v1CarriageCreateRequest'
    all_blr_traceable: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если нужно создать отгрузку с прослеживаемыми товарами.\n')
    delivery_method_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор метода доставки.', json_schema_extra={'format': 'int64'})
    departure_date: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата отгрузки. По умолчанию — текущая дата.', json_schema_extra={'format': 'date-time'})


class OzonV1CarriageCreateResponse(OzonFbsModel):
    __openapi_name__ = 'v1CarriageCreateResponse'
    carriage_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор перевозки.', json_schema_extra={'format': 'int64'})


class OzonV1SetPostingsRequest(OzonFbsModel):
    __openapi_name__ = 'v1SetPostingsRequest'
    carriage_id: int = Field(..., description='Идентификатор отгрузки.', json_schema_extra={'format': 'int64'})
    posting_numbers: list[str] = Field(..., description='Актуальный список отправлений.')


class OzonV1SetPostingsResponse(OzonFbsModel):
    __openapi_name__ = 'v1SetPostingsResponse'
    result: list[OzonSetPostingsResponseResult] = Field(_OPTIONAL_FIELD_DEFAULT)


class OzonSetPostingsResponseResult(OzonFbsModel):
    __openapi_name__ = 'SetPostingsResponseResult'
    error: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Описание ошибки.')
    posting_number: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Номер отправления.')
    result: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Результат обработки запроса. `true`, если запрос был обработан успешно.\n')


class OzonV1CarriageApproveRequest(OzonFbsModel):
    __openapi_name__ = 'v1CarriageApproveRequest'
    carriage_id: int = Field(..., description='Идентификатор отгрузки.', json_schema_extra={'format': 'int64'})
    containers_count: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество грузовых мест. \n\nИспользуйте параметр, если вы подключены к доверительной приёмке и отгружаете заказы грузовыми местами. Если вы не подключены к доверительной приёмке, пропустите его.\n', json_schema_extra={'format': 'int32'})


class OzonV1CarriageApproveResponse(OzonFbsModel):
    __openapi_name__ = 'v1CarriageApproveResponse'
    pass


class OzonCarriageCarriageGetRequest(OzonFbsModel):
    __openapi_name__ = 'carriageCarriageGetRequest'
    carriage_id: int = Field(..., description='Идентификатор перевозки.', json_schema_extra={'format': 'int64'})


class OzonCarriageCarriageGetResponse(OzonFbsModel):
    __openapi_name__ = 'carriageCarriageGetResponse'
    act_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип акта приёма-передачи. Актуально для продавцов FBS.')
    all_blr_traceable: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если отгрузка с прослеживаемыми товарами.\n')
    is_waybill_enabled: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если доступна печать транспортной накладной.\n')
    is_econom: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если отгрузка относится к товарам «Суперэконом».\n')
    arrival_pass_ids: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Список идентификаторов пропусков, оформленных на перевозку.')
    available_actions: list[str] = Field(_OPTIONAL_FIELD_DEFAULT, description='Доступные действия с перевозкой:\n- `get_shipping_list` — получить лист отгрузки;\n- `get_act_of_acceptance` — получить акт приёма-передачи;\n- `get_waybill` — получить товарную накладную в формате PDF;\n- `set_arrival_passes` — [оформить пропуск](#operation/carriagePassCreate).\n')
    cancel_availability: OzonCarriageCarriageGetResponseCancelAvailability = Field(_OPTIONAL_FIELD_DEFAULT)
    carriage_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор перевозки.', json_schema_extra={'format': 'int64'})
    company_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор продавца.', json_schema_extra={'format': 'int64'})
    containers_count: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество грузовых мест.', json_schema_extra={'format': 'int32'})
    created_at: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата создания перевозки.', json_schema_extra={'format': 'date-time'})
    delivery_method_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор метода доставки.', json_schema_extra={'format': 'int64'})
    departure_date: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата выполнения перевозки.')
    first_mile_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип первой мили.')
    has_postings_for_next_carriage: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если есть отправления, которые не попали в перевозку, но нужно отгрузить.\n')
    integration_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип перевозки.')
    is_container_label_printed: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если вы уже напечатали этикетки на грузовые места.\n')
    is_partial: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если перевозка частичная.\n')
    partial_num: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Порядковый номер частичной перевозки.', json_schema_extra={'format': 'int64'})
    retry_count: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Количество повторных попыток создания перевозки.', json_schema_extra={'format': 'int32'})
    status: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Статус перевозки:\n- `received` — идёт приёмка,\n- `closed` — завершена после приёмки,\n- `sended` — отправлена,\n- `cancelled` — отменена.\n')
    tpl_provider_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор провайдера доставки.', json_schema_extra={'format': 'int64'})
    updated_at: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Дата последнего обновления информации о перевозке.', json_schema_extra={'format': 'date-time'})
    warehouse_id: int = Field(_OPTIONAL_FIELD_DEFAULT, description='Идентификатор склада.', json_schema_extra={'format': 'int64'})


class OzonCarriageCarriageGetResponseCancelAvailability(OzonFbsModel):
    __openapi_name__ = 'carriageCarriageGetResponseCancelAvailability'
    'Возможность отмены.'
    is_cancel_available: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='`true`, если перевозку можно отменить.\n')
    reason: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Причина, почему перевозку нельзя отменить.')


class OzonV2PostingFBSGetBarcodeRequest(OzonFbsModel):
    __openapi_name__ = 'v2PostingFBSGetBarcodeRequest'
    id: int = Field(..., description='Идентификатор перевозки.', json_schema_extra={'format': 'int64'})


class OzonV2PostingFBSGetBarcodeResponse(OzonFbsModel):
    __openapi_name__ = 'v2PostingFBSGetBarcodeResponse'
    file_content: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Изображение со штрихкодом в бинарном виде.')
    file_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название файла.')
    content_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип файла.')


class OzonV2PostingFBSGetBarcodeTextResponse(OzonFbsModel):
    __openapi_name__ = 'v2PostingFBSGetBarcodeTextResponse'
    result: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Штрихкод в текстовом виде.')


class OzonV2PostingFBSGetDigitalActRequest(OzonFbsModel):
    __openapi_name__ = 'v2PostingFBSGetDigitalActRequest'
    id: int = Field(..., description='Номер задания на формирование документов (также идентификатор перевозки) из метода [POST /v2/posting/fbs/act/create](#operation/PostingAPI_PostingFBSActCreate).', json_schema_extra={'format': 'int64'})
    doc_type: Any = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип электронного документа:\n- `act_of_acceptance` — лист отгрузки,\n- `act_of_mismatch` — акт о расхождениях,\n- `act_of_excess` — акт об излишках,\n- `waybill` — транспортная накладная.\n', json_schema_extra={'format': 'string'})


class OzonV2PostingFBSGetDigitalActResponse(OzonFbsModel):
    __openapi_name__ = 'v2PostingFBSGetDigitalActResponse'
    file_content: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Содержание файла в бинарном виде.', json_schema_extra={'format': 'byte'})
    file_name: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Название файла.')
    content_type: str = Field(_OPTIONAL_FIELD_DEFAULT, description='Тип файла.')


class OzonV2MovePostingToAwaitingDeliveryRequest(OzonFbsModel):
    __openapi_name__ = 'v2MovePostingToAwaitingDeliveryRequest'
    posting_number: list[str] = Field(..., description='Идентификатор отправления. Максимальное количество в одном запросе — 100.')


class OzonPostingBooleanResponse(OzonFbsModel):
    __openapi_name__ = 'postingBooleanResponse'
    result: bool = Field(_OPTIONAL_FIELD_DEFAULT, description='Результат обработки запроса. `true`, если запрос выполнился без ошибок.')


MODEL_BY_OPENAPI_NAME: dict[str, type[BaseModel] | type[Enum]] = {
    'posting.v4.PostingFbsUnfulfilledListRequest': OzonPostingV4PostingFbsUnfulfilledListRequest,
    'posting.v4.PostingFbsUnfulfilledListRequest.Filter': OzonPostingV4PostingFbsUnfulfilledListRequestFilter,
    'posting.v4.PostingFbsUnfulfilledListRequest.Filter.LastChangedStatusDate': OzonPostingV4PostingFbsUnfulfilledListRequestFilterLastChangedStatusDate,
    'posting.v4.PostingFbsUnfulfilledListRequest.SortDir.Enum': OzonPostingV4PostingFbsUnfulfilledListRequestSortDirEnum,
    'posting.v4.PostingFbsUnfulfilledListRequest.With': OzonPostingV4PostingFbsUnfulfilledListRequestWith,
    'posting.v4.PostingFbsUnfulfilledListResponse': OzonPostingV4PostingFbsUnfulfilledListResponse,
    'posting.v4.PostingFbsUnfulfilledListResponse.Postings': OzonPostingV4PostingFbsUnfulfilledListResponsePostings,
    'posting.v4.PostingFbsUnfulfilledListResponse.Postings.Addressee': OzonPostingV4PostingFbsUnfulfilledListResponsePostingsAddressee,
    'posting.v4.PostingFbsUnfulfilledListResponse.Postings.AnalyticsData': OzonPostingV4PostingFbsUnfulfilledListResponsePostingsAnalyticsData,
    'posting.v4.PostingFbsUnfulfilledListResponse.Postings.Barcodes': OzonPostingV4PostingFbsUnfulfilledListResponsePostingsBarcodes,
    'posting.v4.PostingFbsUnfulfilledListResponse.Postings.Cancellation': OzonPostingV4PostingFbsUnfulfilledListResponsePostingsCancellation,
    'posting.v4.PostingFbsUnfulfilledListResponse.Postings.Customer': OzonPostingV4PostingFbsUnfulfilledListResponsePostingsCustomer,
    'posting.v4.PostingFbsUnfulfilledListResponse.Postings.Customer.Address': OzonPostingV4PostingFbsUnfulfilledListResponsePostingsCustomerAddress,
    'posting.v4.PostingFbsUnfulfilledListResponse.Postings.Container': OzonPostingV4PostingFbsUnfulfilledListResponsePostingsContainer,
    'posting.v4.PostingFbsUnfulfilledListResponse.Postings.Container.CargoType.Enum': OzonPostingV4PostingFbsUnfulfilledListResponsePostingsContainerCargoTypeEnum,
    'posting.v4.PostingFbsUnfulfilledListResponse.Postings.DeliveryMethod': OzonPostingV4PostingFbsUnfulfilledListResponsePostingsDeliveryMethod,
    'posting.v4.PostingFbsUnfulfilledListResponse.Postings.ExternalOrder': OzonPostingV4PostingFbsUnfulfilledListResponsePostingsExternalOrder,
    'posting.v4.PostingFbsUnfulfilledListResponse.Postings.FinancialData': OzonPostingV4PostingFbsUnfulfilledListResponsePostingsFinancialData,
    'posting.v4.PostingFbsUnfulfilledListResponse.Postings.FinancialData.Products': OzonPostingV4PostingFbsUnfulfilledListResponsePostingsFinancialDataProducts,
    'posting.v4.PostingFbsUnfulfilledListResponse.Postings.FinancialData.Products.Commission': OzonPostingV4PostingFbsUnfulfilledListResponsePostingsFinancialDataProductsCommission,
    'money.postingMoney': OzonMoneyPostingMoney,
    'posting.v4.PostingFbsUnfulfilledListResponse.Postings.LegalInfo': OzonPostingV4PostingFbsUnfulfilledListResponsePostingsLegalInfo,
    'posting.v4.PostingFbsUnfulfilledListResponse.Postings.Optional': OzonPostingV4PostingFbsUnfulfilledListResponsePostingsOptional,
    'posting.v4.PostingFbsUnfulfilledListResponse.Postings.Products': OzonPostingV4PostingFbsUnfulfilledListResponsePostingsProducts,
    'posting.v4.PostingFbsUnfulfilledListResponse.Postings.Requirements': OzonPostingV4PostingFbsUnfulfilledListResponsePostingsRequirements,
    'posting.v4.PostingFbsUnfulfilledListResponse.Postings.SortingCenter': OzonPostingV4PostingFbsUnfulfilledListResponsePostingsSortingCenter,
    'posting.v4.PostingFbsUnfulfilledListResponse.Postings.Tariffication': OzonPostingV4PostingFbsUnfulfilledListResponsePostingsTariffication,
    'money.Money.Current_tariff_charge': OzonMoneyMoneyCurrentTariffCharge,
    'money.Money.Current_tariff_min_charge': OzonMoneyMoneyCurrentTariffMinCharge,
    'money.Money.Next_tariff_charge': OzonMoneyMoneyNextTariffCharge,
    'money.Money.Next_tariff_min_charge': OzonMoneyMoneyNextTariffMinCharge,
    'posting.v4.PostingFbsUnfulfilledListResponse.Postings.TarifficationStep': OzonPostingV4PostingFbsUnfulfilledListResponsePostingsTarifficationStep,
    'rpcStatus': OzonRpcStatus,
    'protobufAny': OzonProtobufAny,
    'posting.v4.PostingFbsListRequest': OzonPostingV4PostingFbsListRequest,
    'posting.v4.PostingFbsListRequest.Filter': OzonPostingV4PostingFbsListRequestFilter,
    'posting.v4.PostingFbsListRequest.Filter.LastChangedStatusDate': OzonPostingV4PostingFbsListRequestFilterLastChangedStatusDate,
    'posting.v4.PostingFbsListRequest.SortDir.Enum': OzonPostingV4PostingFbsListRequestSortDirEnum,
    'posting.v4.PostingFbsListRequest.With': OzonPostingV4PostingFbsListRequestWith,
    'posting.v4.PostingFbsListResponse': OzonPostingV4PostingFbsListResponse,
    'posting.v4.PostingFbsListResponse.Postings': OzonPostingV4PostingFbsListResponsePostings,
    'posting.v4.PostingFbsListResponse.Postings.Addressee': OzonPostingV4PostingFbsListResponsePostingsAddressee,
    'posting.v4.PostingFbsListResponse.Postings.AnalyticsData': OzonPostingV4PostingFbsListResponsePostingsAnalyticsData,
    'posting.v4.PostingFbsListResponse.Postings.Barcodes': OzonPostingV4PostingFbsListResponsePostingsBarcodes,
    'posting.v4.PostingFbsListResponse.Postings.Cancellation': OzonPostingV4PostingFbsListResponsePostingsCancellation,
    'posting.v4.PostingFbsListResponse.Postings.Customer': OzonPostingV4PostingFbsListResponsePostingsCustomer,
    'posting.v4.PostingFbsListResponse.Postings.Customer.Address': OzonPostingV4PostingFbsListResponsePostingsCustomerAddress,
    'posting.v4.PostingFbsListResponse.Postings.Container': OzonPostingV4PostingFbsListResponsePostingsContainer,
    'posting.v3.FbsPosting.Container.CargoType.Enum': OzonPostingV3FbsPostingContainerCargoTypeEnum,
    'posting.v4.PostingFbsListResponse.Postings.DeliveryMethod': OzonPostingV4PostingFbsListResponsePostingsDeliveryMethod,
    'posting.v4.PostingFbsListResponse.Postings.ExternalOrder': OzonPostingV4PostingFbsListResponsePostingsExternalOrder,
    'posting.v4.PostingFbsListResponse.Postings.FinancialData': OzonPostingV4PostingFbsListResponsePostingsFinancialData,
    'posting.v4.PostingFbsListResponse.Postings.FinancialData.Products': OzonPostingV4PostingFbsListResponsePostingsFinancialDataProducts,
    'posting.v4.PostingFbsListResponse.Postings.FinancialData.Products.Commission': OzonPostingV4PostingFbsListResponsePostingsFinancialDataProductsCommission,
    'posting.v4.PostingFbsListResponse.Postings.LegalInfo': OzonPostingV4PostingFbsListResponsePostingsLegalInfo,
    'posting.v4.PostingFbsListResponse.Postings.Optional': OzonPostingV4PostingFbsListResponsePostingsOptional,
    'posting.v4.PostingFbsListResponse.Postings.Products': OzonPostingV4PostingFbsListResponsePostingsProducts,
    'posting.v4.PostingFbsListResponse.Postings.Requirements': OzonPostingV4PostingFbsListResponsePostingsRequirements,
    'posting.v4.PostingFbsListResponse.Postings.SortingCenter': OzonPostingV4PostingFbsListResponsePostingsSortingCenter,
    'posting.v4.PostingFbsListResponse.Postings.Tariffication': OzonPostingV4PostingFbsListResponsePostingsTariffication,
    'posting.v4.PostingFbsListResponse.Postings.TarifficationStep': OzonPostingV4PostingFbsListResponsePostingsTarifficationStep,
    'postingv3GetFbsPostingRequest': OzonPostingv3GetFbsPostingRequest,
    'postingv3FbsPostingWithParamsExamplars': OzonPostingv3FbsPostingWithParamsExamplars,
    'v3GetFbsPostingResponseV3': OzonV3GetFbsPostingResponseV3,
    'v3FbsPostingDetail': OzonV3FbsPostingDetail,
    'v3AdditionalDataItem': OzonV3AdditionalDataItem,
    'v3Addressee': OzonV3Addressee,
    'v3FbsPostingAnalyticsData': OzonV3FbsPostingAnalyticsData,
    'v3Barcodes': OzonV3Barcodes,
    'v3Cancellation': OzonV3Cancellation,
    'FbsPostingDetailCourier': OzonFbsPostingDetailCourier,
    'v3Customer': OzonV3Customer,
    'v3Address': OzonV3Address,
    'v3DeliveryMethod': OzonV3DeliveryMethod,
    'posting.v3.FbsPostingDetail.ExternalOrder': OzonPostingV3FbsPostingDetailExternalOrder,
    'v3PostingFinancialData': OzonV3PostingFinancialData,
    'PostingFinancialDataProduct': OzonPostingFinancialDataProduct,
    'v2FboSinglePostingLegalInfo': OzonV2FboSinglePostingLegalInfo,
    'v3FbsPostingDetailOptional': OzonV3FbsPostingDetailOptional,
    'v3FbsPostingProductExemplarsV3': OzonV3FbsPostingProductExemplarsV3,
    'v3FbsPostingExemplarProductV3': OzonV3FbsPostingExemplarProductV3,
    'v3FbsPostingProductExemplarInfoV3': OzonV3FbsPostingProductExemplarInfoV3,
    'v3PostingProductDetail': OzonV3PostingProductDetail,
    'v3Dimensions': OzonV3Dimensions,
    'FbsPostingDetailPrrOption': OzonFbsPostingDetailPrrOption,
    'v3FbsPostingDetailRelatedPostings': OzonV3FbsPostingDetailRelatedPostings,
    'v3FbsPostingRequirementsV3': OzonV3FbsPostingRequirementsV3,
    'posting.v3.FbsPostingDetail.SortingCenter': OzonPostingV3FbsPostingDetailSortingCenter,
    'v3FbsTariffication': OzonV3FbsTariffication,
    'v1GetRestrictionsRequest': OzonV1GetRestrictionsRequest,
    'v1GetRestrictionsResponse': OzonV1GetRestrictionsResponse,
    'v1Restriction': OzonV1Restriction,
    'v2FbsPostingProductCountryListRequest': OzonV2FbsPostingProductCountryListRequest,
    'v2FbsPostingProductCountryListResponse': OzonV2FbsPostingProductCountryListResponse,
    'v2FbsPostingProductCountryListResponseResult': OzonV2FbsPostingProductCountryListResponseResult,
    'googlerpcStatus': OzonGooglerpcStatus,
    'v2FbsPostingProductCountrySetRequest': OzonV2FbsPostingProductCountrySetRequest,
    'v2FbsPostingProductCountrySetResponse': OzonV2FbsPostingProductCountrySetResponse,
    'v6FbsPostingProductExemplarCreateOrGetV6Request': OzonV6FbsPostingProductExemplarCreateOrGetV6Request,
    'v6FbsPostingProductExemplarCreateOrGetV6Response': OzonV6FbsPostingProductExemplarCreateOrGetV6Response,
    'FbsPostingProductExemplarCreateOrGetV6ResponseProduct': OzonFbsPostingProductExemplarCreateOrGetV6ResponseProduct,
    'ProductExemplar': OzonProductExemplar,
    'ExemplarMark': OzonExemplarMark,
    'v5FbsPostingProductExemplarValidateV5Request': OzonV5FbsPostingProductExemplarValidateV5Request,
    'v5FbsPostingProductExemplarValidateV5RequestProduct': OzonV5FbsPostingProductExemplarValidateV5RequestProduct,
    'v5FbsPostingProductExemplarValidateV5RequestProductExemplar': OzonV5FbsPostingProductExemplarValidateV5RequestProductExemplar,
    'v5FbsPostingProductExemplarValidateV5RequestProductExemplarMark': OzonV5FbsPostingProductExemplarValidateV5RequestProductExemplarMark,
    'v5FbsPostingProductExemplarValidateV5Response': OzonV5FbsPostingProductExemplarValidateV5Response,
    'v5FbsPostingProductExemplarValidateV5ResponseProduct': OzonV5FbsPostingProductExemplarValidateV5ResponseProduct,
    'v5FbsPostingProductExemplarValidateV5ResponseProductExemplar': OzonV5FbsPostingProductExemplarValidateV5ResponseProductExemplar,
    'v5FbsPostingProductExemplarValidateV5ResponseProductExemplarMark': OzonV5FbsPostingProductExemplarValidateV5ResponseProductExemplarMark,
    'v6FbsPostingProductExemplarSetV6Request': OzonV6FbsPostingProductExemplarSetV6Request,
    'FbsPostingProductExemplarSetV6RequestProducts': OzonFbsPostingProductExemplarSetV6RequestProducts,
    'FbsPostingProductExemplarSetV6RequestExemplars': OzonFbsPostingProductExemplarSetV6RequestExemplars,
    'ExemplarsMarks': OzonExemplarsMarks,
    'v5FbsPostingProductExemplarStatusV5Request': OzonV5FbsPostingProductExemplarStatusV5Request,
    'v5FbsPostingProductExemplarStatusV5Response': OzonV5FbsPostingProductExemplarStatusV5Response,
    'v5FbsPostingProductExemplarStatusV5ResponseProduct': OzonV5FbsPostingProductExemplarStatusV5ResponseProduct,
    'v5FbsPostingProductExemplarStatusV5ResponseProductExemplar': OzonV5FbsPostingProductExemplarStatusV5ResponseProductExemplar,
    'v5FbsPostingProductExemplarStatusV5ResponseProductExemplarMark': OzonV5FbsPostingProductExemplarStatusV5ResponseProductExemplarMark,
    'postingv3PostingMultiBoxQtySetV3Request': OzonPostingv3PostingMultiBoxQtySetV3Request,
    'postingv3PostingMultiBoxQtySetV3Response': OzonPostingv3PostingMultiBoxQtySetV3Response,
    'postingv3PostingMultiBoxQtySetV3ResponseResult': OzonPostingv3PostingMultiBoxQtySetV3ResponseResult,
    'fbsv4FbsPostingShipV4Request': OzonFbsv4FbsPostingShipV4Request,
    'FbsPostingShipV4RequestPackage': OzonFbsPostingShipV4RequestPackage,
    'FbsPostingShipV4RequestPackageProduct': OzonFbsPostingShipV4RequestPackageProduct,
    'FbsPostingShipV4RequestWith': OzonFbsPostingShipV4RequestWith,
    'fbsv4FbsPostingShipV4Response': OzonFbsv4FbsPostingShipV4Response,
    'FbsPostingShipV4ResponseShipAdditionalData': OzonFbsPostingShipV4ResponseShipAdditionalData,
    'fbsv4PostingProductDetailWithoutDimensions': OzonFbsv4PostingProductDetailWithoutDimensions,
    'v4FbsPostingShipPackageV4Request': OzonV4FbsPostingShipPackageV4Request,
    'v4FbsPostingShipPackageV4RequestProduct': OzonV4FbsPostingShipPackageV4RequestProduct,
    'v4FbsPostingShipPackageV4Response': OzonV4FbsPostingShipPackageV4Response,
    'v1CreateLabelBatchRequest': OzonV1CreateLabelBatchRequest,
    'v2CreateLabelBatchResponse': OzonV2CreateLabelBatchResponse,
    'v2CreateLabelBatchResponseResult': OzonV2CreateLabelBatchResponseResult,
    'v2CreateLabelBatchResponseResultTasks': OzonV2CreateLabelBatchResponseResultTasks,
    'v1GetLabelBatchRequest': OzonV1GetLabelBatchRequest,
    'v1GetLabelBatchResponse': OzonV1GetLabelBatchResponse,
    'v1GetLabelBatchResponseResult': OzonV1GetLabelBatchResponseResult,
    'ResultUnprintedPosting': OzonResultUnprintedPosting,
    'postingPostingFBSPackageLabelRequest': OzonPostingPostingFBSPackageLabelRequest,
    'postingPostingFBSPackageLabelResponse': OzonPostingPostingFBSPackageLabelResponse,
    'v1CarriageCreateRequest': OzonV1CarriageCreateRequest,
    'v1CarriageCreateResponse': OzonV1CarriageCreateResponse,
    'v1SetPostingsRequest': OzonV1SetPostingsRequest,
    'v1SetPostingsResponse': OzonV1SetPostingsResponse,
    'SetPostingsResponseResult': OzonSetPostingsResponseResult,
    'v1CarriageApproveRequest': OzonV1CarriageApproveRequest,
    'v1CarriageApproveResponse': OzonV1CarriageApproveResponse,
    'carriageCarriageGetRequest': OzonCarriageCarriageGetRequest,
    'carriageCarriageGetResponse': OzonCarriageCarriageGetResponse,
    'carriageCarriageGetResponseCancelAvailability': OzonCarriageCarriageGetResponseCancelAvailability,
    'v2PostingFBSGetBarcodeRequest': OzonV2PostingFBSGetBarcodeRequest,
    'v2PostingFBSGetBarcodeResponse': OzonV2PostingFBSGetBarcodeResponse,
    'v2PostingFBSGetBarcodeTextResponse': OzonV2PostingFBSGetBarcodeTextResponse,
    'v2PostingFBSGetDigitalActRequest': OzonV2PostingFBSGetDigitalActRequest,
    'v2PostingFBSGetDigitalActResponse': OzonV2PostingFBSGetDigitalActResponse,
    'v2MovePostingToAwaitingDeliveryRequest': OzonV2MovePostingToAwaitingDeliveryRequest,
    'postingBooleanResponse': OzonPostingBooleanResponse,
}

for _ozon_model in MODEL_BY_OPENAPI_NAME.values():
    if isinstance(_ozon_model, type) and issubclass(_ozon_model, BaseModel):
        _ozon_model.model_rebuild(_types_namespace=globals())

__all__ = [*MODEL_BY_OPENAPI_NAME, 'MODEL_BY_OPENAPI_NAME', 'OzonFbsModel']
