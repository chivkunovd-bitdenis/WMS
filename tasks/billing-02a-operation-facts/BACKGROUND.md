# Фон и контракт данных: волна 2А

## Граница надёжности

`DocumentEvent` — наблюдательный журнал. Его PostgreSQL trigger и best-effort writer специально не
ломают складскую операцию при ошибке, поэтому он не годится единственным источником денег или
выработки. `OperationFact` — отдельный доменный факт: после того как каноническое действие успешно
подтверждено, запись факта выполняется в той же unit-of-work и обязана либо сохраниться вместе с
действием, либо не позволить считать действие подтверждённым. Это не повторная запись
`DocumentEvent` и не изменение его отказоустойчивого контракта.

## Источники и дедупликация

Это сводная таблица границы надёжности; полная исполняемая матрица «реальное событие → code →
source ID → quantity/lines → actor → reversal» находится в §5 `TASK.md` и имеет приоритет.

| Операция | Реальный источник в текущем коде | Разрешённый исход факта |
|---|---|---|
| Приёмка, возврат | terminal `STATUS_DONE` у `InboundIntakeRequest`, его `posted_qty` и новый durable `completed_by_user_id` | документ `req.id`, отдельно по `operation_type` |
| Подбор FBS WB | `FbsOrderPickEvent` | ID отдельного `picked`/`undone` event |
| Подбор FBS Ozon | `FbsOrderProductPick` с новыми durable `picked_by_user_id`/`undone_by_user_id` | ID строки pick; undo различается operation code |
| Упаковка | только item-level `PackagingTaskEvent` pack и explicit undo | ID отдельного event; cancel/complete/label/confirm без lines не являются source |
| Отгрузка | `MarketplaceUnloadRequest` с `STATUS_SHIPPED`/shipped cancellation и новыми durable авторами | `req.id`, code различает completed/reversal |
| Хранение | fixed `StorageStatement` + `StorageMeasurement` | measurement ID, либо statement ID для нулевого документа |

Факт получает один `source_kind`, один устойчивый `source_event_id` и одну операцию. Идемпотентный
ключ хранится и в сервисе проверяется вместе с immutable source tuple. Одинаковый retry возвращает
тот же факт; другой новый физический action после отмены имеет новый source-id и создаёт новый факт.
Только explicit undo/cancel, у которого текущий источник содержит однозначные quantity и исходный
action, создаёт reversal-fact со ссылкой `reversal_of_id`; исходный факт не редактируется. Одна
строка не может одновременно прийти из `DocumentEvent` и специализированного источника —
`DocumentEvent` сознательно исключён из reader/recovery.

## Количество, снимки и tenant isolation

`OperationFact.item_quantity` и строки всегда обозначают фактически обработанные штуки. Ставка,
расчётная единица и сумма в эту модель не входят. Снимки номера документа, селлера, товара/SKU и
автора сохраняются рядом с FK: удаление/переименование не переписывает историю. `tenant_id` —
обязателен у факта и строк; service перед любой связью проверяет tenant исходного документа,
селлера, склада, товара, автора и reversal. Cross-tenant ссылка — ошибка, не «пустое поле».

Нужны как минимум индексы `(tenant_id, seller_id, occurred_at, id)`,
`(tenant_id, actor_user_id, occurred_at, id)`, `(tenant_id, operation_code, occurred_at, id)`,
линии по `operation_fact_id` и уникальные partial/compound индексы из TASK. Порядок `(occurred_at,
id)` используется будущей cursor-pagination и recovery.

## Cutover и legacy

Один системный cutover записывается миграцией ровно один раз. До него новый read-model читает только
legacy `BillingLedgerEntry`; начиная с него — только `OperationFact`. Никакой массовой реконструкции
старого ledger и никаких предположений о товарах для unit=`document`. Тест обязан поставить действие
на границе и доказать: оно видно в одной половине, не ноль и не два раза. `BillingLedgerEntry`, его
уникальность и старые суммы не меняются.

## Recovery

Recovery является повторяемым сервисом, а не фоновым бесконтрольным job и не HTTP API. Он принимает
явный tenant и строгий период/набор исходных ID, берёт только реальный source из таблицы выше,
создаёт отсутствующие факты через штатный writer и возвращает детерминированную сверку. Он не
редактирует факты, не пересчитывает тарифы, не переписывает ledger и не «угадывает» несуществующий
источник: например не создаёт fact по `PackagingTaskEvent.complete`, по `cancel` с quantity zero
или по `DocumentEvent`. Повтор recovery не создаёт дубликат; конфликт source tuple/idempotency key
завершает операцию именованной ошибкой и попадает в proof.

## Миграция

Миграция только добавляет таблицы, FK, constraints и индексы и продолжает единственный Alembic head
`20260825_0109`. Downgrade не является разрешением удалить production-историю. PostgreSQL proof
проверяет один head, состав индексов, partial uniqueness, FK и recovery/retry в настоящей БД.
