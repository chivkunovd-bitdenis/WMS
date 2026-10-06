# WMS-675 — side effects существующего пути WMS-662

Проверка кода общего кандидата `7f9d720ee` (runtime включает узкий fix662b4043c0df).
Никакого выполнения восстановления, измененияDB или внешней записи не было.

Штатный путь `conduct_supply → write_off_order → apply_fbs_supply_write_off →
record_movement_and_adjust_balance` записывает точный warehouse расход и планирует
`schedule_seller_stock_publish` (inventory_service.py:832). Полное снятие резерва
`reduce_ozon_reservations → update_fbs_order_reservation` также планирует публикацию
при реально удалённых reserve rows (inventory_service.py:241). Это существующий
обычный процесс, не новый independent учёт и не основание создавать suppress режим
или product monkeypatch. Операторский лимит не меняется.

Publisher хранит pending intent по tenant/seller/marketplace в session.info и
регистрирует after_commit callback. Затем отправляет Celery task либо in-process
async task; seller publishing выбирает активные configured WB/Ozon stock bindings
и применяет штатный расчёт min(cap, free). Публикация может охватить подключения
селлера шире этих шести product IDs. Точные внешние количества и число запросов
нельзя назвать без текущих caps/bindings/остатков и результата publisher.

Не обещать «ровно одна внешняя публикация после outer commit»: у текущего
callback нет nested guard. Conduct/write-off/billing используют savepoints,
а локальный pure SQLAlchemy probe безDB/marketplace показал after_commit на
nested commit и outer commit. Это подтверждённая граница текущего code/hook,
а не новый live outcome или разрешение изменить publisher в этой задаче.
Повторный расчёт в штатном publisher не означает новый физический расход.

Из fresh live-proof675 scope шесть товаров. Положительные26единиц относятся к5:

| product_id | Положительные | Отмены | Ожидание | reserve положительных в reader snapshot |
|---|---:|---:|---:|---:|
| 2ccde129-ed49-44fd-8dcc-4dd092581e26 | 8 | 3 | 0 | 5 |
| 80fa2a1e-1974-4e6e-8497-2defd0176bd5 | 7 | 0 | 0 | 5 |
| 1a99998b-1576-4e7f-9f9a-cf9eaf14907e | 4 | 1 | 0 | 2 |
| 4d7e4a3d-954e-48f6-94a3-45729f2654d0 | 5 | 0 | 0 | 2 |
| 7e159b28-72f7-4f3c-8f92-ebca10e054db | 2 | 0 | 0 | 1 |
| 605bdc71-baae-43dd-9ed4-fb37e07906c0 | 0 | 0 | 1 | 0 |

Шестой товар не получает нового физического расхода из ожидания. Если свежий
scopedSQL исполнителя675 сохраняет эти же резервы и26нулевыхledger,
при полном проведении26 уменьшатся физический остаток на26 и резерв
положительных на15; тогда свободный остаток по этим пяти товарам суммарно
уменьшится на11. Это условный расчёт из reader snapshot, не подмена freshSQL.
Отмены не используются как положительная передача; waiting резерв сохраняется.

Для11уже billeddelivered заказов `record_fbs_order_confirmed` вызывает
write_operation_fact с прежним source order ID/idempotency_key и
cumulative_handover=True; existing fact quantities растут только до max.
Оба существующих charge service keys (fbs_order/packing) передаются в
record_operational_charge с тем же order source ID. `_extend_handover_charge`
возвращает existing entry, если входящий product physical quantity уже покрыт
активными строками. При уже учтённой единице нового начисления не нужно.
Issued invoice источники сохраняются. Это проверка кода; точное состояние
11actual charges подтверждает новый scopedSQL675, не этот статический отчёт.

План должен явно включать обычную публикацию доступного остатка как side effect
разрешённого восстановления. Сначала сверить exact IDs/ledger/reserves/facts;
восстановить лишь missing delta существующим сервисом; reread ledger/stock/billing;
отдельно проверить queued/published stock outcome. Самостоятельный live repair
и создание альтернативного local-only режима этим отчётом не выполняются.
