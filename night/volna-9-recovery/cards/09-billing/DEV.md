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

# 09-A backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/models/billing.py` — частичные уникальные индексы для общих/селлерских версий тарифов и для `reversal_of_id`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_0094_billing_financial_core.py` — соответствующие добавляющие ограничения миграции.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_models.py` — проверки индексов SQLite-схемы.

## Гейты

- `ruff check .` — FAIL на существующих ошибках вне атома (83 ошибки в других файлах); `ruff check app/models/billing.py tests/test_billing_models.py` — PASS.
- `mypy .` — FAIL на 17 существующих ошибках вне атома; `mypy app/models/billing.py` — PASS.
- `pytest` — прерван после 216 PASS и 3 skipped из 825 тестов, без падений в пройденной части; целевые billing-тесты PASS, 4 теста.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в рабочей копии по указанному пути.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в рабочей копии по указанному пути.
- `git diff --check` — PASS.

## Не реализовано

- Находки ревью про API, сервисы, задачи и frontend не входят в атом 09-A и намеренно не изменялись.
- Отдельная миграция для удаления старой уникальности не нужна: исходная миграция ещё содержит создаваемую схему, поэтому nullable-уникальность заменена до создания таблицы.

## Находки

- В рабочем дереве до начала работы уже были изменены `night/volna-9-recovery/JOURNAL.md` и удалён прежний `night/volna-9-recovery/cards/09-billing/DEV.md`; эти изменения не относятся к коду атома.

# Фича 4

# DEV-09 — API реквизитов и версионных тарифов

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_configuration_service.py` — закрытый набор услуг и единиц (`inbound`, `marketplace_outbound`, `storage_liter_day`), включая явный `liter_day` для хранения и понятные ошибки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py` — GET профилей ФФ/селлера и GET тарифов с tenant-фильтрацией; существующие mutation-ручки сохранены.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_configuration_service.py` — проверки неизвестной услуги и недопустимой единицы хранения.

## Миграции

Нет: схема базы данных этим атомом не изменялась.

## Тесты

- Проверена валидация ИНН и конфликт дат версий.
- Добавлены проверки, что неизвестная услуга и `storage_liter_day` с единицей `item` отклоняются.
- Запущены `tests/test_billing_configuration_service.py` и `tests/test_billing_models.py`: 6 passed.

## Гейты

- `ruff`: пройден для изменённых backend-файлов.
- `mypy`: пройден для изменённых API и сервиса.
- `pytest`: профильный набор пройден, 6 passed; полный набор не запускался.
- `back_guard.py`: не запущен — файл отсутствует в этой рабочей копии по пути `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/scripts/ci/back_guard.py`.
- `check_migrations.py`: не запущен — файл отсутствует в этой рабочей копии по пути `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/scripts/ci/check_migrations.py`.
- `git diff --check`: пройден.

## Не реализовано

- Исправления начислений, счетов, фоновых задач, UI и внешних интеграций не входят в атом API конфигурации и не изменялись.
- Конкурентная защита от двух одновременных записей остаётся на существующих индексах базы; новую миграцию для перестройки индексов в этот атом не добавлял.

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

# 09-billing — backend-dev

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_ledger_service.py — подбор тарифа по календарной дате МСК и безопасная постановка ledger-записи внутри savepoint.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/inbound_intake_service.py — начисление при финализации коробочного и сохранённого распределения; передача исполнителя.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/inbound_intake.py — передача user.id в оба финальных backend-пути.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_ledger_service.py — тест границы календарного месяца МСК.

## Миграции

Нет.

## Тесты

- Адресные: `13 passed` для ledger, distribution и box putaway сценариев.
- Добавлен тест выбора тарифа для операции `2026-03-01 00:30` по МСК.

## Гейты

- `ruff check .` — FAIL на существующих несвязанных нарушениях в baseline; адресный ruff изменённых файлов — PASS.
- `mypy .` — FAIL на существующих несвязанных ошибках в baseline; ошибок в изменённых файлах в выводе нет.
- `pytest` — FAIL в baseline на `tests/test_fbs_supply_from_orders.py` (полная прогонка остановлена после обнаружения unrelated failure); адресный набор PASS (13 тестов).
- `python3 scripts/ci/back_guard.py` — не запущен: файла нет в этой рабочей копии по требуемому пути.
- `python3 scripts/ci/check_migrations.py` — не запущен вместе с back_guard из-за отсутствия `scripts/ci/back_guard.py`.

## Не реализовано

- Остальные находки REVIEW.md относятся к UI, billing API/invoice или соседним атомам и намеренно не менялись.
- Новых роутов и миграций в этом атоме нет.

## Блокеры

- Реализация проверена, но commit невозможен: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` из-за запрета доступа к общем worktree metadata. Поэтому результат локальный, SHA отсутствует.

# Фича 8

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py — добавлены реальные GET-ручки начислений, списка счетов и детализации счета с tenant/admin изоляцией.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_invoice_service.py — пустой месяц и незакрытое хранение блокируют выпуск, строки счета получают стабильный `id`.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/tasks/billing_tasks.py — ежедневный запуск догоняет все закрытые месяцы, для которых есть ledger-факты.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/celery_app.py — расписание Celery закреплено за Europe/Moscow.

## Гейты

- ruff — зелёный для изменённых backend-файлов.
- mypy — зелёный для изменённых backend-файлов.
- pytest — адресные billing-тесты: 7 passed; полный запуск начат, в этой сессии остановился на длительном прогоне после 16% без финального результата.
- back_guard.py — не выполнен: файл отсутствует в этой рабочей копии.
- check_migrations.py — не выполнен: файл отсутствует в этой рабочей копии.

## Не реализовано

- Полная переоценка ранее `unpriced` ledger-строк после добавления тарифа не внесена: immutable ledger не должен переписывать исторический факт; повторный выпуск остаётся заблокированным до отдельного решения алгоритма ретарификации.
- Подключение `record_reversal` к конкретному бизнес-событию отмены не менялось: в разрешённом атоме нет названного backend-пути отмены складской операции.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Фича 9

# 09-billing · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

Экран оставлен в границах контракта: маршрут и пункт меню уже были доступны только администратору, поэтому `App.tsx` и `AuthedAppLayout.tsx` не менялись.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не завершён: процесс не вывел ошибок, но завис в окружении без завершения и был остановлен после ожидания.
- `python3 scripts/ui/ui_guard.py` — красный из-за пяти ранее существовавших нарушений в `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; `--update` не применялся.
- `npm run test:unit` — не запущен: в окружении отсутствует команда `vitest` (`vitest: command not found`).

## Не реализовано

- Backend-находки из `REVIEW.md` не исправлялись: они находятся вне файлового списка атома `09-billing` и требуют отдельного backend-прохода.
- Полное browser product review не выполнялось ролью `screen-dev`.

# Фича 10

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — исправлено состояние повторного формирования счёта: блокирующая причина передаётся через `disabledReason`, после устранения причин показывается действие с контрактной подписью; переходы «Открыть тарифы» и другие исправляющие действия сохранены.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-ledger.spec.ts` — сценарий `S-31-TC-004` теперь проверяет отправку номера документа в запросе, а также сохранение данных при переключении вкладок.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: локальная команда `npx` не завершилась и не вывела результат; остановлена после ожидания.
- `python3 scripts/ui/ui_guard.py` — красный по пяти нарушениям в несвязанных файлах: `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/ff/FfSettingsScreen.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не изменялась.
- `npm run test:unit` — не запущен: в окружении отсутствует исполняемый файл `vitest` (`vitest: command not found`).

## Не реализовано

- Backend-находки ревью (GET API, пересчёт начислений, timezone, идемпотентность и миграции) не изменялись: контракт этого атома разрешает только экран `FfBillingScreen.tsx` и `billing-ledger.spec.ts`.
- Исправление доступа и состояния вкладки тарифов в `FfSettingsScreen.tsx` не выполнялось по той же границе файлов.

# Фича 11

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts — сценарий `S-31-TC-007` теперь открывает печатное popup-окно и проверяет содержимое HTML счёта; `S-31-TC-008` проверяет подтверждённую отмену и отсутствие повторного запроса.

Экран `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` проверен по находкам ревьюера: в текущем коде исправляющие действия, безопасная печать со снимками реквизитов и идемпотентное UI-состояние отмены уже реализованы, поэтому файл не изменялся.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: процесс не завершился за время проверки и был остановлен.
- `python3 scripts/ui/ui_guard.py` — красный из-за новых относительно baseline нарушений в чужих файлах: `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Файлы атома 11 не затронуты; baseline не обновлялся.
- `npm run test:unit` — не запустился: в окружении отсутствует команда `vitest` (`vitest: command not found`).

## Не реализовано

- Backend-находки 1–13 и находка 17 относятся к другим слоям и файлам; по ограничению атома 11 они не изменялись.
- Полный запуск e2e `billing-invoices.spec.ts` не подтверждён, потому что локальные frontend-зависимости не установлены (`vitest` отсутствует), а `tsc` не завершился.
