# Фича 1

# Backend dev · 05-prod-slow · атом 1

## Изменённые файлы

- Нет: продуктовый backend-код и тесты не изменялись.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md` — этот отчёт.

## Гейты

- ruff: FAIL, 79 существующих нарушений вне атома; файлы атома не менялись.
- mypy: FAIL, 21 существующая ошибка в 6 несвязанных файлах; файлы атома не менялись.
- pytest: целевой `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_wb_marketplace_orders_service.py` — PASS, 12 passed. Полный запуск собрал 830 тестов, но его итог в доступном выводе не был получен; поэтому полный gate не подтверждён.
- back_guard.py: не запускался — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/scripts/ci/back_guard.py` отсутствует в рабочей копии.
- check_migrations.py: не запускался — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/scripts/ci/check_migrations.py` отсутствует в рабочей копии.

## Не реализовано

- Атом 1 не реализован. В обязательном входном файле `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/CONTRACT.md` отсутствует раздел «API и данные», поэтому backend-dev не может менять поведение `new`/`reconcile` или трактовать ошибку повторного `next_token` из ревью как утверждённый API-контракт.
- Релевантная находка ревью №3 зафиксирована: полная сверка не защищена от повторяющегося `next_token`; её исправление требует явного серверного контракта для результата и ошибки обхода.
- Отдельный Git-коммит не создан: Git отказал в создании `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock` с `Operation not permitted`. Артефакт остаётся незакоммиченным в рабочей копии.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

# Фича 2

# Backend dev · 05-prod-slow · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/wb_marketplace_orders_service.py` — часовая сверка WB прекращает обход с retryable-ошибкой `cursor_cycle`, если WB повторяет ранее выданный `next_token`; дублирующая страница не записывается и привязка поставок не выполняется.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_wb_marketplace_orders_service.py` — проверки раздельного запуска Celery-задач `new`/`reconcile`, single-flight по `(seller_id, sync_kind)`, отсутствия seller-wide lock в job-пути и повторного курсора.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md` — этот отчёт.

## Гейты

- ruff: адресно PASS (`ruff check app/services/wb_marketplace_orders_service.py tests/test_wb_marketplace_orders_service.py`); полный `ruff check .` FAIL — 79 существующих нарушений вне атома.
- mypy: полный `mypy .` FAIL — 21 существующая ошибка в 6 несвязанных файлах; адресный запуск также получает 4 ошибки из импортируемых несвязанных сервисов, изменённые файлы ошибок не добавили.
- pytest: адресно PASS — `tests/test_wb_marketplace_orders_service.py`, 15 passed. Полный `pytest -q` дважды прервался средой после 5–6 тестов без итогового статуса; лог `/private/tmp/volna-9-05-prod-slow-pytest.log` содержит только точки, поэтому полный результат не заявляется.
- back_guard.py: не запущен — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/scripts/ci/back_guard.py` отсутствует в рабочей копии.
- check_migrations.py: не запущен — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/scripts/ci/check_migrations.py` отсутствует в рабочей копии.
- Миграции: нет.

## Не реализовано

- Backend-находки ревью №3 и все проверки атома 2 устранены. Фронтенд-находки №1, №4–10 относятся к другим разрешённым файлам и не менялись в роли backend-dev.
- Git-коммит не создан: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock` (`Operation not permitted`), поэтому изменения сохранены только в рабочем дереве.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

# Фича 3

# Backend dev · 05-prod-slow · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/background_job_service.py` — повторная публикация активного `marking_label_tape` и восстановление только устаревшего `running`-job после 15-минутной аренды; захват остаётся single-flight на уровне БД.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/api/marking_codes.py` — повторный идентичный запрос публикует тот же активный job, не создавая дубликат.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/alembic/versions/20260822_0050_marking_label_tape_jobs.py` — отформатирована существующая добавляющая миграция: `idempotency_key`, частичный уникальный индекс активного job и `expires_at` для print asset.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_background_jobs.py` — сценарии повторной публикации без второго job, запрета захвата свежего `running` и восстановления устаревшего `running`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md` — отчёт backend-dev.

## Гейты

- `ruff check .` — не пройден: 79 уже существующих ошибок вне изменённого атома. Адресный `ruff check` всех файлов атома — пройден.
- `mypy .` — не пройден: 21 уже существующая ошибка в шести чужих файлах. Адресный запуск также видит старые ошибки зависимостей и тестовых фикстур; новых диагностик в изменённом сервисе и API нет.
- `pytest tests/test_background_jobs.py tests/test_fbs_print_assets.py` — пройдено: 16 passed.
- `pytest` — полный набор не завершился в изолированной среде запуска до выдачи результата; адресные наборы атома прошли: 16 passed.
- `python3 scripts/ci/back_guard.py` — не запущен: файла нет в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — не запущен: файла нет в этой рабочей копии.
- `git diff --check` — пройден.

## Не реализовано

- Фронтенд-находки ревью №1, №4–10 не относятся к серверному атому 3 и его файлам; они не изменялись.
- Серверная находка ревью №2 исправлена: повтор активного запроса повторно ставит в очередь тот же job, а stale `running` можно безопасно перехватить; свежий `running` не перехватывается.
- Секреты, ключи, токены, `.env`, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

# Фича 4

# Backend dev · 05-prod-slow · атом 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/api/marking_codes.py` — публикация существующего `marking_label_tape` job в очередь `print` стала best-effort: отказ брокера не меняет ответ `202`, а durable `pending` job повторно публикуется тем же идемпотентным запросом.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_background_jobs.py` — регрессия отказа публикации в брокер: API-обвязка не выбрасывает ошибку и активное задание остаётся пригодным для повторной публикации.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md` — отчёт backend-dev.

## Что реализовано

- `POST /operations/marking-codes/label-artifact-tape` — после сохранения job возвращает `202` даже при временном отказе Celery-брокера; повтор того же запроса использует тот же активный job, без дубликата.
- `background_job_service` — действующее восстановление stale `running` job после 15-минутной аренды и single-flight захват job сохранены; worker создаёт один `label_tape` asset, ошибки переводят job в `failed`.

## Миграции

- Нет новых миграций. Используется существующая добавляющая `20260822_0050_marking_label_tape_jobs.py` с идемпотентным ключом, частичным уникальным индексом активного job и сроком хранения asset.

## Гейты

- `ruff check .` — FAIL: 79 существующих нарушений вне атома; адресный `ruff check` файлов атома — PASS.
- `mypy .` — FAIL: 21 существующая ошибка в 6 несвязанных файлах; адресный запуск слоя очереди видит 4 ошибки из зависимостей вне атома, новых ошибок в изменённых файлах нет.
- `pytest tests/test_background_jobs.py tests/test_marking_pdf_label_artifact.py tests/test_fbs_print_assets.py` — PASS, 34 passed; покрыты `202`, тот же active job, один PDF asset, ошибка worker и истечение asset.
- `pytest` — FAIL вне атома: после 161 passed и 3 skipped остановлен на 11 падениях в `tests/test_fbs_orders_intake.py`, связанных с WB-статусами и поставками; сценарии ленты ЧЗ не затронуты и адресный набор из 34 тестов зелёный.
- `python3 scripts/ci/back_guard.py` — не запущен: файла нет в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — не запущен: файла нет в этой рабочей копии.
- `git diff --check` — PASS.

## Не реализовано

- Нагрузочный прогон на 155 и 500 кодов с одновременным `/health` не запускался: для него требуется выделенный стенд с Celery worker; production не затрагивался.
- Фронтенд-находки ревью №1, №4–10 не относятся к backend-слою этого атома и не изменялись.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

# Фича 5

# DEV · 05-prod-slow · TableLoadMore

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

Продуктовые файлы атома не изменялись: ревью не содержит замечаний к
`TableLoadMore`, а текущая реализация уже соответствует контракту. Проверены:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/TableLoadMore.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/UiKitShowcase.tsx`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (из `frontend/`) — зелёный.
- `python3 scripts/ui/ui_guard.py` (из корня) — красный из-за новых нарушений в
  чужих файлах: `MarkingPrintDialog.tsx`, `WbProductPickerDialog.tsx`,
  `FfFbsOrdersScreen.tsx`, `FfFbsSupplyWorkspace.tsx`,
  `SellerInboundDraftScreen.tsx`. Файлы атома в выводе отсутствуют; базовая
  линия не менялась.
- `npm run test:unit -- --run` (из `frontend/`) — не запущен: команда завершилась
  с `sh: vitest: command not found`; зависимости тестового раннера отсутствуют.

Проверены сценарии контракта: без следующего курсора элемент скрывается;
доступное состояние показывает единственное действие «Показать ещё»; при
загрузке показаны «Загружаем…» и спиннер, а повторный клик блокируется; при
ошибке `ErrorNotice` расположен над вновь доступным действием. Витрина ui-kit
демонстрирует скрытое, доступное, загружаемое и ошибочное состояния, а её
интерактивный пример считает вызовы и не допускает повторного запуска во время
загрузки.

## Не реализовано

Нет продуктовых пунктов, не реализованных буквально в пределах этого атома.
Зелёный `ui_guard.py` и unit-тесты не подтверждены из-за нарушений вне
разрешённых файлов и отсутствующего `vitest`; исправление чужих экранов,
изменение baseline или установка зависимостей не входят в атом.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой
кабинет Wildberries не читались и не затрагивались.

# Фича 6

# DEV · 05-prod-slow · S-03 pagination rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-fbs-orders.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/fbsApi.ts` не менялся: его запрос уже передаёт `limit` и `cursor` по контракту этого атома.

Фоновый 30-секундный тик теперь явно отделён от обычной загрузки: он заменяет только первую порцию, сохраняет реально догруженный хвост и удаляет устаревшие строки именно из первой порции. Смена селлера, склада или вкладки выполняет обычную замену списка и не смешивает выдачи. Устаревший ответ отменяется номером запроса. Пустое состояние остальных вкладок снова использует их общий текст, а не текст вкладки «Новые».

В E2E добавлены/уточнены сценарии `S-03-TC-001`–`S-03-TC-007` и `S-03-TC-010`–`S-03-TC-012`: 50 строк, догрузка, «Выбрать все» по курсорам, скелет, пустой ответ, фоновый тик, лимит 100 на рабочей вкладке, двойной клик, ошибка с повтором и скрытая вкладка.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend`) — зелёный.
- `npm run test:unit` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend`) — зелёный.
- `python3 scripts/ui/ui_guard.py` (из корня) — красный. Скрипт сообщает новые нарушения монолитности в `src/components/MarkingPrintDialog.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsOrdersScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Baseline через `--update` не менялась; три из пяти файлов не входят в разрешённую границу этого атома.
- `npm run test:e2e -- tests-e2e/ff-fbs-orders.spec.ts` — не запущен: в локальном `frontend/node_modules` нет `playwright`; npm вызвал постороннюю команду `playwright`, которая вернула `error: unknown command 'test'`.

## Не реализовано

- Браузерный прогон новых `S-03` сценариев не подтверждён из-за отсутствующего локального Playwright. Сами сценарии записаны в разрешённый E2E-файл.
- Зелёный `ui_guard.py` не получен: исправление остальных четырёх указанных скриптом файлов либо изменение baseline запрещены границей роли и атома.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

# Фича 7

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/components/MarkingPrintDialog.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/docs/blockers/S-03.md`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

Исправлен несуществующий setter состояния, добавлена защита от завершения старого polling после закрытия или смены контекста диалога, а истечение подготовленного PDF сохраняет отдельное операторское состояние. В журнал блокировок добавлено правило запрета повторной печати активной/готовой ленты.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный: сообщает о новых baseline-отклонениях в `src/components/MarkingPrintDialog.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsOrdersScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовую линию не обновлял.
- `npm run test:unit -- --runInBand` — красный: `vitest: command not found` в этой рабочей копии.
- `npm run test:e2e -- --grep "S-03-TC-008|S-03-TC-009|S-03-TC-014|S-03-TC-015"` — команда завершилась без совпавших тестов; в разрешённых спецификациях нет сценариев с этими TC-ID, поэтому перечисленные Playwright-пути не подтверждены.
- `git commit` — не выполнен: Git не разрешил создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock` (`Operation not permitted`). Изменения не сохранены коммитом.

## Не реализовано

- Находки ревью о backend-задачах и `FfFbsOrdersScreen.tsx` не исправлялись: они находятся вне файлов и слоя данного атома.
- В `frontend/tests-e2e/ff-marking-print-constructor.spec.ts` и `frontend/tests-e2e/ff-separate-marking-print.spec.ts` отсутствуют требуемые сценарии `S-03-TC-008`, `S-03-TC-009`, `S-03-TC-014`, `S-03-TC-015`; их нельзя выдать за пройденные без отдельной реализации тестов.
