# REVIEW · 01-wb-marking

Вердикт: CHANGES_REQUESTED.

ВЕРДИКТ: НАХОДКИ 7

## Находки

1. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py:161` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py:66` — решение WB `required` отображается в `accepted`, а тест закрепляет это как норму. Если WB вернёт `required` с непустым, например отражённым старым, значением, специальная ветка `required` без значения не сработает, `_apply_meta_detail_to_marking` поставит `accepted`, а `compute_delivery_allowed` разрешит сдачу. По принятому решению проходят только `filled` и `optional`; цена — ложное зелёное состояние и отказ WB уже при сдаче поставки.

2. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py:548` — совместимое поле `check_status` по-прежнему берётся из устаревшего `row.meta.checkStatus` и вообще не выводится из `metaDetails.decision`. При нормальном ответе нового метода только с `metaDetails` решение `invalid` переведёт `meta_status` в `rejected`, но оставит прежний `check_status=ok`; существующий API и чип проверки покажут «Проверен» одновременно с требованием исправить код. Цена — противоречащие друг другу статусы для оператора и нарушение заявленной обратной совместимости поля.

3. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_autopoll_service.py:267` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py:600` — пропущенный в частичном ответе `order_id` превращается в пустой `meta_batch`, после чего сервис всё равно пересчитывает `meta_details_json` и `metadata_delivery_allowed`, отправляет обновление поставки и увеличивает счётчик `synced`. Если WB вернул 99 строк из запрошенных 100, сотый заказ будет учтён как успешно синхронизированный без единого подтверждённого поля. Цена — ложный успех мониторинга и изменение допуска к сдаче по старым локальным данным, хотя контракт требует полностью сохранить состояние пропущенного заказа.

4. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py:505` — идемпотентность `wb_orphaned` реализована небезопасной парой «сначала SELECT, затем INSERT» без блокировки строки и без уникального ограничения. Два параллельных ручных запуска синхронизации оба могут увидеть отсутствие события и записать по событию каждый. Цена — дубли в аудите именно в обязательном ломающем кейсе параллельного запуска вместо одного факта расхождения.

5. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py:532` — локальные привязки читаются до сетевого ожидания WB и затем применяются без `FOR UPDATE` и без повторного чтения актуальной привязки. Если оператор успеет закрепить новый КИЗ, пока старый batch-запрос находится в сети, ответ к старому снимку перезапишет агрегат заказа и `metadata_delivery_allowed`. Цена — разрешение или блокировка сдачи по уже неактуальному коду; это прямо нарушает контракт гонки с ручной записью.

6. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py:652` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py:148` — значение внешнего `Retry-After` используется без верхней границы, а тест явно одобряет ожидание 1,5 секунды вместо короткого ограниченного повтора. Если WB или прокси пришлёт `Retry-After: 3600`, задача удержит обработку продавца на час, не перейдёт к следующим пачкам и задержит остальные статусы. Цена — остановка фоновой обработки одного продавца на произвольное время, заданное внешним ответом.

7. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py:126` — тест `wb_orphaned` сам вставляет `MarkingCodeEvent` в БД и потому не проверяет ни вызов сверки WB, ни переход `missing`/`replacement_required`, ни однократность, ни сохранность кода именно внутри новой сервисной логики. Он останется зелёным, если `_record_wb_orphaned_once` перестанет вызываться или начнёт дублировать события. Цена — обязательный аудит-факт не защищён тестом поведения, хотя зелёный набор создаёт обратное впечатление.

## Проверено и нормально

- Весь diff от базового коммита `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking` проверен; продуктовые изменения ограничены ровно восемью разрешёнными backend-файлами, остальные изменения являются стадийными артефактами и не считались выходом за границы.
- Автоматического освобождения КИЗ, сброса `marking_code_id`, перевода в `available`/`void`, записи в WB и изменений фронтенда в diff нет; обязательная граница `ARCH-CROSS.md` соблюдена.
- Устаревшее одиночное чтение `fetch_marketplace_order_meta` удалено; актуальный batch POST остаётся единственным путём чтения метаданных.
- Точечный `ruff` прошёл. Целевые файлы `test_wildberries_marketplace_fbs_client.py`, `test_marking_code_events.py`, `test_fbs_kiz.py` прошли: 73 теста. Зелёный результат не покрывает находки выше.
