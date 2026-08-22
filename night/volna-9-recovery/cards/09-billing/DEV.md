# Фича 1

# 09-billing — screen-dev

## Изменённые файлы

В рамках атома «Общая денежная ячейка и печать счёта» изменений в исходных файлах не потребовалось: требуемая реализация уже присутствует в checkout.

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Cells.tsx` — `MoneyCell` и `formatMoney`: RUB, две цифры, сторно без сигнальной окраски, правое выравнивание.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Actions.tsx` — `PrintAction` принимает `what="счёт"` и формирует подпись «Печать счёта».
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/index.ts` — экспортирует `MoneyCell`, `formatMoney` и `PrintAction`.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: команда `npx` зависла без вывода в окружении без доступного локального результата.
- `python3 scripts/ui/ui_guard.py` — красный из-за пяти ранее существующих нарушений в чужих файлах (`src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`); файлы этого атома не указаны.
- `npm run test:unit` — красный: `vitest: command not found`.
- Адресный unit-тест `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Cells.test.ts` уже покрывает положительную сумму, ноль, сторно и `—`.

## Не реализовано

По относящимся к этому атому пунктам контракта нереализованных требований не обнаружено. Находки `REVIEW.md` относятся к backend и соседним экранам; исправление их выходило бы за границы разрешённых файлов этого атома.

# Фича 2

# 09-billing · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/PeriodPicker.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

Компонент сохраняет контролируемое значение `YYYY-MM` при любых перерисовках родителя,
передаёт новое значение через `onChange`, поддерживает границы `min`/`max`, disabled-состояние
и текст ошибки. Для ошибки добавлена доступная связь поля с подсказкой через `aria-invalid` и
`aria-describedby`. Экспорт `PeriodPicker` и `PeriodPickerProps` уже присутствовал в
`frontend/src/ui-kit/index.ts`, поэтому файл экспорта не изменялся.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не запущен: в окружении отсутствует `frontend/node_modules/.bin/tsc` (exit 127).
- `python3 scripts/ui/ui_guard.py` — красный по пяти несвязанным существующим монолитным экранам: `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Нарушений в изменённом `PeriodPicker.tsx` не указано; базовую линию не обновлял.
- `npm run test:unit` — не запущен: команда `vitest` отсутствует в окружении (exit 127).
- `git diff --check` — зелёный.

## Не реализовано

Пунктов контракта, относящихся к `PeriodPicker`, которые не удалось реализовать буквально, нет.

# Фича 3

# 09-billing — backend-dev · rework атома 09-A

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_models.py` — реальная SQLite-проверка: второй charge с тем же tenant/source event и второе reversal для одной исходной строки отклоняются ограничениями базы.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_financial_core_migration.py` — проверка, что финансовое ядро присутствует в единственной Alembic-цепочке и в checkout нет нескольких heads.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — отчёт этого rework-прохода.

## Миграции

Нет новых миграций. Существующая `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_0094_billing_financial_core.py` уже создаёт общий набор billing-таблиц; адресная проверка подтверждает одну текущую вершину `20260822_0095`.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_models.py` — уникальность исходного события и уникальность reversal на уровне БД.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_financial_core_migration.py` — единственная Alembic-линия финансового ядра.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/models/billing.py tests/test_billing_models.py tests/test_billing_financial_core_migration.py` — PASS.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/models/billing.py` — PASS.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_models.py tests/test_billing_financial_core_migration.py` — PASS, 4 passed (одно предупреждение Alembic о конфигурации `path_separator`).
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && alembic heads` — PASS, `20260822_0095 (head)`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ci/back_guard.py` — не выполнен: файла нет по этому абсолютному пути (exit 2).
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ci/check_migrations.py` — не выполнен: файла нет по этому абсолютному пути (exit 2).
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && git diff --check` — PASS.

## Не реализовано

- Находки `REVIEW.md` по API, сервисам, задачам, реальным storage-statement, UI и e2e не относятся к модели и миграции атома 09-A; они не менялись.
- Изменять `down_revision` на отсутствующие в этом checkout миграции 03/07-A нельзя: Alembic перестанет собирать локальный граф. Вместо этого добавлена проверка единственного head; при интеграции соседних миграций она не позволит оставить несколько вершин.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Фича 4

# 09-billing — backend-dev, атом 4: API реквизитов и версионных тарифов

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_configuration_service.py` — нормализация обязательных банковских полей, единая tenant-проверка селлера и блокировка tenant/цепочки тарифов при создании новой версии; конфликт уникальности преобразуется в понятную доменную ошибку.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py` — чужой seller-profile не раскрывается, а конкурентный конфликт тарифа возвращает понятный HTTP 400 вместо 500.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_configuration_service.py` — проверка, что пробелы не проходят как обязательные банковские реквизиты.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_configuration_api.py` — HTTP-сценарий: валидный профиль и нулевая ставка, пробельные реквизиты, чужой селлер и конфликт версии.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — этот отчёт.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/services/billing_configuration_service.py app/api/billing.py tests/test_billing_configuration_service.py tests/test_billing_configuration_api.py` — пройдено: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/services/billing_configuration_service.py app/api/billing.py` — пройдено: `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_configuration_service.py tests/test_billing_configuration_api.py` — пройдено: `6 passed`.
- `git diff --check` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing` — пройдено, вывода нет.
- `python3 scripts/ci/back_guard.py` — неприменим: в атоме не добавлялся новый маршрут; файла `scripts/ci/back_guard.py` в этой рабочей копии нет.
- `python3 scripts/ci/check_migrations.py` — неприменим: миграция в атоме не добавлялась; файла `scripts/ci/check_migrations.py` в этой рабочей копии нет.

## Не реализовано

- Находки ревью по read-model начислений и счетов, формированию/сторно счетов, storage-barrier, дате включения биллинга, миграционной линии, frontend e2e и `docs/blockers/S-31.md` не относятся к атомарному API-контуру реквизитов и версионных тарифов; этот атом их не изменяет.
- Автоматическая переоценка уже записанных `BillingLedgerEntry` без ставки после добавления тарифа требует изменения ledger/invoice-контура и не выполнялась в этом атоме, чтобы не переписывать финансовую историю за пределами утверждённого шага.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Фича 5

# 09-billing · screen-dev · атом 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-seller-profile.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не выполнен: в `frontend/node_modules/.bin` отсутствует `tsc`; `npx` не завершился в доступное время.
- `python3 scripts/ui/ui_guard.py` — красный из-за пяти существующих нарушений в соседних файлах: `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Изменённый `SellersScreen.tsx` новым нарушением не отмечен.
- `npm run test:unit` — не выполнен: `vitest: command not found`.
- `git diff --check` — зелёный.

## Не реализовано

- Пунктов контракта в пределах атома 5, которые не удалось реализовать буквально, нет. Исправлены загрузка сохранённого профиля при раскрытии блока и негативный сценарий `S-31-TC-009`: после ошибочного ИНН success скрывается, а повторное открытие подтверждает ранее сохранённый ИНН.

# Фича 6

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — зелёный.
- `python3 scripts/ui/ui_guard.py` из корня — красный: обнаружены новые/накопленные нарушения монолитности, включая `FfSettingsScreen.tsx: 701 → 795`; baseline не обновлялся.
- `npm run test:unit -- --runInBand` из `frontend/` — не запущен: в окружении отсутствует команда `vitest` (`vitest: command not found`).

## Не реализовано

- Полная продуктовая browser-проверка сценариев S-31-TC-002, S-31-TC-003, S-31-TC-010, S-31-TC-011 и S-19-TC-001 не выполнена: в среде нет установленного test runner/dependency setup.
- Ревью-находки, относящиеся к backend и другим экранам, не менялись: контракт этого атома разрешает только `FfSettingsScreen.tsx` и его E2E-файл.

# Фича 7

# 09-billing — backend-dev, rework атома 7

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/models/tenant.py — добавлено nullable-поле `billing_enabled_from`; пустое значение оставляет биллинг выключенным для существующего tenant.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_0096_billing_activation_date.py — добавляющая миграция даты включения биллинга.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_configuration_service.py — первый явно сохранённый тариф фиксирует дату включения tenant равной `valid_from`.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_ledger_service.py — до даты включения не создаёт ни тарифицированную, ни `unpriced` строку; с даты включения сохраняет прежнее атомарное идемпотентное поведение.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_ledger_service.py — покрыт пропуск финального факта до даты включения.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_configuration_service.py — покрыта фиксация даты включения первым тарифом.

## Эндпоинты и сервисы

- Эндпоинты: нет; существующие финальные пути приёмки и ФФ→МП-отгрузки продолжают использовать `record_operational_charge`.
- Сервисы: `billing_ledger_service.record_operational_charge` применяет границу `billing_enabled_from`; `billing_configuration_service.create_tariff` записывает явный старт из первого выбранного `valid_from`.

## Миграции

- `20260822_0096_billing_activation_date` — добавляет nullable-колонку `tenants.billing_enabled_from`, без удаления или изменения существующих данных.

## Тесты

- `test_operational_charge_before_billing_activation_is_not_recorded` — старый финальный факт не создаёт ledger-запись.
- `test_first_tariff_explicitly_activates_billing_from_its_start_date` — первый тариф задаёт дату начала учёта.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/models/tenant.py app/services/billing_ledger_service.py app/services/billing_configuration_service.py tests/test_billing_ledger_service.py tests/test_billing_configuration_service.py alembic/versions/20260822_0096_billing_activation_date.py` — PASS.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/models/tenant.py app/services/billing_ledger_service.py app/services/billing_configuration_service.py` — PASS, 3 source files.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_ledger_service.py tests/test_billing_configuration_service.py` — PASS, 10 passed.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ci/back_guard.py` — не выполнен: файла `scripts/ci/back_guard.py` в этой рабочей копии нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ci/check_migrations.py` — не выполнен: файла `scripts/ci/check_migrations.py` в этой рабочей копии нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && alembic heads` — PASS, единственный head `20260822_0096`.
- `git diff --check` — PASS.

## Не реализовано

- Находки ревью по read-model, счетам, поздней тарификации, storage-barrier, сторно, API и UI не относятся к атому 7 и его не меняли.
- Перекрёстная корректировка базовой миграционной цепочки из находки 12 не относится к этому атому; новая миграция продолжает текущую единственную цепочку `20260822_0095 → 20260822_0096`.

## Блокеры

Git не позволяет создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock`: `Operation not permitted`. Поэтому commit и проверенный SHA не получены; изменения существуют только в рабочем дереве. Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не читались и не затрагивались.

# Фича 8

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py` — GET начислений и счетов принимают период `YYYY-MM`, значение `seller_id=all`, фильтры, возвращают оболочки экрана и отдельные блокирующие причины; формирование проверяет tenant через сервис.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_invoice_service.py` — проверена принадлежность селлера tenant, storage-barrier опирается на опубликованные `storage_measurement`, а строки счёта содержат неизменяемые дату и номер исходного факта.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_configuration_service.py` — добавление покрывающей ставки ретарифицирует только ранее неоценённые подходящие записи ledger.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_service.py` — обновлены сценарии формирования с проверкой tenant-принадлежности до поиска счёта.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_configuration_service.py` — обновлены моки потока ретарификации.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/docs/blockers/S-31.md` — зафиксированы объяснения `unpriced`, `missing_profile` и `storage_period_not_closed`.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/services/billing_invoice_service.py app/services/billing_configuration_service.py app/api/billing.py tests/test_billing_invoice_service.py tests/test_billing_configuration_service.py` — зелёный, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/services/billing_invoice_service.py app/services/billing_configuration_service.py app/api/billing.py` — зелёный, `Success: no issues found in 3 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_invoice_service.py tests/test_billing_configuration_service.py tests/test_billing_configuration_api.py tests/test_billing_ledger_service.py` — зелёный, `13 passed`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ci/back_guard.py` — не выполнен: файла `scripts/ci/back_guard.py` в рабочей копии нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ci/check_migrations.py` — не выполнен: файла `scripts/ci/check_migrations.py` в рабочей копии нет; миграции в этом rework не менялись.
- `git diff --check` — зелёный.

## Не реализовано

- Привязка `record_reversal` к конкретному пути отмены складского документа не внесена: в атоме не назван допустимый production-путь отмены, а новый маршрут создал бы неописанный контрактом способ менять финансовую историю.
- API возвращает блокирующие причины отдельным массивом `issues`; текущий экран должен потребить этот массив. Его изменение вне роли `backend-dev`.
- Миграция финансового ядра не менялась: обязательный предшественник 07-A отсутствует в этой рабочей копии, а изменение `down_revision` без него создало бы невалидную цепочку.

# Фича 9

# 09-billing · screen-dev rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

Экран берёт блокирующие причины из отдельного поля `issues` ответа списка счетов, а не из несуществующего поля счёта. После успешного повторного формирования он повторно запрашивает список. Добавлен e2e-сценарий `S-31-TC-013` для видимой причины и исправляющего действия.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Красный, новых нарушений экран не добавил: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py`. Зафиксированы уже существующие нарушения в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/App.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`; `--update` не применялся.
- Красный из-за неполных локальных зависимостей: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- --passWithNoTests FfBillingScreen` → `vitest: command not found`.
- Красный из-за тех же неполных зависимостей: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:e2e -- billing-ledger.spec.ts billing-invoices.spec.ts` → `error: unknown command 'test'`; локального `node_modules/.bin/playwright` нет.
- Зелёный: `git diff --check`.

## Не реализовано

- Backend-находки из `REVIEW.md` не изменялись: роль `screen-dev` ограничена экранным слоем.
- Целевые unit/e2e не запущены до завершения из-за отсутствующих локальных зависимостей. В тестовом файле добавлен сценарий, но его выполнение требует восстановить зависимости этой рабочей копии.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не затрагивались.

# Фича 10

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-ledger.spec.ts
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx playwright test tests-e2e/billing-ledger.spec.ts` — зелёный; выполнен только тестовый файл атома.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- --runInBand` — красный до запуска тестов: `sh: vitest: command not found`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` — красный из-за уже имеющихся отклонений вне файлов атома: `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не обновлялась.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check` — зелёный.
- Сохранение отдельным Git-коммитом не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` из-за ограничения прав текущей среды. Чужой `night/volna-9-recovery/JOURNAL.md` в индекс не добавлялся.

## Не реализовано

- Для S-31-TC-004, S-31-TC-005 и S-31-TC-012 экран передаёт в живой ledger API начало выбранного месяца в `date=YYYY-MM-01`, не отправляет `seller_id=all` и принимает реальный массив строк. Поиск, фильтр услуги и данные полей строки требуют серверного read-model; это находка ревью №2 и находится за границей screen-dev.
- Находки ревью №3–12 и №14 относятся к API, сервисам, миграциям и документации блокировок, поэтому в этот атомарный экранный проход не вносились. Находка №13 про `billing-invoices.spec.ts` также не относится к разрешённому тестовому файлу атома.
- Контракт не удалось подтвердить полностью: `test:unit` не запускается из-за отсутствующего Vitest, а `ui_guard.py` блокируется нарушениями в чужих файлах.

# Фича 11

# 09-billing — screen-dev, атом 11

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — для списка счетов выбран последний закрытый месяц, календарный период показан в читаемом виде, а детализация хранения не показывает технический источник.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts` — `S-31-TC-007` дополнительно проверяет снимки обеих сторон в HTML-печати и отсутствие управляющих кнопок.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — обязательный артефакт этапа.

## Гейты

- Зелёный: `npx --no-install tsc --noEmit -p tsconfig.app.json` (запуск из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend`).
- Красный, внешние для атома новые нарушения: `python3 ../scripts/ui/ui_guard.py` (запуск из `frontend/`) сообщает `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не менялась.
- Красный: `npm run test:unit -- --run src/screens/ff/FfBillingScreen.test.tsx` — в рабочей копии отсутствует `vitest` (`sh: vitest: command not found`); отдельного unit-теста экрана в `src/screens/ff/` нет.
- Зелёный: `npx --no-install playwright test tests-e2e/billing-invoices.spec.ts` (запуск из `frontend/`), только назначенный e2e-файл атома.
- Зелёный: `git diff --check`.

## Не реализовано

- Пункты контракта атома 11, относящиеся к экрану и e2e `S-31-TC-007`/`S-31-TC-008`, реализованы.
- Находки REVIEW.md по API, сервисам, моделям, миграции, записи ledger и документу `docs/blockers/S-31.md` не относятся к разрешённым файлам фронтенд-экрана и e2e этого атома, поэтому не менялись.
