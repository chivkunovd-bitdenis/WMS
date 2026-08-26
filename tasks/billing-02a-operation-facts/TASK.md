# Волна 2А: надёжные факты операций

## 0. Как работать и открыть наряд

Работа выполняется одним исполнителем в одном контексте и только в worktree
`/Users/deniscivkunov/Projects/WMS/.worktrees/billing-module-20260826`, ветка
`codex/billing-module-20260826`. База волны — `e957b2d6c508cb2e2ac080ed9421e99d40bbe9df`,
а этот пакет обязан пройти независимое ревью исполнимости **до** открытия наряда и первой
правки продуктового кода.

После принятого ревью открыть ровно такой наряд:

```bash
python3 scripts/naryad.py new "Волна 2А модуля «Расчёты»: надёжные факты операций без нового экрана" --lane обычная --files backend/app/models/operation_fact.py,backend/app/models/__init__.py,backend/app/models/inbound_intake.py,backend/app/models/fbs_order.py,backend/app/models/fbs_order_pick.py,backend/app/models/marketplace_unload.py,backend/app/services/operation_fact_service.py,backend/app/services/operation_fact_recovery_service.py,backend/app/services/inbound_intake_service.py,backend/app/services/fbs_picking_service.py,backend/app/services/fbs_supply_service.py,backend/app/services/packaging_task_service.py,backend/app/services/marketplace_unload_service.py,backend/app/services/storage_statement_service.py,docs/backend-guard-baseline.json
```

`backend/alembic/versions/20260826_0110_operation_facts.py` и новые тесты
`backend/tests/test_operation_facts.py`, `backend/tests/test_operation_fact_recovery.py` входят в
границы волны, хотя хук наряда охраняет только `backend/app`. Хук, его конфигурацию, baseline
сторожей и файлы `frontend/src` менять запрещено. Исключение возможно только после доказанной
технической необходимости: если минимальная writer-интеграция неизбежно добавляет строки в уже
большой source-сервис и только поэтому краснеет `back_guard`, разрешён один отдельный
baseline-коммит. Он меняет только заранее названные записи реально затронутых writer-интеграцией
файлов: `inbound_intake_service.py`, `fbs_picking_service.py`, `fbs_supply_service.py`,
`packaging_task_service.py`, `marketplace_unload_service.py`, — и только
`docs/backend-guard-baseline.json`. Для каждой изменённой записи до commit обязательны отдельная
доказанная причина и построчная сверка «было → стало» в evidence. Массовый `--update`, любые
другие baseline entries и смешение baseline с продуктовым commit запрещены. Если наряд не открыт,
статус только `BLOCKED`; обходить защиту нельзя.

Не запускать `wms_lead`, `scripts/sol_pipeline.py`, оркестраторы, модераторов или агентов,
управляющих агентами. Не писать `ARCH.md`, классификаторы, глобальный реестр экранов, дельта-матрицы
или аудит WMS. Нужные будущие волны не начинать. После двух технически разных безрезультатных
попыток — `BLOCKED` с точной причиной.

## 1. Цель и бизнес-результат

Создать надёжный неизменяемый слой фактов оказанных складских операций. Он отвечает на вопрос,
какая услуга и чьё действие действительно состоялись, не подменяя физическое количество расчётной
единицей. Волна даёт будущим отчётам селлеров и сотрудников один восстанавливаемый источник,
устойчивый к повтору запросов и отменам, но ещё не создаёт деньги, тарифы, экран или новый публичный
API.

## 2. Дословные требования владельца из `TASK.FINAL.md`

> «До отчётов вводится надёжный, идемпотентный и восстанавливаемый факт оказанной операции».

> «Физическое количество `item_quantity` не перезаписывается расчётной единицей».

> «Факт должен иметь процедуру сверки и восстановления по каноническим документам и существующим
> журналам. Пропавшее событие не должно навсегда исчезать из расчётов».

> «История до ввода `OperationFact` не исчезает и не реконструируется предположениями».

> «На дате отсечения старый ledger и новый `OperationFact` не теряют и не задваивают один факт».

Также обязательна каноническая 2А-нарезка: приёмка, возврат, подбор FBS, упаковка, отгрузка,
хранение, отмены и сторно; реальные FBS-события, включая отмену и повторное выполнение.

## 3. Что уже существует и обязательно переиспользуется

- `DocumentEvent` — append-only best-effort аудит статусов и данных документов. Его сбой не должен
  откатывать складскую операцию; он **не** становится источником `OperationFact`.
- `FbsOrderPickEvent` (`picked`, `undone`), `PackagingTaskEvent` (упаковка, отмена, выполнение) и
  фактические `FbsOrderProductPick` для Ozon — источники доказательства подбора и его отмены.
- `InboundIntakeRequest`, `MarketplaceUnloadRequest`, `FbsSupply`, `PackagingTask`,
  `StorageStatement`/`StorageMeasurement` — канонические документы и строки; их действующие
  статусы, остатки и процессы не переписываются.
- `BillingLedgerEntry`, его `uq_billing_ledger_source_event`, существующие тарифы, счета и
  `staff_packaging_billing_service` сохраняются. Упаковка сотрудников продолжает оплачиваться
  только существующим сервисом: эта волна не создаёт `StaffEarningEntry` и не начисляет зарплату.
- Единственный текущий Alembic head перед реализацией: `20260825_0109`.

## 4. Нормативные и запрещённые входы

Главные источники: данный `TASK.md`, `BACKGROUND.md`, `CASES.md`, `BILLING-SCREEN.md`,
`tasks/billing-module-20260825/TASK.FINAL.md`, `AGENTS.md`, `CLAUDE.md`,
`docs/process/KANON_ZADACHI_RU.md`, `docs/product/NARYAD_RU.md` и
`docs/product/UX_CANON_RU.md`. Фактические константы и сервисы из раздела 3 уточняют только
реальные точки записи; исторический `TASK.RECOVERED-REV2.md` — справочный и не отменяет FINAL.

Запрещены: повтор волны 1/второй `DocumentEvent`; чтение фактов одновременно из `DocumentEvent` и
нового журнала; пересчёт, удаление или задняя правка legacy ledger; ослабление
`uq_billing_ledger_source_event`; изменение существующих счетов, тарифов, хранения, упаковочной
оплаты, FBS-процесса, RBAC, маршрутов, внешних API, экранов и фронтенда; production/deploy и
доступ к кабинетам или секретам.

## 5. Модели, API, состояния и сценарии

### Данные и сервис

Добавить `OperationFact`, `OperationFactLine` и один системный singleton cutover (дата-время
включения новой половины read-model). У факта обязательны: `id`, `tenant_id`, `operation_code`,
nullable `billable_service_code`, `source_kind`, `source_event_id`, `idempotency_key`, `seller_id`,
`seller_name_snapshot`, nullable `warehouse_id`/`marketplace`, `document_type`, `document_id`,
`document_number_snapshot`, nullable `actor_user_id`/`actor_name_snapshot`, `source` (`system` или
`user`), `occurred_at`, физическое `item_quantity`, nullable `reversal_of_id` и
`integrity_status`. Строка хранит факт, товар, SKU/название-снимки и физическое количество.

Уникальность `(tenant_id, idempotency_key)` для непустого ключа, уникальность канонического
`(tenant_id, source_kind, source_event_id, operation_code)`, запрет кросс-тенантных связей в
сервисе, отдельные индексы для seller- и employee-отчётов и стабильный порядок восстановления
обязательны. Миграция строго добавляющая и продолжает единственный head.

Чтобы recovery не выдумывал автора, миграция также добавляет nullable durable author fields только
в канонические источники, где их сейчас нет: terminal `completed_by_user_id` у
`InboundIntakeRequest`; `completed_by_user_id` и `cancelled_by_user_id` у
`MarketplaceUnloadRequest`; `picked_by_user_id` и `undone_by_user_id` у
`FbsOrderProductPick`. Сервисы заполняют их в том же commit, что и реальное действие.
Исторические source rows до миграции лежат до cutover и не backfill-ятся: recovery не создаёт по
ним fact с выдуманным автором или source. `FbsOrderPickEvent` и `PackagingTaskEvent` уже хранят
нужного автора и новых полей не требуют.

Таксономия фиксируется константами и тестами: завершённая приёмка и возврат; `fbs_pick` и его
отмена/сторно; фактическая упаковка и её undo; завершённая отгрузка и её отмена; зафиксированное
хранение; system/user. Повтор после отмены создаёт новый факт с новым источником, а не изменяет
старый. `DocumentEvent` не читается и не записывается как часть этого контура.

### Исчерпывающая матрица реальных источников 2А

| Реальное событие или переход в текущем коде | `operation_code` | `source_kind` / `source_event_id` | Количество и lines | Момент записи | Автор и source | Сторно, отмена, повтор |
|---|---|---|---|---|---|---|
| `InboundIntakeRequest` достигает `STATUS_DONE` через `receive_line`, `post_all_remaining` или `complete_distribution`; `operation_type=inbound` | `inbound_completed` | `inbound_intake_request` / `req.id` | `sum(line.posted_qty)`; по одной line на `InboundIntakeLine` с `posted_qty>0` | после `_maybe_complete_request`, до существующего `session.commit()` | новый durable `req.completed_by_user_id` из `performer_id`; user при непустом ID, иначе system | В текущем коде DONE не переоткрывается; `reopen_receiving` доступен только из sorting и не сторнирует ещё не созданный terminal fact. Повтор terminal-вызова после DONE ошибки/возвращает существующее состояние, writer идемпотентен по `req.id`. |
| То же terminal-переход, но `operation_type=return` | `return_completed` | `inbound_intake_request` / `req.id` | те же фактические `posted_qty` и lines | тот же commit | тот же durable `completed_by_user_id` / user-or-system | Та же фактическая граница; возврат не маскируется кодом приёмки. |
| WB-ветка `fbs_picking_service.scan_pick_product` либо `_auto_pass_picking_if_needed`: создан `FbsOrderPick` и `FbsOrderPickEvent(event_type=picked)` | `fbs_pick` | `fbs_order_pick_event` / ID события `picked` после flush | 1 штука и line из связанного `FbsOrderPick.product_id` | после flush `FbsOrderPickEvent`, до возврата workspace/commit вызывающего запроса | `FbsOrderPickEvent.actor_user_id`; user при непустом ID, иначе system для auto-pass | Повторный scan/auto key не создаёт новый pick/event/fact. |
| WB-ветка `undo_pick`: создан `FbsOrderPickEvent(event_type=undone)` | `fbs_pick_reversal` | `fbs_order_pick_event` / ID события `undone` после flush | 1 штука и та же product line | после flush undo-event, до возврата workspace | `FbsOrderPickEvent.actor_user_id` / user | `reversal_of_id` указывает на fact `picked` связанного pick. Повтор undo-key возвращает существующее состояние; новый pick после undo создаёт новый event и новый `fbs_pick`. |
| Ozon-ветка `scan_pick_product`: создан `FbsOrderProductPick` | `fbs_pick` | `fbs_order_product_pick` / `FbsOrderProductPick.id` после flush | 1 штука и line из `order_product_id` | после flush нового position-pick, до возврата workspace | новый durable `FbsOrderProductPick.picked_by_user_id=actor.id` / user | Повтор `scan_idempotency_key` не создаёт второй source/fact. |
| Ozon-ветка `undo_pick`: у того же `FbsOrderProductPick` установлены `undone_at`, `undo_idempotency_key`, `undone_by_user_id` | `fbs_pick_reversal` | `fbs_order_product_pick` / тот же ID; operation code отличает reversal от pick | 1 штука и line того же order product | после flush изменения undo-полей, до возврата workspace | новый durable `undone_by_user_id=actor.id` / user | `reversal_of_id` указывает на исходный fact; повтор undo-key не дублирует. Новый pick после отмены — новая row `FbsOrderProductPick`, следовательно новый fact. |
| `record_pack_progress`/`mark_line_prepacked_external` добавляет `PackagingTaskEvent` с `manual_pack`, `scan_pack` или `prepacked_external` и положительным quantity | `packing_completed` | `packaging_task_event` / `PackagingTaskEvent.id` после `_add_task_event` flush | event quantity и ровно одна line из `event.line_id`/`event.product_id` | сразу после `_add_task_event`, до commit этого сервисного вызова | `created_by_user_id`; user при непустом ID, иначе system | Каждое новое action-event — новый факт; label-print и `complete` не создают второй факт, потому что не несут нового построчного physical work. |
| `undo_last_pack_action` помечает исходный pack-event `reversed_at` и добавляет `PackagingTaskEvent(action=undo_last)` | `packing_reversal` | `packaging_task_event` / ID нового `undo_last` event | quantity и line исходного reversible event | после flush нового undo-event, до commit | `reversed_by_user_id` исходного event (если задан), иначе `created_by_user_id` нового; без ID system | `reversal_of_id` на fact отменённого pack-event. Повтор невозможен, потому что исходный event уже `reversed_at`; следующий pack создаёт новый event/fact. |
| `cancel_task` создаёт `PackagingTaskEvent(action=cancel, quantity=0)`; `complete_task` создаёт `complete` без product line; `confirm_line_packed_from_shelf` не создаёт task event | не создаётся | не создаётся | не создаётся | не создаётся | не создаётся | Эти текущие записи не содержат доказанного нового item-level work или однозначного обратного quantity. Их запрещено превращать в фиктивный факт/сторно; отмена уже выполненной упаковки покрывается только явным `undo_last_pack_action`. |
| `complete_unload` переводит `MarketplaceUnloadRequest` в `STATUS_SHIPPED` | `marketplace_outbound_completed` | `marketplace_unload_request` / `req.id` | `sum(distributed_qty_by_product(req).values())`; lines только по фактически distributed product quantities | после `req.status=STATUS_SHIPPED` и до commit, рядом с существующим `record_operational_charge` | новый durable `req.completed_by_user_id=performer_id`; user при непустом ID, иначе system | Повтор невозможен вне `EXECUTION_STATUSES`; fact по `req.id` идемпотентен. |
| `cancel_request` для shipped request вызывает существующий `record_operational_reversal` и сохраняет `STATUS_SHIPPED` | `marketplace_outbound_reversal` | `marketplace_unload_request` / `req.id`, code отличает reversal | исходные distributed lines и quantity исходного outbound fact, не пересчёт плана | в той же транзакции рядом с существующим reversal, до commit | при первом cancel установить `req.cancelled_by_user_id=performer_id` только если поле пусто; user при непустом ID, иначе system | `reversal_of_id` на outbound fact. Повторный cancel идёт из всё ещё `STATUS_SHIPPED`: writer/recovery по тому же source tuple возвращает тот же reversal-fact, а `cancelled_by_user_id` не перезаписывается. Cancel до shipment факта не создаёт reversal. Текущий код не имеет повторной отгрузки этого же cancelled request. |
| `fix_storage_statement` фиксирует `StorageStatement`; каждая существующая `StorageMeasurement` получает публикацию | `storage_fixed` | `storage_measurement` / `measurement.id`; при нулевом statement — `storage_statement` / `statement.id` | `StorageMeasurement` содержит только `quantity_days`/`liter_days`, не фактические штуки: в 2А `item_quantity=0` и lines нет, чтобы не выдать литро-дни за штуки | после проверки draft/calculated и до единственного commit, одновременно с фиксацией statement, но не из `BillingLedgerEntry` | в текущей сигнатуре нет actor; system | Fixed statement идемпотентно возвращается без нового source/fact. В текущем коде нет операции отмены fixed storage statement, поэтому 2А не выдумывает storage reversal. |

Ни одна строка матрицы не использует `DocumentEvent` или `BillingLedgerEntry` как source. В частности,
`FbsSupply` status и `DocumentEvent` trigger не заменяют реальный pick/undo source; для автоматического
подбора, где `fbs_supply_service` создаёт тот же `FbsOrderPickEvent`, применяется WB-строка таблицы.

Запись факта находится в той же транзакционной единице работы, что и подтверждённое каноническое
действие. Для старых потерянных записей отдельный recovery-service сверяет только канонические
документы и указанные специализированные журналы, создаёт лишь отсутствующие факты через те же
ключи и возвращает счётчики `found/created/already_present/conflicted`; он не исправляет историю
догадкой и не дублирует строки.

### Экран и API

Экран: не затрагивается — см. `BILLING-SCREEN.md`. API: не затрагивается; эта волна не добавляет
роут, не меняет `/api/billing/ledger` и не раскрывает финансовые данные. Внутренний recovery-service
покрывается тестами и пока не публикуется HTTP/CLI-командой. Следовательно OpenAPI не меняется;
проверка отсутствия незаявленного нового route обязательна через `back_guard`.

### Сценарии

Положительные, негативные, регрессионные, PostgreSQL- и будущие браузерные границы перечислены в
`CASES.md`; их тесты пишутся до продуктового кода. Никакого browser-сценария в 2А нет, потому что
видимого поведения не меняется.

## 6. Границы файлов, зависимости и порядок работы

1. После независимого review открыть наряд и зафиксировать Alembic head.
2. Написать тесты из `CASES.md`, затем добавить модели, их регистрацию и одну миграцию.
3. Реализовать единый writer/recovery-service и подключить **только** перечисленные сервисные точки
   фактического завершения/отмены. Не расширять изменения на соседние процессы.
4. Проверить FBS WB и Ozon: подбор → отмена → повторный подбор даёт три отдельных устойчивых
   факта без дубля при повторе того же idempotency key.
5. Выполнить миграционные и тестовые гейты, независимое ревью, доказательство PostgreSQL и
   сохранить evidence. Затем отдельный commit и push.

Разрешённые продуктовые файлы названы в команде наряда; список повторно сверён с матрицей: три
модели автора (`inbound_intake.py`, `fbs_order.py`, `marketplace_unload.py`) нужны для
восстановимости, а пять сервисов-источников и storage service — для точек записи. Единственная
миграция и два новых test-файла названы в разделе 0. `storage_statement_service.py` создаёт лишь
факт за уже зафиксированное хранение и не меняет месячный расчёт или `BillingLedgerEntry`.

### Amendment — fidelity SQLite-тестов WB redo

`backend/app/models/fbs_order_pick.py` добавлен в границы только для того, чтобы SQLite metadata
в тестовом контуре повторяла уже существующий PostgreSQL partial unique index
`uq_fbs_order_picks_active_order` (`undone_at IS NULL`). Без этого WB `pick → undo → redo`
некорректно блокируется глобальным unique index в SQLite. Production schema и FBS-поведение этим
amendment не расширяются и не меняются; CASES уже содержит требуемый redo-сценарий.

## 7. Что остаётся неизменным

Не создаются экран `/app/ff/billing`, вкладки, модалки, таблицы, маршруты, новый API или frontend.
Не меняются «Остатки и движения», «Хранение», существующий экран/legacy API расчётов, счета,
операции склада, состояния FBS, `DocumentEvent`, существующие специализированные журналы и
упаковочная зарплата. Факт не является денежным начислением: ни ставка, ни сумма, ни tariff-version
в 2А не создаются. Старые ledger-строки остаются историей до cutover, новые факты не
реконструируют прошлое. Baseline/guard не меняются, кроме одного отдельного случая из §0: один
commit может обновить только реально затронутые записи пяти заранее названных source-сервисов и не
разрешает массовую нормализацию или смешение с продуктовым commit.

## 8. Тесты, машинные гейты, PostgreSQL и живой браузер

До кода — тесты из `CASES.md`. Минимум: ORM/constraints, tenant isolation, идемпотентность,
точность lines/снимков, source user/system, reversal/re-execution, Ozon и WB FBS, recovery без
дублей, cutover без пропуска/дублирования, регрессии приёмки/возврата/подбора/упаковки/отгрузки/
хранения, и отсутствие изменения `staff_packaging_billing_service` поведения.

Обязательные команды с фактическими exit code:

```bash
(cd backend && uv run ruff check .)
(cd backend && uv run mypy .)
(cd backend && uv run pytest tests/test_operation_facts.py tests/test_operation_fact_recovery.py)
(cd backend && uv run pytest)
python3 scripts/ci/back_guard.py
python3 scripts/ci/check_migrations.py
```

Отдельно на PostgreSQL: upgrade с `20260825_0109` до новой ревизии, `alembic heads` ровно один,
inspection всех индексов/unique constraints/FK и сценарий параллельного/повторного recovery. SQLite
этого не заменяет. Фронтенд не меняется, поэтому tsc/unit/build/Playwright/ui_guard и живой браузер
неприменимы; это фиксируется, а не заменяется фиктивным скриншотом. В evidence сохранить команды,
exit codes, миграционный proof, выборку фактов и независимый review:
`docs/evidence/billing-02a-operation-facts/OPERATION-FACTS-PROOF.md`.

Если сработало единственное исключение §0, добавить туда отдельный подраздел
`BACK_GUARD_BASELINE.md`: для **каждой** изменённой записи одного из пяти названных source-сервисов
— конкретную причину, почему вынести минимальный writer-вызов невозможно, строку
`docs/backend-guard-baseline.json` «было → стало» и SHA отдельного baseline commit. Доказать, что
других baseline-файлов/записей не менялось. `back_guard.py --update` не запускать.

До закрытия реализации обязательны: независимое содержательное ревью диффа и отдельный независимый
прогон существующего регресса. Красный тест, в том числе унаследованный, закрытие запрещает.

## 9. Отчёт, доказательства, commit и push

Отчёт писать по событиям и формату:

```text
Полоса: обычная
Экран: отсутствует — backend/data, BILLING-SCREEN.md
Стадия: <номер и название>
Статус: <результат>
Base SHA: <SHA>
Commit: <SHA или нет>
Доказательства: <путь или нет>
Раунд правок: 0 | 1 | 2
Блокеры: <список или нет>
```

Перед словом «готово в ветке»: `git status`, ограниченный diff, отдельный commit только этой волны,
проверенный SHA и `git push origin codex/billing-module-20260826`. Модуль и волна не объявляются
готовыми без реализации, всех гейтов, review, evidence и последующего merge; production не трогать.
