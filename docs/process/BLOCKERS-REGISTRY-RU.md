# Реестр блокировок Pipeline и backlog WMS

Дата среза: 21.08.2026.

Документ фиксирует препятствия, которые сейчас не дают безопасно запускать задачи
автономно и не дают считать отдельные направления backlog готовыми к разработке,
приёмке или выпуску. Это реестр наблюдаемых блокеров, а не план исправлений:
продуктовый и технический код в рамках этого документа не меняется.

Источники среза: `docs/process/PIPELINE-RU.md`,
`docs/process/PIPELINE-HOLES-RU.md`, `docs/process/PIPELINE-READY-REPORT-RU.md`,
`docs/process/PIPELINE-DESIGN-RU.md`, `docs/process/PIPELINE-ADDITIONS-RU.md`,
`pipeline/pipeline.yml`, `docs/BACKLOG-2026-08-19-CHAT-RU.md`,
`docs/ACTUAL_BACKLOG_RU.md`, `docs/NEXT_TASKS_RU.md` и
`docs/BACKLOG_EPICS_RU.md`.

## Как читать запись

`Минимальный артефакт закрытия` означает проверяемый результат, после которого
блокер можно снять именно для указанной зоны. Само намерение, устный ответ,
зелёный тест на соседний слой или наличие незакоммиченного кода блокер не снимают.

Машинная версия реестра лежит в `docs/product/blocks.json`. CI сверяет её с
этим Markdown через `scripts/ci/check_blockers_registry.py`: набор `BLK-*`
должен совпадать один-к-одному, а каждая запись обязана иметь `status`,
`affected_task_ids`, `evidence`, `last_verified_at`, `resume_stage` и
`supersedes`.

## Блокеры автономного запуска pipeline

### BLK-PIPE-001 — Pipeline v2 активирован как единый канон

- **Статус:** закрыт 21.08.2026 прямым решением владельца; `pipeline/pipeline.yml` имеет `status: ACTIVE`.
- **Тип:** pipeline / owner approval / release.
- **Где закрыт:** `docs/process/PIPELINE-RU.md`, `pipeline/pipeline.yml`, activation manifest и обновлённые entrypoint'ы.
- **Что изменилось для бизнеса:** все новые задачи идут по одному controller flow; старый Product gate больше не является параллельным маршрутом.
- **Кто закрывает:** владелец процесса; control-plane Reviewer и release owner подтверждают комплектность.
- **Resume stage:** activation gate, не карточка разработки.
- **Минимальный артефакт закрытия:** hash-linked activation manifest с commit SHA, owner activation line с датой, машинным переводом `pipeline/pipeline.yml` в `ACTIVE`, сохранёнными E-1…E-7 артефактами, E8 matrix по task profiles/traits, validator proof для controller/CI/deploy и аудитом старых process entrypoint'ов. Зелёные MT01…MT40 сами по себе этот блокер не снимают.

### BLK-PIPE-002 — Нет distributed host и внешнего durable store для wave-driver

- **Статус относительно ACTIVE:** не блокирует управляемый локальный controller; блокирует обещание полностью автономного распределённого запуска.
- **Тип:** architecture / environment / integration.
- **Где обнаружен:** `docs/process/PIPELINE-HOLES-RU.md`, раздел «Controller появился...»; `docs/process/PIPELINE-READY-REPORT-RU.md`, раздел «Что не готово для автономной ночной работы».
- **Почему блокирует бизнес:** dry-run уже детерминированно планирует отдельные worktree, порты, базы, очереди и эмуляторы, но локальная машина не может надёжно применить этот план для распределённой ночной волны. Без controller-owned внешнего durable store restart на другом host не восстановит authority state и leases.
- **Кто закрывает:** Architect согласует distributed host и store; Dev реализует исполнительный слой; Reviewer проверяет изоляцию и recovery.
- **Минимальный артефакт закрытия:** рабочий wave-driver с выдачей изолированного окружения, lease/fencing, возвратом состояния после сбоя и интеграционный receipt на конфликтующие ресурсы.

### BLK-PIPE-003 — Receipt доверяет локальной hash-подписи

- **Статус относительно ACTIVE:** не блокирует управляемый controller; остаётся ограничением независимой trust boundary.
- **Тип:** architecture / security / control plane.
- **Где обнаружен:** `docs/process/PIPELINE-HOLES-RU.md`, раздел «Схемы подключены...»; `docs/process/PIPELINE-RU.md`, разделы 7–8.
- **Почему блокирует бизнес:** worker потенциально не отделён от источника вердикта. Нельзя надёжно доказать, что receipt не был создан или изменён тем же исполнителем, который получил результат своей работы.
- **Кто закрывает:** Architect; Dev и Reviewer.
- **Минимальный артефакт закрытия:** независимая подпись receipt ключом, недоступным worker, единая проверка подписи в controller, CI и deploy, плюс негативный тест подмены receipt.

### BLK-PIPE-004 — Не весь тестовый контур закрыт от внешних marketplace-вызовов

- **Статус относительно ACTIVE:** штатный CI закрыт guard'ом; ad-hoc и browser network sandbox остаются отдельным ограничением и не разрешают live marketplace-вызовы.
- **Тип:** integration / test / security.
- **Где обнаружен:** `docs/process/PIPELINE-HOLES-RU.md`, раздел «Fail-closed test egress...».
- **Почему блокирует бизнес:** обход штатного runner или browser-level sandbox может обратиться в живой WB/Ozon. Это создаёт риск реальных изменений, утечки тестовых данных и неповторяемого результата.
- **Кто закрывает:** Architect и Dev; Reviewer проверяет все штатные entrypoint'ы.
- **Минимальный артефакт закрытия:** инвентаризация всех test entrypoint'ов и доказательство deny-by-default на уровне процесса или сети, включая браузер, с негативным тестом внешнего соединения.

### BLK-PIPE-005 — Не доказан durable recovery вне локального controller

- **Статус относительно ACTIVE:** локальный replay активен; внешний multi-host recovery остаётся ограничением распределённой автономности.
- **Тип:** architecture / integration / release.
- **Где обнаружен:** `docs/process/PIPELINE-HOLES-RU.md`, раздел «Crash/restart lane»; `docs/process/PIPELINE-RU.md`, разделы 7 и 8.
- **Почему блокирует бизнес:** controller-level ledger и replay MT40 уже проверяют локальный контракт, но ночной автономный запуск требует доказать restart на durable state и provider-specific crash proof. Иначе после падения между внешним эффектом и записью состояния можно повторить операцию, миграцию, комментарий или deploy.
- **Кто закрывает:** controller Architect; Dev интеграций; Reviewer.
- **Минимальный артефакт закрытия:** restart proof на durable store, replay receipt для каждого внешнего адаптера и deploy-пути, сценарий сбоя между эффектом и записью состояния, доказательство отсутствия двойного эффекта.

### BLK-PIPE-006 — Нет автономной promotion/rollback-доставки

- **Статус относительно ACTIVE:** offline exact-SHA delivery остаётся единственным разрешённым transport; production release всё равно требует отдельного owner authorization.
- **Тип:** release / integration / access.
- **Где обнаружен:** `docs/process/PIPELINE-HOLES-RU.md`, раздел «Offline build-once artifact promotion...».
- **Почему блокирует бизнес:** offline exact-SHA artifact уже fail-closed и защищает от server-side build. Блокер остаётся не потому, что обязательно нужен OCI registry, а потому что автономная доставка, права доступа, promotion между контурами и rollback ещё не оформлены end-to-end.
- **Кто закрывает:** Architect и DevOps/Dev; Reviewer.
- **Минимальный артефакт закрытия:** проверенный promotion/rollback receipt независимо от транспорта: artifact/digest manifest, exact SHA, delivery proof, rollback proof и отдельное владелецкое решение по доступам/секретам.

### BLK-PIPE-007 — Старые process entrypoint'ы переведены в adapters

- **Статус:** закрыт 21.08.2026; обязательные entrypoint'ы указывают на Pipeline v2, а старые документы сокращены до pointers.
- **Тип:** process / product / architecture.
- **Где закрыт:** `AGENTS.md`, `CLAUDE.md`, PR template, `.dev/PROCESS.md`, Cursor skill и legacy process docs.
- **Результат:** Codex, Claude и Cursor получают один machine-backed маршрут S01–S28 и не могут выбрать старую цепочку как альтернативу.
- **Кто закрывает:** pipeline BA/Architect; Reviewer проверяет inventory всех entrypoint'ов.
- **Минимальный артефакт закрытия:** карта старых entrypoint'ов к Pipeline v2, архивирование или короткие adapters без конкурирующих правил и receipt аудита отсутствия второго канона.

### BLK-PIPE-008 — Очередь задач остановлена на `WAITING`

- **Тип:** product / owner input.
- **Где обнаружен:** `docs/process/PIPELINE-READY-REPORT-RU.md`, разделы «Итог» и «Блокеры до запуска фиксов багов».
- **Почему блокирует бизнес:** `resume` снимает только owner hold и разрешает ранние стадии S01/S02/BA. Это не равно допуску к разработке. Автоматический старт фикса может начаться только после отдельного Product receipt.
- **Кто закрывает:** владелец задачи для снятия `WAITING`; Product отдельно закрывает допуск в Dev.
- **Resume stage:** S01/S02 после owner `resume`; S18 только после BLK-PROD-003.
- **Минимальный артефакт закрытия:** owner approval на конкретную карточку и controller receipt `resume`. `TASK_INTAKE_READY`, `IMPACT_CLASSIFIED` и role binding появляются уже после снятия hold.

### BLK-COST-001 — Нет бюджета и hard stop по моделям

- **Тип:** cost / model policy / control plane.
- **Статус:** narrowed; static policy closed, runtime accounting remains open.
- **Где обнаружен:** `pipeline/budget-policy.yml` и `scripts/ci/check_pipeline_budget_policy.py` задают и проверяют лимиты, warning, hard stop, usage receipt, recovery packet и owner override; runtime usage accounting ещё не подключён.
- **Почему блокирует бизнес:** статический контракт теперь запрещает считать бюджет закрытым без runtime receipts и durable aggregation. До их появления ночная волна всё ещё не имеет доказанной фактической остановки по измеренному расходу.
- **Кто закрывает:** владелец процесса совместно с pipeline Architect/FinOps.
- **Resume stage:** S01/S02 для обычной подготовки допустимы; автономная волна и массовый запуск дорогих stages ждут бюджет.
- **Закрытая часть:** policy, schema, CI-check и metatest покрывают бюджет wave/card/stage tier, warning threshold, hard stop, recovery packet и owner override marker.
- **Оставшийся минимальный артефакт:** usage receipt по executor/model/stage, durable aggregation по wave/card, runtime dispatch gate с hard stop и доказательство восстановления после остановки.

## Блокеры разработки по backlog

### BLK-PROD-001 — Для спорного поведения Честного знака нет зафиксированного оракула

- **Тип:** product / integration / research.
- **Где обнаружен:** `docs/process/PIPELINE-READY-REPORT-RU.md`, блокеры до запуска фиксов; `docs/BACKLOG-2026-08-19-CHAT-RU.md`, D3 и разделы I/H.
- **Почему блокирует бизнес:** нельзя безопасно определить, является ли `sgtinApplied` достаточным условием dispatch и нужно ли отправлять КИЗ, когда WB сообщает `requiredMeta: []`. Ошибка затрагивает обязательства продавца, передачу кодов и риск регуляторных последствий.
- **Кто закрывает:** Product при участии BA и Research; правовую/регуляторную часть подтверждает Compliance/Legal либо явно назначенный owner; Architect фиксирует границу интеграции.
- **Минимальный артефакт закрытия:** утверждённый oracle/decision record с правовым и WB-контрактом, состояниями успеха/ошибки и правилом для `requiredMeta`/`optionalMeta`.

### BLK-PROD-002 — Часть backlog описана как дефект, но не имеет полного контракта результата

- **Тип:** product / BA.
- **Где обнаружен:** `docs/BACKLOG-2026-08-19-CHAT-RU.md` (D1, D2, D23); `docs/ACTUAL_BACKLOG_RU.md` (частично реализованные inbound/outbound, акты и отгрузка на МП).
- **Почему блокирует бизнес:** симптом известен, но без точного целевого процесса нельзя отличить исправление от изменения политики. Например, для 155 заказов и для отказа сдачи нужно заранее определить допустимое поведение, состав сообщения оператору и сохранение складского инварианта.
- **Кто закрывает:** BA и Product.
- **Минимальный артефакт закрытия:** атомарная feature card с Given/When/Then, ролями, данными, негативными случаями, границами задачи и критерием видимого бизнес-результата.

### BLK-PROD-003 — У карточек нет Product receipt на допуск к Dev

- **Тип:** product / per-card approval.
- **Где обнаружен:** `docs/process/PIPELINE-READY-REPORT-RU.md`, раздел «Как начать только после разрешения»; текущие bug cards заведены как `WAITING`.
- **Почему блокирует бизнес:** снятие `WAITING` разрешает разбор и подготовку, но не даёт агенту права писать фикс. Без `PRODUCT_APPROVED_FOR_DEV` разработчик может начать менять код по непроверенной карточке и закрепить неверный процесс.
- **Кто закрывает:** Product.
- **Resume stage:** S16 → S18.
- **Минимальный артефакт закрытия:** утверждённая card hash, S08/S12/S15 package и controller receipt `PRODUCT_APPROVED_FOR_DEV` на конкретный task/card.

### BLK-BACKLOG-001 — Versioned backlog-очередь есть, owner-approved wave ещё нет

- **Тип:** backlog / product / planning.
- **Статус:** сужен; очередь создана, но owner-approved wave ещё не выдана.
- **Где обнаружен:** `docs/BACKLOG-2026-08-19-CHAT-RU.md` прямо фиксирует, что есть два списка, которые нужно свести и приоритизировать; свежие входящие 21.08 добавлены в тот же backlog.
- **Что закрыто этим артефактом:** `docs/product/backlog-queue.json` даёт stable IDs, источники, типы, статусы, readiness, зависимости, приоритеты и suggested roles/stages; `scripts/ci/check_backlog_queue.py` проверяет обязательные поля, уникальность IDs и ссылки зависимостей.
- **Что остаётся блокером:** очередь не является разрешением на разработку. Для конкретной волны нужны owner approval, Product receipt и обычные гейты pipeline; items с `needs_product_*`, `needs_architecture_*` или `waiting_*` нельзя отправлять прямо в Dev.
- **Кто закрывает остаток:** BA/Product и pool Architect; владелец утверждает конкретную wave.
- **Resume stage:** S01/S02 для очереди; S12 для нарезки карточек.
- **Минимальный артефакт полного закрытия:** owner-approved wave с receipt, привязанная к версии очереди и commit SHA.

### BLK-ARCH-001 — Не закрыта архитектурная граница для data guard и исправления данных

- **Тип:** architecture / data.
- **Где обнаружен:** `docs/process/PIPELINE-DESIGN-RU.md`, раздел 9.3; `docs/ACTUAL_BACKLOG_RU.md`, разделы про изоляцию и неполные инварианты.
- **Почему блокирует бизнес:** дубли складов, штрихкодов и карточек в разных tenant'ах не ловятся обычным конвейером кода. Без владельца источника истины и безопасной политики remediation ночной процесс может только обнаружить проблему, но не понять, какие данные допустимо менять.
- **Кто закрывает:** Architect совместно с Product и BA.
- **Минимальный артефакт закрытия:** схема data guard с правилами, severity, owner каждой находки, read-only отчётом и отдельным безопасным процессом исправления/подтверждения.

### BLK-ARCH-002 — Для крупных операций не закреплён безопасный concurrency-контракт

- **Тип:** architecture / integration / test.
- **Где обнаружен:** `docs/BACKLOG-2026-08-19-CHAT-RU.md`, D14: deadlock при создании поставки из 155 заказов и одновременном автоопросе.
- **Почему блокирует бизнес:** массовая операция может не завершиться, хотя данные откатываются целиком; складской оператор вынужден повторять действие вручную. При росте пачки вероятность отказа увеличивается, поэтому малый happy path не доказывает работоспособность процесса.
- **Кто закрывает:** Architect и Dev; Reviewer проверяет транзакционный контракт.
- **Минимальный артефакт закрытия:** согласованная модель блокировок/порядка захвата, retry/timeout policy, нагрузочный case на размере не менее 155 заказов и доказательство отсутствия двойного эффекта.

### BLK-RESEARCH-001 — Внешние контракты WB/ЧЗ не собраны по полям и статусам

- **Тип:** research / integration.
- **Где обнаружен:** `docs/process/PIPELINE-ADDITIONS-RU.md`, Д1–Д2; `docs/BACKLOG_EPICS_RU.md`, E4 и E6.
- **Почему блокирует бизнес:** предположенный формат уже приводил к непринятым кодам ЧЗ, потере полей схемой ответа и неверной трактовке пагинации WB. Без источника, версии, формата поля и критерия успеха нельзя строить надёжный импорт, печать или dispatch.
- **Кто закрывает:** Research и BA; Product утверждает результат; Architect проверяет границы адаптера.
- **Минимальный артефакт закрытия:** versioned external-contract dossier: поля, статусы, pagination, ошибки, источник достоверности и безопасный emulator/sandbox proof.

### BLK-TEST-001 — Полный pytest-прогон не является работающим гейтом

- **Тип:** test / environment.
- **Где обнаружен:** `docs/BACKLOG-2026-08-19-CHAT-RU.md`, D22; обязательные команды в `AGENTS.md`/`CLAUDE.md`.
- **Почему блокирует бизнес:** полный обязательный прогон зависает, а `pytest-timeout` не подключён. Команда вынуждена ограничиваться точечными тестами и может выпустить регрессию в соседнем слое, считая технический gate пройденным.
- **Кто закрывает:** Test Infrastructure и Reviewer.
- **Last verified:** требуется свежий exact-SHA replay; текущая запись основана на наблюдении backlog от 20.08.
- **Минимальный артефакт закрытия:** изолированный зависающий test ID, exact SHA, команда, лог, закрытая внешняя зависимость, заданный timeout и успешный полный прогон с сохранённым логом и понятной причиной возможного skip.

### BLK-TEST-002 — Per-card S22/S23 proof отсутствует до запуска карточки

- **Тип:** test / integration.
- **Где обнаружен:** `docs/ACTUAL_BACKLOG_RU.md` (статусы «Частично»), `docs/NEXT_TASKS_RU.md` (P3), `docs/process/PIPELINE-RU.md`, стадии S15/S22/S23.
- **Почему блокирует бизнес:** HTTP 200 или тест сервисного слоя не доказывает, что оператор увидел правильный экран, данные записались в правильный tenant и внешний эффект состоялся. Особенно рискованны маркировка, остатки, отгрузка и фоновые задачи.
- **Кто закрывает:** Test Automation и Reviewer; Browser QA подтверждает пользовательский путь, если он есть.
- **Resume stage:** S22/S23 конкретной карточки, не глобальный запрет на BA/архитектуру.
- **Минимальный артефакт закрытия:** traceability matrix с TC-ID, Given/When/Then, негативами, exact task ID/SHA, runnable references и доказательством пользовательского результата через API, БД/worker и UI там, где это применимо.

### BLK-BROWSER-001 — Per-card S25 Product Browser receipt отсутствует до реализации

- **Тип:** browser / product acceptance.
- **Где обнаружен:** `docs/process/PIPELINE-READY-REPORT-RU.md` (обязательные Product gate и Browser review); `docs/process/PIPELINE-RU.md`, стадии S25 и S28.
- **Почему блокирует бизнес:** Playwright, curl и скриншот не подтверждают, что реальный оператор в нужной роли прошёл путь, увидел ошибку/пустоту/успех и получил правильную версию данных. Без этого нельзя закрыть карточку или выпускать изменение операторского потока.
- **Кто закрывает:** Browser QA/Product Browser QA.
- **Resume stage:** S25/S28 конкретной карточки, не глобальный запрет на ранние стадии.
- **Минимальный артефакт закрытия:** receipt с exact SHA/URL, ролью, реальными кликами/вводом/сканированием, состояниями success/error/empty/reload-readback, скриншотами и вердиктом `PRODUCT_BROWSER_APPROVED`/`FINAL_ACCEPTANCE_APPROVED` либо именованным blocker.

### BLK-DESIGN-001 — Старые экраны ещё не переведены на UI-kit

- **Тип:** design / frontend foundation.
- **Где обнаружен:** `docs/process/PIPELINE-DESIGN-RU.md`, раздел 8.1: зафиксированы 56 файлов с отступлениями, 283 свои кнопки и 53 свои таблицы; на 21.08 базовые формы/меню/модалка/каркас добавлены в `ui-kit`, но существующие экраны автоматически не переписаны.
- **Почему блокирует бизнес:** старые экраны продолжают жить на разной локальной вёрстке. Это не блокирует запуск pipeline целиком, но блокирует обещание “вся система уже строго через ui-kit” и массовые дизайн-операции вроде “перекрасить все кнопки”.
- **Кто закрывает:** Architect/Design; Dev реализует компоненты; Reviewer и Browser QA проверяют применение.
- **Resume stage:** per-screen migration card.
- **Минимальный артефакт закрытия:** план переезда по экранам, codemod/ручные карточки для старого долга, `ui_guard.py` показывает убывающую базовую линию, а migrated screen имеет browser receipt.

### BLK-DESIGN-002 — UI-kit enforcement ещё без zone baseline

- **Тип:** design / guard / frontend foundation.
- **Где обнаружен:** `scripts/ui/ui_kit_usage_guard.py`, `scripts/ui/ui_guard.py`, `docs/process/PIPELINE-RU.md` stage S22/S24.
- **Почему блокирует бизнес:** базовый W12 guard уже запрещает новые экранные файлы без `ui-kit` и новый raw MUI/inline-style в экранных diff, но ещё не доказывает визуально, что каждая новая зона совпала с утверждённой zone baseline. Поэтому он защищает от нового обхода набора, но не заменяет Design Implementation Review.
- **Кто закрывает:** UI Platform/Guard и Browser QA.
- **Resume stage:** S22/S24.
- **Минимальный артефакт закрытия:** committed guard SHA, негативные метатесты для raw MUI при существующем `ui-kit` import и новых screen/shared files, zone baseline, `invariants.js` evidence и browser visual receipt.

### BLK-DATA-001 — В рабочих данных есть неподтверждённые расхождения и сироты

- **Тип:** data / product / integration.
- **Где обнаружен:** `docs/process/PIPELINE-DESIGN-RU.md`, П7 и раздел 9.3; `docs/BACKLOG-2026-08-19-CHAT-RU.md`, D5, D7; `docs/ACTUAL_BACKLOG_RU.md`, разделы про tenant isolation и частичные инварианты.
- **Почему блокирует бизнес:** дубли штрихкодов, 208 кодов без привязки из 209 и пустой `last_wb_sync_at` могут привести к неверному выбору товара, несвоевременной отмене заказа или расхождению остатков. Нельзя считать интеграционный backlog закрытым, пока источник и допустимое состояние данных не подтверждены.
- **Кто закрывает:** BA и Product определяют допустимое состояние; Architect и Dev готовят read-only проверку; Reviewer.
- **Минимальный артефакт закрытия:** обезличенный data snapshot, отчёт нарушений с уникальными ключами записей, решением по каждой категории и подтверждением tenant/складских инвариантов.

### BLK-INTEGRATION-001 — Импорт WB ограничен и не поддерживает автономную актуализацию каталога

- **Тип:** integration / product / research.
- **Где обнаружен:** `docs/BACKLOG-2026-08-19-CHAT-RU.md`, D19–D21; `docs/NEXT_TASKS_RU.md`, P2; `docs/BACKLOG_EPICS_RU.md`, E4.
- **Почему блокирует бизнес:** импорт каталога останавливался после первых 100 карточек, фоновой синхронизации нет, а текущий picker грузит весь каталог вместо серверного поиска. Новый товар может не появиться в WMS, а операторский выбор становится медленным и непредсказуемым.
- **Кто закрывает:** Product/BA формируют контракт пагинации и поиска; Architect и Dev интеграции; Reviewer.
- **Минимальный артефакт закрытия:** контракт пагинации WB с доказанным stop condition, idempotent background sync, server-side search contract, измерение полного каталога и e2e на товаре за пределами первой страницы.

### BLK-INTEGRATION-002 — Печать 58×40 и драйвер не исследованы до разработки

- **Тип:** research / design / integration.
- **Где обнаружен:** `docs/BACKLOG_EPICS_RU.md`, E6; `docs/NEXT_TASKS_RU.md`, P2 и E6.
- **Почему блокирует бизнес:** без выбора способа печати, состава этикетки и подтверждённого устройства нельзя обещать оператору физический результат. UI-кнопка без printer evidence не означает, что маркировка или адрес попадут на правильный носитель.
- **Кто закрывает:** Research и Product; Architect согласует интеграционную границу; Browser QA/Reviewer.
- **Минимальный артефакт закрытия:** printer dossier с форматом 58×40, полями, способом печати (браузер/ESC/POS), повторной печатью, ошибками и подтверждением на разрешённом устройстве.

### BLK-PROCESS-001 — Машинный `blocks.json` есть, runtime rules binding ещё не полный

- **Тип:** process / machine registry.
- **Статус:** сужен; `docs/product/blocks.json` и CI guard введены, runtime binding ещё не останавливает закрытие карточек по всем blocker IDs.
- **Где обнаружен:** `docs/product/blocks.json` и `scripts/ci/check_blockers_registry.py` зеркалят текущий реестр, но controller пока не требует снять конкретный blocker ID перед каждым `close`.
- **Почему блокирует бизнес:** агент уже получает машинный список блокеров, owner и resume stage, но автономный pipeline ещё должен научиться не закрывать карточку, если связанный `BLK-*` открыт или не имеет closure evidence.
- **Кто закрывает:** pipeline Architect и Guard.
- **Resume stage:** S08/S15/S22 в зависимости от правила.
- **Закрытая часть:** machine registry и CI-храповик, который сверяет его с Markdown-реестром.
- **Оставшийся минимальный артефакт:** controller/rules binding: `close`, `resume` и `advance` учитывают открытые blocker IDs, closure evidence и негативный metatest на попытку закрыть карточку при открытом блокере.

### BLK-RELEASE-001 — Cache-control/D12 не включён в browser/release proof

- **Тип:** release / browser evidence.
- **Где обнаружен:** `docs/BACKLOG-2026-08-19-CHAT-RU.md`, D12; `docs/process/PIPELINE-RU.md`, stages S23/S25/S28.
- **Почему блокирует бизнес:** если браузер видит старый asset после выката, Product Browser может принять не тот код или отклонить уже исправленный. Это ломает связь “exact SHA → то, что видит оператор”.
- **Кто закрывает:** release engineer и Browser QA.
- **Resume stage:** S23/S25/S28.
- **Минимальный артефакт закрытия:** browser/release receipt с exact SHA, asset URL/hash, cache headers, hard reload proof и подтверждением, что экран открыт из нового artifact.

### BLK-ARCH-003 — Ozon и аналитический модуль требуют dossier/ARCH до разработки

- **Тип:** architecture / product / research.
- **Где обнаружен:** `docs/BACKLOG-2026-08-19-CHAT-RU.md`, задачи про Ozon и K2 «аналитическая отчётность для селлера и фулфилмента».
- **Почему блокирует бизнес:** Ozon вводит новый внешний контракт, а аналитика вводит новый продуктовый контур для двух ролей. Если начать с кода, можно закрепить не те метрики, не тот источник данных, неверную свежесть и права доступа.
- **Кто закрывает:** Research, Product и Architect.
- **Resume stage:** S03/S05/S07/S13 до S12/S18.
- **Минимальный артефакт закрытия:** research dossier, role needs, data-source/freshness/access contract, architecture decision, first-version boundary и Product approval до разработки.

## Граница этого реестра

Записи выше не являются разрешением запускать исправления, менять backlog,
вызывать WB/Ozon, работать с секретами или менять frontend/backend. До снятия
соответствующего блокера допустимы только чтение источников и подготовка
документальных receipts в рамках разрешённой задачи.
