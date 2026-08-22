# Фича 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Cells.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Actions.tsx` — проверен без изменений: `PrintAction what="счёт"` даёт подпись «Печать счёта».
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Cells.test.ts`

## Гейты

- `tsc --noEmit -p tsconfig.app.json`: не запущен — в checkout отсутствует `frontend/node_modules/.bin/tsc`.
- `python3 scripts/ui/ui_guard.py`: красный из-за пяти новых/изменённых вне этого атома нарушений (`src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`); файлы этого атома в выводе отсутствуют, базовую линию не обновлял.
- `npm run test:unit`: не запущен — отсутствует `frontend/node_modules/.bin/vitest`.

## Не реализовано

- Находки из `REVIEW.md`, относящиеся к backend и экранным файлам биллинга, не относятся к разрешённым файлам этого атома и не изменялись.
- `PrintAction` не требовал правки: для `what="счёт"` панель уже показывает «Печать счёта».

# Фича 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/PeriodPicker.tsx` — проверен контрактный переиспользуемый выбор месяца: controlled `YYYY-MM`, label «Месяц», границы `min`/`max`, ошибка, disabled и сохранение значения при загрузке родителя.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/index.ts` — проверен экспорт `PeriodPicker` и `PeriodPickerProps`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — отчёт screen-dev.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не выполнен: в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend` отсутствует `node_modules/.bin/tsc`; `npx --no-install` также не может использовать локальный компилятор.
- `python3 scripts/ui/ui_guard.py` — красный (`GUARD_STATUS=1`): обнаружены пять новых нарушений в чужих файлах (`src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`); `PeriodPicker.tsx` и `index.ts` в нарушениях отсутствуют, baseline не обновлялся.
- `npm run test:unit` — не выполнен: в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend` отсутствует `node_modules/.bin/vitest`.

## Не реализовано

- Находок из `REVIEW.md`, относящихся к `PeriodPicker.tsx` или `index.ts`, нет. Находки ревью по backend, экрану биллинга, настройкам и e2e-тестам не относятся к разрешённому слою этого атома и не изменялись.
- Исходный атом уже был в HEAD и буквально соответствует контракту, поэтому дополнительная правка исходников не потребовалась.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Фича 3

# 09-A backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/models/billing.py` — частичный уникальный индекс профиля ФФ теперь явно ограничен `seller_id IS NULL` и для SQLite.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_0094_billing_financial_core.py` — то же условие добавлено в DDL миграции.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_models.py` — тест проверяет частичный индекс в SQLite.

## Гейты

- `ruff check .` — FAIL: 83 существующие ошибки вне этого атома; изменённые модель и тест проходят ruff, миграция содержит ранее существовавшие нарушения форматирования.
- `mypy .` — FAIL: 21 существующая ошибка в 6 файлах вне этого атома.
- `pytest` — адресные billing-тесты PASS: `3 passed`; полный прогон не даёт отдельного результата из-за остановки обязательной цепочки на baseline-ruff.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в этой рабочей копии.

## Не реализовано

- Находки ревьюера по задачам Celery, API, сервисам, frontend и e2e не относятся к 09-A и намеренно не изменялись.
- Секреты, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Фича 4

# 09-billing · backend-dev

Исправлен backend-атом 4 по замечаниям ревьюера.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_configuration_service.py` — исправлена проверка контрольных цифр 12-значного ИНН; версии тарифа теперь конфликтуют на уровне услуги и селлера независимо от единицы расчёта.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_configuration_service.py` — регрессии для валидного/невалидного 12-значного ИНН и пересечения тарифов по разным единицам.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — этот отчёт.

## Гейты

- `ruff check .` из `backend/` — НЕ ПРОЙДЕН: 84 существующих нарушения в несвязанных FBS, marketplace и scripts-файлах; затронутые billing-файлы проходят адресный `ruff check`.
- `mypy .` из `backend/` — НЕ ПРОЙДЕН из-за общего запуска после ruff-блока; адресный `mypy` для `billing_configuration_service.py`, `billing.py` и `api/billing.py` — ПРОЙДЕН.
- `pytest` из `backend/` — ПРЕРВАН по тайм-ауту рабочего прохода после `223 passed, 3 skipped`; адресные billing-тесты — `4 passed`.
- `python3 scripts/ci/back_guard.py` — НЕ ПРОЙДЕН: файл отсутствует в checkout (`scripts/ci/back_guard.py` не найден).
- `python3 scripts/ci/check_migrations.py` — НЕ ПРОЙДЕН: файл отсутствует в checkout (`scripts/ci/check_migrations.py` не найден).

## Миграции

Нет. Частичный уникальный индекс профиля ФФ уже содержит `postgresql_where` и `sqlite_where` в существующей миграции `20260822_0094_billing_financial_core.py`; новую миграцию для этого исправления не добавлял.

## Не реализовано

- Остальные находки ревьюера относятся к invoice/ledger automation, frontend или product-browser тестам и не входят в API/данные атома 4.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Фича 5

# 09-billing · screen-dev · атом 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-seller-profile.spec.ts`

Экран `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellersScreen.tsx` не потребовал изменения: обязательный негативный путь реализован тестом на уже существующем UI.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не выполнен: в checkout отсутствует `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/node_modules/.bin/tsc`; запуск через `npx` завис без вывода и был остановлен.
- `python3 scripts/ui/ui_guard.py` — красный из-за уже существующих нарушений вне затронутых файлов: `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`.
- `npm run test:unit` — не выполнен: `vitest: command not found`.
- `git diff --check` — зелёный.

## Не реализовано

В пределах разрешённых файлов и данного атома пунктов контракта, которые не удалось реализовать буквально, нет. `S-31-TC-009` больше не пропускается: тест сохраняет корректные реквизиты, отправляет неверный ИНН, проверяет понятную ошибку и подтверждает, что сохранённые юридическое наименование и КПП не затёрты.

# Фича 6

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-tariffs.spec.ts
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: локального `tsc` нет, `npx` завис на попытке разрешить пакет и был остановлен.
- `python3 scripts/ui/ui_guard.py` — красный: обнаружено новое нарушение монолитного экрана для `FfSettingsScreen.tsx` (701 → 778 строк); baseline не обновлялся.
- `npm run test:unit` — красный: `vitest: command not found`, зависимости frontend не установлены.
- `git diff --check` — зелёный.
- Commit не создан: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`); изменения остаются локальными и не опубликованы.

## Не реализовано

- Загрузка сохранённых реквизитов, действующих тарифов и полной серверной истории буквально невозможна в пределах этой карточки: `backend/app/api/billing.py` предоставляет для них только mutation-ручки (`PUT`/`POST`), без `GET`. История отображается для версий, созданных в текущем UI-сеансе.
- Серверная проверка пересечения периодов и финальная атомарность сохранения остаются ответственностью backend и не менялись, так как файлы backend не входят в разрешённый список атома.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Фича 7

# 09-billing — backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_ledger_service.py` — атомарная запись операционного начисления через savepoint и безопасное разрешение гонки по уникальному событию.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_ledger_service.py` — тестовый savepoint-контекст для сценариев начисления.

## Гейты

- `ruff check .` — FAIL: 83 существующие ошибки вне изменённых файлов.
- `mypy .` — FAIL: 21 существующая ошибка в 6 файлах вне изменённых файлов.
- `pytest -q tests/test_billing_ledger_service.py` — PASS: 2 passed.
- `pytest -q` — прерван после длительного прогона без итогового результата; адресный набор зелёный.
- `python3 scripts/ci/back_guard.py` — FAIL/не доступен: файл `scripts/ci/back_guard.py` отсутствует в checkout.
- `python3 scripts/ci/check_migrations.py` — FAIL/не доступен: файл `scripts/ci/check_migrations.py` отсутствует в checkout.

## Не реализовано

- Остальные находки ревьюера относятся к другим атомам (счета, тарифы, UI, автоматический Celery-выпуск, ИНН, storage) и в этот backend-атом не входят.
- Миграций нет.

# Фича 8

# 09-billing — backend-dev · атом 8 после ревью

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_invoice_service.py` — единый алгоритм закрытого месяца по календарю МСК, блокировка незакрытого хранения, атомарное разрешение гонки, детализация ledger-источниками и идемпотентное сторно.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/tasks/billing_tasks.py` — ежедневный Celery-запуск: перебор tenant/селлеров и формирование предыдущего месяца.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py` — понятный HTTP 400 для незакрытого/некорректного периода.

## Гейты

- `ruff check app/services/billing_invoice_service.py app/tasks/billing_tasks.py app/api/billing.py` — PASS.
- `mypy app/services/billing_invoice_service.py app/tasks/billing_tasks.py app/api/billing.py` — PASS.
- `pytest -q tests/test_billing_invoice_service.py tests/test_billing_ledger_service.py` — PASS, 4 passed.
- `pytest -q` — полный прогон запущен, но итоговый вывод не получен в доступное время; адресные тесты зелёные.
- `ruff check .` — FAIL на 83 существующих ошибках вне изменённых billing-файлов, включая FBS/WB/scripts.
- `mypy .` — FAIL на существующих ошибках в 7 файлах вне изменённого слоя; изменённые файлы проверены отдельно и проходят.
- `python3 scripts/ci/back_guard.py` — НЕ ДОСТУПЕН: файла нет в checkout.
- `python3 scripts/ci/check_migrations.py` — НЕ ДОСТУПЕН: файла нет в checkout.
- `git diff --check` — PASS.

## Миграции

Нет: схема существующих моделей не менялась.

## Не реализовано

- Полный runtime-тест с реальным `StorageStatement` невозможен в этой копии: модель/таблица `StorageStatement` отсутствует. Сервис использует опубликованный межкарточный маркер `storage_statement` или `storage_statement_closed` в общем ledger.
- Полный интеграционный тест двух настоящих параллельных транзакций и Celery-брокера не добавлен; защита реализована на уникальном ограничении и обработке `IntegrityError`.
- GET-реестр счетов и UI-находки ревью не реализованы: они относятся к frontend/другим атомам.

## Находки

- В рабочем дереве уже было несвязанное изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/JOURNAL.md`; файл не изменялся этим атомом.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Фича 9

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/App.tsx — передан Bearer-токен в экран расчётов.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx — запросы начислений, счетов и отмены счета авторизованы; исправлена подпись пустого состояния.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не завершён: в checkout отсутствует локальный `tsc`, а `npx` ожидал установку пакета и был остановлен без сетевой установки.
- `python3 scripts/ui/ui_guard.py` — красный из-за пяти нарушений, не созданных этой правкой: `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`.
- `npm run test:unit` — не запущен: `vitest: command not found`.
- `git diff --check` — зелёный.

## Не реализовано

- Полный живой API-контракт `/billing/ledger` и `/billing/invoices` не расширялся: это backend-атомы, не входящие в разрешённые файлы этого экрана.
- Остальные находки ревью относятся к backend, настройкам тарифов, seller-профилю или e2e-тестам других атомов и здесь не исправлялись.

# Фича 10

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — очищает текущие начисления и счета перед новым запросом, чтобы ошибка не показывала старые данные как актуальные.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-ledger.spec.ts` — усиливает `S-31-TC-004`, `S-31-TC-005`, `S-31-TC-012` и добавляет проверку очистки устаревшей строки при ошибке обновления.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — этот отчёт.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: в checkout отсутствует локальный `tsc`, а `npx` не завершил выполнение в доступное время.
- `python3 scripts/ui/ui_guard.py` — FAIL из-за пяти новых/зафиксированных нарушений в чужих файлах: `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Нарушений в изменённом billing-экране нет; базовую линию не обновлял.
- `npm run test:unit` — FAIL: `vitest: command not found`.
- `git diff --check` — PASS.

## Не реализовано

- GET-ручки `/api/billing/ledger` и `/api/billing/invoices` отсутствуют в `backend/app/api/billing.py`. Добавление backend-файла запрещено границами этого экранного атома; E2E сохраняет маршрутные моки, чтобы проверять пользовательские сценарии экрана.
- Остальные находки REVIEW.md относятся к backend, `FfSettingsScreen.tsx`, моделям и сервисам, которые не входят в разрешённые файлы этого атома.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Фича 11

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx — добавлен вывод блокирующих причин выпуска счёта с единственным исправляющим действием; раскрытие детализации показывает исходные документы отдельными строками.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts — существующие сценарии S-31-TC-007 и S-31-TC-008 проверены; изменений тестового файла не потребовалось.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный из-за пяти уже существующих нарушений в несвязанных файлах: `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовую линию не обновлял.
- `npm run test:unit` — не запустился: в рабочей копии отсутствует команда `vitest` (`vitest: command not found`).

## Не реализовано

- REVIEW находки по backend API, автоматическому выставлению, моделям и сервисам не менялись: контракт этого атома разрешает только экран `FfBillingScreen.tsx` и `billing-invoices.spec.ts`.
- Кнопки исправления блокирующих причин оставлены без навигации, поскольку контракт не указывает маршруты для тарифов, селлера и хранения, а соседние экраны запрещены к изменению.
- E2E-сценарии S-31-TC-007 и S-31-TC-008 не запускались отдельно: в рабочей копии отсутствуют зависимости frontend для unit-запуска, а обязательный `ui_guard.py` уже сообщает несвязанные нарушения.
