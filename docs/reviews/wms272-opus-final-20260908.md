# WMS-272: Opus CLI max review основных исправлений

Запуск начат с указанием 08f2ac39. Во время чтения исходники дополнены 12c230bd: stream-лог содержит финальные accepted - bound и возврат partial_rejection. Поскольку итоговый текст не выносит отдельный вердикт по этой маленькой дельте, она вместе с устранением ложного timeout дополнительно передана отдельным самодостаточным diff в финальный CLI-review. Замечание о пустом order_ids независимо отвергнуто; ложный timeout устранён в ad116f0d.

Проверил только правки между `8baa351f` и `08f2ac39` в `backend/app/services/fbs_supply_service.py` и `backend/tests/test_fbs_create_http_connection.py`. Модель — Opus 4.7. Прогонов, HTTP, изменений и делегирования не было.

## Что сходится с кодом

- **Транзакция закрывается до HTTP create.** `fbs_supply_service.py:674` — `session.commit()` перед `create_marketplace_supply`; `session.expire_all()` на входе в новую транзакцию под advisory-блокировкой продавца (`:712`).
- **Advisory-блокировка транзакционная и короткая.** `marketplace_seller_lock_service.py:54-58` действительно берёт `pg_try_advisory_xact_lock`, а не сессионный, поэтому commit на `:824` её отпускает. Отдельного `release_marketplace_seller_lock` не вызывается — `finally` в `marketplace_seller_lock_service.py:102-104` корректно ничего не делает при `transaction_scoped=True`.
- **Локальная попытка сохраняется только с реальным `wb_supply_id`.** `fbs_supply_service.py:666-688` держит `wb_supply_id` в локальной переменной до входа в блокировку; `create_pending_operation` + `mark_operation_pending_confirmation` + запись `FbsSupply.wb_supply_id = wb_supply_id` идут одним коммитом на `:817-824`. Оверинжиниринговых новых таблиц/лизов/TTL нет.
- **Проигравший создатель повторно проходит проверку и переезжает на победителя.** `:710-728` внутри блокировки заново проверяет ключ и заказы через `_existing_create_for_orders`; при попадании коммитит и уходит в `_resume_from_orders_operation`, не выполняет `add-orders` по своей пустой заявке. Тест-параметризация `same_key`/`rotated_key`/`loser_failed` в `test_fbs_create_http_connection.py:38-42` держит именно эту инвариант через ассерты `add_calls.count("WB-GI-winner") == 1` и `"WB-GI-main" not in add_calls`.
- **Ротация ключа не ломает победителя.** `_existing_create_for_orders` в `:530-568` фильтрует SQL по `(state != CONFIRMED OR request_hash == request_hash)` и в Python возвращает победителя по совпадению `request_hash`, иначе — валит `operation_in_progress`. Отдельно проверяется семантика на разных наборах заказов (ветка `else`).
- **Отказ до победителя не оставляет локального следа.** В ветках `transport`, `invalid`, `rejected`, `owner_cancelled` тест ассертит отсутствие любых `FbsWbOperation` и `FbsSupply` кроме disjoint-`other`, и что тот же браузерный ключ снова годен (`retry` → `WB-GI-retry`). Это соответствует поведению кода: исключение из `create_marketplace_supply` в `:681-688` уходит вверх до коммита операции, транзакции ещё нет.
- **Ремонт не подтверждает по неполному составу WB.** `_close_pending_operation_if_complete` (`:1533-1552`) читает `request_summary_json.order_ids`, тянет `FbsOrder.wb_order_id` по этим UUID и подтверждает только когда `set(expected).issubset(wb_order_ids)` при полной длине. Тест внутри `add` фазы гоняет `[]` и `[27200]` — оба оставляют `pending_confirmation`.
- **Фронт не тронут по существу.** `FbsSupplyCreateDialog.tsx:73-78` пересоздаёт ключ только при смене `deliveryType` (I6-комментарий на месте), к идентичности создания это отношения не имеет и в правку не входило.

## Введённые дефекты

**P2 — косметика: `error_code = "wb_timeout"` на счастливом пути.** `mark_operation_pending_confirmation` в `fbs_supply_reconcile_service.py:424-440` имеет дефолт `error_code="wb_timeout"`, а вызов в `fbs_supply_service.py:817-819` его не переопределяет. В окне между коммитом победителя и `mark_operation_confirmed` строка операции лежит с `error_code="wb_timeout"`, хотя таймаута ещё не было. На функцию не влияет (окончательный `mark_operation_confirmed` сбрасывает в `None`, повторные попытки идут через `_resume_from_orders_operation`), но внешние наблюдатели/дэшборды в это окно видят ложный таймаут. При аварии до add-orders операция навсегда останется с этим ярлыком.

**P2 — оборонительный зазор в ремонте.** Если `request_summary_json.order_ids` окажется пустым (пустой список), проверка в `:1551` `len(expected) != len(requested_ids)` даст `0 != 0 = False`, `set().issubset(...) = True`, и операция подтвердится безусловно. На бою `create_supply_from_orders:585-587` не даёт создать операцию без заказов, но защита ремонта тут держится только на верхнем контракте.

## Что осталось как baseline (не проверял на регресс)

- Пустые черновики WB после гонки или потерянного ответа — явно приняты в разделе «Практическое ограничение» отчёта; внешнего вызова на удаление таких черновиков в правке нет и не должно быть.
- Параллельный вызов add-orders победителем и `_resume_from_orders_operation` проигравшего до перехода победителя в CONFIRMED — вытекает из решения не держать блокировку через HTTP; смягчено идемпотентностью WB PATCH-эндпоинта.
- Отчёт корректно оговаривает, что SIGKILL руками не проверялся, а полный `pytest` локально не крутился.

## Итог

По объёму review — блокеров нет. P0/P1 не обнаружено. Два P2 — маркер `error_code` на счастливом пути и оборонительная дыра пустого `order_ids` в `_close_pending_operation_if_complete` — по желанию владельца, оба некритичны для инварианта «нет постоянного блока заказов».