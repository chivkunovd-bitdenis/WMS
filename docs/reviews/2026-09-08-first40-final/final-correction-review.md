# Проверка последних исправлений печати, PDF и контрактов CI

Проверены только новые коммиты и непосредственно затронутые зависимости:

- `22d1bfd73e2bf6111615737d2f31f5a85ba03bdd` поверх `e1ff9705f045675b80fd063ec33d7d298031166e`, checkout `.worktrees/backlog40-review-print-fix`;
- `5b6b9f4d4f3a86501f7df765966faa331000db66`, checkout `.worktrees/backlog40-ci-pdf`;
- `5ce71fb969d9696d17f4457ca7a7f61f23dad461`, checkout `.worktrees/backlog40-ci-contracts`.

Проверка read-only; записан только этот отчёт. Pytest, тестовые PostgreSQL-сценарии и браузер я не запускал. Заявленные исполнителями проверки не считаются моим наблюдением. Root ранее проверил форму экрана и первую/повторную печать общего `7702678b`, но это не браузерная проверка новой транзакционной реализации `22d1bfd7`.

**Итог: исходные F1/F2 исправлены в проверенных WB-путях. PDF и обновление контрактов дополнительных исправлений по результатам этой проверки не требуют. В новом print-коммите остаются два конкретных дефекта.**

## C1 — P2: второй неопределённый ответ для уже сверенной привязки падает на UNIQUE

В [tape:434–445](/Users/deniscivkunov/Projects/WMS/.worktrees/backlog40-review-print-fix/backend/app/services/fbs_order_tape_print_service.py:434) поиск учитывает только `pending_confirmation`. Для подтверждённой операции возвращается `None`, и повторная печать той же привязки снова вызывает PUT. При новом transport/5xx [строки 462–466](/Users/deniscivkunov/Projects/WMS/.worktrees/backlog40-review-print-fix/backend/app/services/fbs_order_tape_print_service.py:462) передают неизменный `idempotency_key=f"tape:{marking.id}"`.

В [record_pending_kiz_operation:701–712](/Users/deniscivkunov/Projects/WMS/.worktrees/backlog40-review-print-fix/backend/app/services/fbs_marking_service.py:701) каждый вызов безусловно создаёт новую строку с hash того же ключа, order.id и marking.id. Существующая [уникальность seller/kind/idempotency_key](/Users/deniscivkunov/Projects/WMS/.worktrees/backlog40-review-print-fix/backend/app/models/fbs_wb_operation.py:36) сохраняется и для confirmed-строк.

Цепочка: первая печать получает неопределённый ответ → pending сохраняется; повтор GET подтверждает эту операцию; оператор снова печатает тот же КИЗ; новая ошибка PUT/GET пытается вставить тот же уникальный ключ → `IntegrityError` при коммите tape на 409. Ошибка не перехватывается веткой `FbsMarkingError`, и новый pending не сохраняется. Первоначальный код остаётся занятым благодаря первому коммиту, но штатный повтор печати заканчивается ошибкой базы. Существующий тест [uncertain → recovery:252–267](/Users/deniscivkunov/Projects/WMS/.worktrees/backlog40-review-print-fix/backend/tests/test_fbs_tape_background_concurrency.py:252) проверяет только первую сверку и не делает следующую попытку.

**Минимальное исправление:** не создавать второй раз операцию с тем же ключом. Использовать существующую запись этой привязки/попытки согласованно с её состоянием; для подтверждённой неизменившейся привязки повтору печати не нужен повтор PUT. Если повторный PUT всё же необходим, его последующий неопределённый результат должен сохраняться без нарушения существующей уникальности. Новая таблица, состояние или запрет печати не нужны.

**Одна точная проверка:** продолжить существующий тест после confirmed ещё одной печатью/reprint и вторым неопределённым ответом. Нужны отсутствие IntegrityError, один занятый код/одна привязка и рабочий GET-only повтор для действительно неопределённой операции.

## C2 — P1: вынесенный из блокировки Ozon GET применяется к сменившемуся КИЗ

В [sync_order_marking_statuses:1025–1048](/Users/deniscivkunov/Projects/WMS/.worktrees/backlog40-review-print-fix/backend/app/services/fbs_marking_service.py:1025) Ozon GET теперь выполняется до захвата parent/order. После сети код перечитывает текущие markings и применяет к ним прежний `result`, не сравнивая набор привязок до и после запроса. Это отличается от новой WB-защиты на 745–749/784–786.

Конкурентная [замена Ozon-КИЗ](/Users/deniscivkunov/Projects/WMS/.worktrees/backlog40-review-print-fix/backend/app/services/ozon_kiz_service.py:208) создаёт новую marking (208–220), получает её собственный статус (222–230) и удаляет старую активную привязку (233–234). Прежний ответ `/v5/fbs/posting/product/exemplar/status` относится к состоянию отправления до замены; [read_marking_status:540–554](/Users/deniscivkunov/Projects/WMS/.worktrees/backlog40-review-print-fix/backend/app/services/ozon_fbs_process_service.py:540) возвращает общий status без CIS. [apply_status:133–157](/Users/deniscivkunov/Projects/WMS/.worktrees/backlog40-review-print-fix/backend/app/services/ozon_fbs_marking_gate_service.py:133) затем копирует этот общий status в текущие markings.

Поэтому старый `validation_in_process`/`ship_not_available` может затереть уже полученный accepted нового кода; обратный случай — старый `ship_available` делает новую pending-привязку принятой без ответа по ней. Перечитывание строк само по себе не связывает старый сетевой результат с новой привязкой. Этот риск появился при переносе Ozon GET перед ранее удерживаемыми блокировками.

**Минимальное исправление:** до Ozon GET сохранить в локальной переменной идентификаторы текущих markings, после parent/order-lock сравнить их с перечитанным набором. При изменении не применять старый status и вернуть актуальные записи, как уже сделано для WB. Не возвращать долгие упаковочные блокировки через HTTP и не добавлять поля/сущности.

**Одна точная проверка:** задержать старый ответ Ozon GET, завершить смену КИЗ с новым результатом, отпустить старый ответ; новая marking и её фактический статус должны сохраниться. Два направления status — старый accepted против нового pending и старый pending против нового accepted — проверяют обе ошибочные смены.

## Что подтверждено без новых замечаний

**WB-блокировки:** `sync_order_statuses` теперь получает все страницы статусов до захвата строк, затем вызывает общий batch helper и перечитывает orders в UUID-порядке ([wb_marketplace_orders_service:973–1000](/Users/deniscivkunov/Projects/WMS/.worktrees/backlog40-review-print-fix/backend/app/services/wb_marketplace_orders_service.py:973)). Родители блокируются до заказов, поэтому уже разобранная цепочка фоновой отмены order → supply устранена. В metadata-autopoll HTTP всех batch предшествует применению, порядок UUID общий; основной entrypoint коммитит статусную и metadata-фазы отдельно ([autopoll:370–413,473–475](/Users/deniscivkunov/Projects/WMS/.worktrees/backlog40-review-print-fix/backend/app/services/fbs_autopoll_service.py:370)). Позднее WB-уведомление не захватывает supply.

**QR и первый коммит:** QR запрашивается до упаковочных блокировок; его изменения коммитятся до mixed QR+CZ, а QR-only вызывает `_load_supply(for_update=False)` ([tape:114–156](/Users/deniscivkunov/Projects/WMS/.worktrees/backlog40-review-print-fix/backend/app/services/fbs_order_tape_print_service.py:114)). Выделенные КИЗ и привязки сохраняются вместе на 381 до сетевой отправки. Во время отправки удерживается только текущий order; перед PUT проверяются актуальный marking.id и отмена заказа (384–398), после каждой попытки — commit409. Уведомление supply подавлено; Ozon promotion вызывается после отпускания order. Складские движения и резервы в этом изменении не добавлены.

**Обработанная неопределённость WB:** transport/5xx и ошибка чтения после PUT сохраняют существующую привязку и код, создают pending, а следующий запрос при pending выполняет GET. C1 касается последующей повторной попытки уже после confirmed, а не первого recovery. Для WB GET новый набор marking IDs после HTTP оставляет актуальные записи без наложения старого ответа ([marking:784–786](/Users/deniscivkunov/Projects/WMS/.worktrees/backlog40-review-print-fix/backend/app/services/fbs_marking_service.py:784)); рассматриваемые скан/отвязка действительно заменяют/удаляют marking IDs.

**PDF:** [локальная переменная samples:37–40](/Users/deniscivkunov/Projects/WMS/.worktrees/backlog40-ci-pdf/backend/app/services/marking_datamatrix_service.py:37) удерживает копию пиксельного буфера до завершения native decode. Mutex, новые потоки, формат страницы и декодирование значения не меняются. Тест с weakref проверяет владение буфером перед вызовом native reader для RGB и grayscale. [usefixtures db_session](/Users/deniscivkunov/Projects/WMS/.worktrees/backlog40-ci-pdf/backend/tests/test_marking_cis_restore.py:20) подключает уже существующую инициализацию тестовой схемы для самостоятельного запуска CIS restore-тестов; production apply не запускался и не добавлялся.

**Контракты CI:** изменены тесты и статический OpenAPI-снимок, production-роуты и дизайн этим коммитом не меняются. Ozon-тест различает сохранённый физический источник и штатный `forced_negative` на сортировке при отсутствии источника; это соответствует [планировщику:357–377](/Users/deniscivkunov/Projects/WMS/.worktrees/backlog40-ci-contracts/backend/app/services/fbs_shipment_source_service.py:357) и сохраняет проверку общего -1/одного внешнего handoff. Mock каталога принимает уже существующие cursor-аргументы и дополнительно проверяет завершение job. Ledger/CSV-тест проверяет внешний КИЗ без пула и изоляцию tenant. OpenAPI-снимок прочитан как JSON, отсутствующих локальных schema refs не найдено; это проверка структуры артефакта, не запуск сервера/CI.

Два оставшихся изменения C1/C2 затрагивают один marking-сервис; их следует передать одному исполнителю печати. PDF и test/contracts можно интегрировать независимо. Новых операторских блокировок, складских действий упаковки, восстановления истории или изменений дизайна для исправления C1/C2 не требуется.
