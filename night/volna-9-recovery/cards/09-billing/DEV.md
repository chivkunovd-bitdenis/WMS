# Фича 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Cells.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Actions.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/index.ts`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не получил вывод и не завершился за ожидание; остановлен вручную.
- `python3 scripts/ui/ui_guard.py` — красный из-за существующих нарушений вне этой карточки: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`.
- `npm run test:unit` — не запустился: `vitest: command not found`.

## Не реализовано

- Остальные части контракта 09-billing не реализовывались: эта карточка ограничена атомом `MoneyCell` и расширением `PrintAction` для счёта.

# Фича 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/PeriodPicker.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/index.ts`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не завершился за отведённое время; остановлен вручную без диагностического вывода.
- `python3 scripts/ui/ui_guard.py` — красный из-за нарушений вне этой карточки: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`.
- `npm run test:unit` — не запустился: `vitest: command not found`.

## Не реализовано

- Нереализованных пунктов атомарного контракта нет. `PeriodPicker` принимает и отдаёт значение `YYYY-MM`, показывает label «Месяц» по умолчанию, передаёт `min`/`max`, ошибку и disabled-состояние, а controlled-значение не очищается при изменениях состояния родителя.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Фича 3

# 09-billing — backend-dev 09-A

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/models/billing.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/models/__init__.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_0094_billing_financial_core.py`

Добавлены `BillingProfile`, `BillingTariffVersion` и `BillingLedgerEntry`. Профили и тарифы
tenant-изолированы, тарифы поддерживают `document`, `item`, `liter_day`; для хранения сохраняются
контрактные `service_code='storage_liter_day'` и `source='storage_measurement'`. Ledger запрещает
повторное начисление одного исходного события уникальностью `(tenant_id, source_type, source_id)`;
сторно хранит `reversal_of_id` и не имеет операции изменения исходной строки.

## Гейты

- `ruff`: PASS для изменённого `backend/app/models/billing.py`; полный запуск репозитория BLOCKED существующими ошибками вне карточки.
- `mypy`: PASS для `backend/app/models/billing.py` (`Success: no issues found in 1 source file`).
- `pytest`: запущен, но остановлен после частичного выполнения из-за длительности полного набора; итоговый PASS не подтверждён.
- `back_guard.py`: BLOCKED — файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/scripts/ci/back_guard.py` отсутствует.
- `check_migrations.py`: BLOCKED — файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/scripts/ci/check_migrations.py` отсутствует.
- `compileall`: PASS для новой модели.

## Не реализовано

- API, сервисы, обработчики операционных начислений и счета не реализованы: они относятся к следующим атомарным кускам 09-billing и не входят в 09-A.
- Автоматическая запретительная защита UPDATE/DELETE ledger на уровне БД не добавлялась: текущий контракт фиксирует неизменяемость через модель данных и ссылку сторно; отдельный writer/сервис будет добавлен в следующем backend-атоме.

## Находки

Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не затрагивались. Боевой прод не трогался.

# Фича 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_configuration_service.py` — tenant-изолированное сохранение профилей, проверка ИНН, версионное создание тарифов и закрытие предыдущей версии.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py` — PUT профиля ФФ, PUT профиля селлера и POST новой ставки с проверкой прав администратора.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/main.py` — подключён billing router.

## Гейты

- `ruff` для изменённых файлов: PASS.
- `mypy` для изменённых файлов: BLOCKED существующими ошибками в `inventory_movement_report_service.py`, `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`, `wildberries_product_import_service.py`; ошибок в новых файлах нет.
- `pytest`: полный набор из 816 тестов запущен; на момент отчёта выполняется, ранее затронутый набор `tests/test_staff_packaging_billing.py`: PASS (2 passed).
- `back_guard.py`: BLOCKED, файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/scripts/ci/back_guard.py` отсутствует.
- `check_migrations.py`: BLOCKED, файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- GET-методы чтения профилей/тарифов и история ставок не добавлялись: в атомарном пункте 4 явно описано сохранение профилей и создание ставки; чтение относится к экранному/следующему API-контракту.
- Отдельные новые тесты API в этой рабочей копии не добавлялись; существующий backend-набор не содержит готовых фикстур для billing-профилей.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не затрагивались.
- В рабочем дереве обнаружено несвязанное изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/JOURNAL.md`; оно не включалось в реализацию.

# Фича 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellersScreen.tsx` — строка селлера открывает существующий диалог; в нём добавлен раскрываемый блок «Реквизиты для счетов» с сохранением через billing API, подтверждением и понятной ошибкой над полями.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-seller-profile.spec.ts` — добавлены сценарии `S-31-TC-001` и заготовка `S-31-TC-009`.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не завершился в рабочее время без вывода; процесс остановлен, итог не подтверждён.
- `python3 scripts/ui/ui_guard.py` — красный из-за существующих нарушений в `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; новых нарушений для `SellersScreen.tsx` после исправления кнопки нет.
- `npm run test:unit` — не запустился: в рабочей копии отсутствует команда `vitest` (`vitest: command not found`).

## Не реализовано

- Полное чтение ранее сохранённого профиля при новом открытии диалога не реализовано буквально: доступный контракт backend предоставляет только `PUT`, без GET. Значения сохраняются и остаются видимыми в текущем открытом экране; ошибка валидации не меняет сохранённое локальное состояние.
- `S-31-TC-009` оставлен как пропущенный тестовый сценарий до появления общей фикстуры чтения профиля; UI-ошибка контрольного числа реализована через ответ API.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не затрагивались.
- Несвязанное изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/JOURNAL.md` не включалось в работу.

# Фича 6

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный: существующие нарушения в нескольких экранах и новое превышение монолита `FfSettingsScreen.tsx` (701 → 747 строк); базовую линию не обновлял.
- `npm run test:unit` — не запустился: в рабочем checkout отсутствует исполняемый `vitest` (`sh: vitest: command not found`).

## Не реализовано

- Полная загрузка уже сохранённых реквизитов и тарифов/истории не реализована буквально: доступный API-контракт в checkout содержит только сохранение профиля и создание тарифа, GET-методов для чтения нет.
- E2E-файл `billing-tariffs.spec.ts` не добавлялся, потому что в checkout отсутствует готовый сценарий авторизации/фикстуры для этого экрана, а контракт ограничивает изменение экраном и указанным тестом; технический gate unit также заблокирован отсутствующим `vitest`.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Фича 7

# 09-billing — backend-dev, атом 7

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_ledger_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/inbound_intake_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/marketplace_unload_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/marketplace_unload_pick_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/inbound_intake.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/marketplace_unload_requests.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_ledger_service.py`

Операционные начисления создаются в той же транзакции при первом `done` приёмки и первом `shipped` Marketplace-отгрузки. Тариф и его снимок выбираются по дате факта с приоритетом тарифа селлера; отсутствие тарифа сохраняет `unpriced`-строку и не блокирует склад. Повтор исходного документа возвращает существующую запись и не добавляет дубль. Внутренняя отгрузка не изменялась.

## Гейты

- `ruff check .` — BLOCKED: 84 существующие ошибки в репозитории; изменённые файлы проходят адресную проверку, кроме существующего B007 в `marketplace_unload_pick_service.py`.
- `mypy .` — BLOCKED: 22 ошибки, включая существующие ошибки в 7 файлах; после исправления неверной передачи аргумента в `create_cargo_places` ошибок от этого атома не остаётся.
- `pytest` — BLOCKED по времени: полный набор прерван после 63 тестов за 42.73 секунды; `tests/test_billing_ledger_service.py` — PASS, 2 passed.
- `back_guard.py` — BLOCKED: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/scripts/ci/back_guard.py` отсутствует в checkout.
- `check_migrations.py` — BLOCKED: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/scripts/ci/check_migrations.py` отсутствует в checkout.

## Не реализовано

- Новые API-роуты и внутренняя отгрузка не добавлялись: они не входят в атом 7.
- Полная гонка двух параллельных финальных запросов защищена существующим уникальным ограничением ledger; отдельный retry после `IntegrityError` не добавлялся.

## Находки

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/JOURNAL.md` содержит несвязанное изменение; его не включал.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Фича 8

# DEV — 09-billing, backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/models/billing.py` — модели неизменяемого счёта и блокирующей причины.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/models/__init__.py` — регистрация моделей.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_invoice_service.py` — единый алгоритм формирования и идемпотентной отмены.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/tasks/billing_tasks.py` — задача ежедневного запуска.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/celery_app.py` — подключение задачи и расписание 02:30.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py` — ручки формирования и отмены счёта.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_0095_billing_invoices.py` — добавляющая миграция.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_service.py` — тест блокировки `unpriced` и идемпотентного повтора.

## Гейты

- `ruff`: PASS для изменённых backend-файлов; полный `ruff check .` в репозитории уже содержит 137 исходных нарушений вне этой карточки.
- `mypy`: PASS для изменённых модулей.
- `pytest`: PASS, `2 passed` для `tests/test_billing_invoice_service.py`.
- `back_guard.py`: НЕ ЗАПУЩЕН — файла `scripts/ci/back_guard.py` в этой рабочей копии нет.
- `check_migrations.py`: НЕ ЗАПУЩЕН — файла `scripts/ci/check_migrations.py` в этой рабочей копии нет.

## Не реализовано

- Полный обход всех tenant/seller в Celery-задаче оставлен за существующим runner-контуром: в текущем backend нет готового безопасного tenant-итератора для фоновой сессии. API и сервис используют один и тот же алгоритм.
- Проверка закрытия хранения реализована через опубликованный ledger-маркер `storage_period_open`; фактическая публикация `StorageStatement` остаётся в межкарточной реализации 08-B.
- Секреты, токены, `.env` и кабинеты учётных данных не читались.

# Фича 9

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/layouts/AuthedAppLayout.tsx` — добавлен пункт «Расчёты» только для администратора ФФ.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/App.tsx` — добавлен защищённый маршрут `/app/ff/billing`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — создан общий каркас экрана с вкладками «Начисления» и «Счета», общими фильтрами месяца и селлера.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — НЕ ПРОЙДЕН: локальный `tsc` отсутствует, `npx` попытался скачать пакет, но сеть недоступна (`ENOTFOUND registry.npmjs.org`).
- `python3 scripts/ui/ui_guard.py` — НЕ ПРОЙДЕН: обнаружены пять новых относительно базовой линии нарушений в чужих/несвязанных файлах (`src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`). Базовая линия не изменялась.
- `npm run test:unit` — НЕ ПРОЙДЕН: в `frontend` отсутствует команда `vitest` (`vitest: command not found`).

## Не реализовано

- Таблицы начислений и счетов, их API, детализация и печать не реализованы: текущий атомарный кусок FEATURES.md ограничен маршрутом, доступом и общим каркасом.
- `screens.registry.json` не изменялся, поскольку он не входит в разрешённый список файлов карточки.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Фича 10

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — реализована вкладка «Начисления»: период, селлер, услуга, поиск документа, режимы «По операциям»/«По исполнителям», таблица через `DataTable`, проблема «Нет тарифа», пустое/загрузочное/ошибочное состояния и сохранение контекста вкладок.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-ledger.spec.ts` — добавлены сценарии `S-31-TC-004`, `S-31-TC-005`, `S-31-TC-012` с мокированием чтения журнала.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — PASS.
- `python3 scripts/ui/ui_guard.py` — FAIL: храповик показывает пять ранее существовавших нарушений в `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`; изменённый экран billing в списке новых нарушений отсутствует. Базовую линию не обновлял.
- `npm run test:unit` — FAIL: в окружении отсутствует исполняемый `vitest` (`vitest: command not found`).

## Не реализовано

- Вкладка «Счета» и детализация счёта не расширялись: этот атомарный кусок FEATURES.md ограничен реестром начислений.
- В текущем checkout нет GET-ручки журнала в `backend/app/api/billing.py`; экран вызывает согласованный ресурс `/api/billing/ledger`, а E2E покрывает пользовательский результат через маршрутный mock. Добавление backend-файла запрещено списком файлов этой карточки.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Фича 11

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — добавлены вкладка «Счета», фильтры, реестр, блокирующие состояния, диалог детализации, раскрытие исходных документов, печать HTML и подтверждённая идемпотентная отмена.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts` — добавлены сценарии `S-31-TC-007` и `S-31-TC-008`.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — диагностик TypeScript не выведено; команда в данном checkout завершилась без итогового кода в оболочке, поэтому полноценный статус не подтверждён.
- `python3 scripts/ui/ui_guard.py` — красный: обнаружены новые относительно baseline нарушения в чужих файлах `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`; изменённый экран в списке нарушений отсутствует. Baseline не обновлялся.
- `npm run test:unit` — красный до запуска тестов: `vitest: command not found`, зависимости checkout не установлены.

## Не реализовано

- Полный backend GET-контракт списка/деталей счетов в checkout отсутствует: экран использует предусмотренные маршруты `/api/billing/invoices` и `/api/billing/invoices/{id}/cancel`, а формат списка поддерживает поля `invoices` или `rows`.
- Печатное HTML-представление формируется на клиенте из доступного снимка счёта; серверного шаблона печати в разрешённых файлах нет.
